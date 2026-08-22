"""Permission/scope matrix for the dashboard metric registry."""

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.contrib.auth.models import Group, Permission
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import (
    ADMIN,
    AGENT,
    BRANCH_MANAGER,
    REGION_MANAGER,
    ScopeType,
    role_group_name,
)
from apps.user.services.role_assignments import (
    create_role_assignment,
    get_effective_access,
    revoke_role_assignment,
)
from apps.web.authorization import ROUTE_POLICIES
from apps.web.metrics import (
    METRIC_BY_KEY,
    METRIC_DEFINITIONS,
    METRIC_GROUP_BY_KEY,
    SOURCE_MODULE_AVAILABILITY,
    Availability,
    MetricScope,
    UnavailableBehavior,
    dashboard_metrics,
    format_count,
    format_currency,
    format_percent,
    pending_source,
    resolve_scope,
    select_metrics,
    utilization_ratio,
    year_to_date_start,
)

SELF_METRIC_KEYS = (
    "ownActiveTransactions",
    "ownUpcomingClosings",
    "ownCommissionYtd",
    "ownPendingTasks",
    "ownFollowUpsDue",
    "ownNewLeads",
)

TEAM_METRIC_KEYS = (
    "teamActiveTransactions",
    "teamContractsAwaitingSignature",
    "teamOverdueInventory",
    "teamRoomUtilization",
    "teamNewAgents",
    "teamOpenTasks",
    "teamComplianceExceptions",
)

# Branch and region managers do not hold every operations permission, so their
# team card set is a documented subset rather than the whole band.
BRANCH_TEAM_METRIC_KEYS = (
    "teamOverdueInventory",
    "teamRoomUtilization",
    "teamNewAgents",
    "teamOpenTasks",
)
REGION_TEAM_METRIC_KEYS = (
    "teamActiveTransactions",
    "teamOverdueInventory",
    "teamRoomUtilization",
    "teamNewAgents",
    "teamOpenTasks",
)


def keys(user) -> list[str]:
    return [definition.key for definition in select_metrics(user)]


def payload_keys(payload: dict) -> list[str]:
    return [metric["key"] for group in payload["groups"] for metric in group["metrics"]]


def make_user(email: str, office: Office | None = None) -> User:
    return User.objects.create_user(email=email, profile_completed=True, office=office)


def system_actor() -> User:
    actor, _ = User.objects.get_or_create(
        email="system@example.com",
        defaults={"is_superuser": True, "is_staff": True},
    )
    return actor


def assign(user: User, role: str, scope_type: str, office: Office | None = None):
    return create_role_assignment(
        actor=system_actor(),
        target_user=user,
        role=role,
        scope_type=scope_type,
        scope_office=office,
    )


def branch(index: int = 0) -> Office:
    offices = list(
        Office.assignable_queryset().filter(kind=Office.Kind.BRANCH).order_by("pk")
    )
    assert len(offices) > index
    return offices[index]


def region_of(office: Office) -> Office:
    assert office.region is not None
    return office.region


def other_region_office(office: Office) -> Office:
    """An assignable office under a different region.

    Not necessarily a branch: the seeded tree puts every branch under
    Mid-Atlantic, so the cross-region case is a New England regional office.
    """
    other = (
        Office.assignable_queryset()
        .filter(kind__in=[Office.Kind.BRANCH, Office.Kind.REGIONAL_OFFICE])
        .exclude(region=office.region)
        .order_by("pk")
        .first()
    )
    assert other is not None
    return other


def agent(email: str, office: Office | None = None) -> User:
    user = make_user(email, office=office)
    if office is not None:
        assign(user, AGENT, ScopeType.OFFICE, office)
    else:
        user.groups.add(Group.objects.get(name=role_group_name(AGENT)))
    return user


def branch_manager(email: str, office: Office) -> User:
    user = make_user(email, office=office)
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office)
    return user


def region_manager(email: str, region: Office) -> User:
    user = make_user(email)
    assign(user, REGION_MANAGER, ScopeType.REGION, region)
    return user


def company_admin(email: str) -> User:
    user = make_user(email)
    assign(user, ADMIN, ScopeType.COMPANY)
    return user


def inertia_props(response) -> dict:
    return json.loads(response.content)["props"]


def metrics_props(client, user) -> dict:
    client.force_login(user)
    response = client.get(
        reverse("dashboard"),
        HTTP_X_INERTIA="true",
        HTTP_X_INERTIA_PARTIAL_DATA="metrics",
        HTTP_X_INERTIA_PARTIAL_COMPONENT="Dashboard",
    )
    assert response.status_code == 200
    return inertia_props(response)["metrics"]


def metrics_data(client, user) -> dict:
    """Unwrap the widget envelope down to the metric payload."""
    widget = metrics_props(client, user)
    assert widget["status"] == "ready"
    return widget["data"]


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_registry_rows_are_unique_grouped_and_documented():
    registry_keys = [definition.key for definition in METRIC_DEFINITIONS]
    assert len(registry_keys) == len(set(registry_keys))
    assert set(registry_keys) == set(SELF_METRIC_KEYS) | set(TEAM_METRIC_KEYS)
    for definition in METRIC_DEFINITIONS:
        assert definition.group in METRIC_GROUP_BY_KEY
        assert definition.source_module in SOURCE_MODULE_AVAILABILITY
        assert definition.all_permissions, f"{definition.key} must gate on a permission"
        assert definition.definition.strip(), f"{definition.key} needs a definition"
        assert definition.scopes
    orders = [definition.order for definition in METRIC_DEFINITIONS]
    assert orders == sorted(orders)


def test_every_drill_down_requires_at_least_the_metric_permissions():
    """Hiding a card is never the only protection behind the figure."""
    checked = 0
    for definition in METRIC_DEFINITIONS:
        if definition.drill_down is None:
            continue
        policy = next(
            policy
            for policy in ROUTE_POLICIES.values()
            if definition.drill_down.route_name in policy.route_names
        )
        assert policy.access == "permission_protected"
        assert set(definition.all_permissions).issubset(set(policy.all_permissions))
        checked += 1
    assert checked, "expected at least one metric with a guarded drill-down"


# --------------------------------------------------------------------------- #
# Selection matrix
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fixture", "expected_scope", "expected_keys"),
    [
        ("no_role", MetricScope.SELF, ()),
        ("agent", MetricScope.SELF, SELF_METRIC_KEYS),
        ("agent_with_assignment", MetricScope.OFFICE, SELF_METRIC_KEYS),
        (
            "branch_manager",
            MetricScope.OFFICE,
            SELF_METRIC_KEYS + BRANCH_TEAM_METRIC_KEYS,
        ),
        (
            "region_manager",
            MetricScope.REGION,
            SELF_METRIC_KEYS + REGION_TEAM_METRIC_KEYS,
        ),
        ("company_admin", MetricScope.COMPANY, SELF_METRIC_KEYS + TEAM_METRIC_KEYS),
        ("superuser", MetricScope.COMPANY, SELF_METRIC_KEYS + TEAM_METRIC_KEYS),
        (
            "multi_role",
            MetricScope.REGION,
            SELF_METRIC_KEYS + REGION_TEAM_METRIC_KEYS,
        ),
    ],
)
def test_metric_selection_matrix(fixture, expected_scope, expected_keys):
    office = branch()
    if fixture == "no_role":
        user = make_user("nobody@example.com")
    elif fixture == "agent":
        user = agent("agent@example.com")
    elif fixture == "agent_with_assignment":
        user = agent("scoped-agent@example.com", office)
    elif fixture == "branch_manager":
        user = branch_manager("branch@example.com", office)
    elif fixture == "region_manager":
        user = region_manager("region@example.com", region_of(office))
    elif fixture == "company_admin":
        user = company_admin("admin@example.com")
    elif fixture == "superuser":
        user = User.objects.create_superuser(email="root@example.com")
    else:
        user = make_user("multi@example.com", office=office)
        assign(user, AGENT, ScopeType.OFFICE, office)
        assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office)
        assign(user, REGION_MANAGER, ScopeType.REGION, region_of(office))

    assert resolve_scope(user, get_effective_access(user)) == expected_scope
    selected = keys(user)
    # Registry order, exactly once each, for every fixture.
    assert selected == [
        definition.key
        for definition in METRIC_DEFINITIONS
        if definition.key in set(expected_keys)
    ]
    assert len(selected) == len(set(selected))


@pytest.mark.django_db
def test_multi_role_resolution_is_a_stable_union_without_duplicates():
    office = branch()
    solo_agent = agent("solo-agent@example.com", office)
    solo_manager = branch_manager("solo-manager@example.com", office)

    combined = make_user("combined@example.com", office=office)
    assign(combined, AGENT, ScopeType.OFFICE, office)
    assign(combined, BRANCH_MANAGER, ScopeType.OFFICE, office)

    expected = set(keys(solo_agent)) | set(keys(solo_manager))
    assert set(keys(combined)) == expected
    # Deterministic: the same request twice yields the same ordered list, and a
    # role held twice over never doubles a card.
    assert keys(combined) == keys(combined)
    assert len(keys(combined)) == len(expected)


@pytest.mark.django_db
def test_manager_role_never_downgrades_the_agent_metric_set():
    office = branch()
    manager = branch_manager("no-downgrade@example.com", office)
    assert set(SELF_METRIC_KEYS).issubset(set(keys(manager)))


@pytest.mark.django_db
def test_permission_without_scope_does_not_grant_a_team_metric():
    user = make_user("perms-no-scope@example.com")
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web",
            content_type__model="operationspermission",
            codename="view_new_agents",
        )
    )
    assert resolve_scope(user, get_effective_access(user)) == MetricScope.SELF
    assert "teamNewAgents" not in keys(user)


@pytest.mark.django_db
def test_revoked_assignment_drops_its_team_metrics():
    office = branch()
    manager = make_user("revoked@example.com", office=office)
    assignment = assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    assert "teamNewAgents" in keys(manager)

    revoke_role_assignment(actor=system_actor(), assignment=assignment)
    assert keys(manager) == []


@pytest.mark.django_db
def test_expired_assignment_drops_its_team_metrics():
    office = branch()
    manager = make_user("expiring@example.com", office=office)
    assignment = assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    assignment.ends_at = timezone.now() - timedelta(minutes=1)
    assignment.status = UserRoleAssignment.Status.ACTIVE
    assignment.save(update_fields=["ends_at", "status"])
    assert keys(manager) == []


@pytest.mark.django_db
def test_anonymous_user_selects_nothing():
    from django.contrib.auth.models import AnonymousUser

    assert select_metrics(cast(User, AnonymousUser())) == ()


# --------------------------------------------------------------------------- #
# Card selection and the data behind it stay aligned
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_losing_a_permission_removes_both_the_card_and_its_drill_down(client):
    office = branch()
    manager = branch_manager("drilldown@example.com", office)
    assert "teamNewAgents" in keys(manager)

    client.force_login(manager)
    assert client.get(reverse("admin_new_agents")).status_code == 200

    group = Group.objects.get(name=role_group_name(BRANCH_MANAGER))
    group.permissions.remove(
        Permission.objects.get(
            content_type__app_label="web",
            content_type__model="operationspermission",
            codename="view_new_agents",
        )
    )
    manager = User.objects.get(pk=manager.pk)

    assert "teamNewAgents" not in keys(manager)
    assert client.get(reverse("admin_new_agents")).status_code == 403


@pytest.mark.django_db
def test_stripping_commission_permission_drops_only_the_commission_card():
    """Commission visibility is independent of the rest of the agent pipeline."""
    office = branch()
    user = agent("no-commission@example.com", office)
    assert "ownCommissionYtd" in keys(user)
    assert "ownActiveTransactions" in keys(user)

    group = Group.objects.get(name=role_group_name(AGENT))
    group.permissions.remove(
        Permission.objects.get(
            content_type__app_label="web",
            content_type__model="dashboardmetricpermission",
            codename="view_own_commission",
        )
    )
    user = User.objects.get(pk=user.pk)

    selected = keys(user)
    assert "ownCommissionYtd" not in selected
    assert "ownActiveTransactions" in selected
    assert "ownPendingTasks" in selected


# --------------------------------------------------------------------------- #
# Aggregation and scope
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_new_agents_aggregate_excludes_other_offices():
    home = branch(0)
    away = branch(1)
    assert home.pk != away.pk
    make_user("home-newcomer@example.com", office=home)
    make_user("away-newcomer@example.com", office=away)
    make_user("unplaced-newcomer@example.com")

    manager = branch_manager("branch-count@example.com", home)
    payload = dashboard_metrics(manager)
    metric = next(
        item
        for group in payload["groups"]
        for item in group["metrics"]
        if item["key"] == "teamNewAgents"
    )
    # The manager and their own office newcomer; nobody from another office and
    # nobody without an office.
    assert metric["value"] == "2"
    assert metric["availability"] == Availability.AVAILABLE
    assert metric["scopeLevel"] == MetricScope.OFFICE


@pytest.mark.django_db
def test_new_agents_aggregate_covers_a_whole_region_without_double_counting():
    home = branch(0)
    region = region_of(home)
    sibling = (
        Office.assignable_queryset()
        .filter(kind=Office.Kind.BRANCH, region=region)
        .exclude(pk=home.pk)
        .first()
    )
    assert sibling is not None
    outside = other_region_office(home)

    make_user("region-a@example.com", office=home)
    make_user("region-b@example.com", office=sibling)
    make_user("outside@example.com", office=outside)

    manager = region_manager("regional@example.com", region)
    # Also office-scoped inside the same region: the union must not count the
    # overlapping office twice.
    assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, home)

    payload = dashboard_metrics(manager)
    metric = next(
        item
        for group in payload["groups"]
        for item in group["metrics"]
        if item["key"] == "teamNewAgents"
    )
    assert metric["value"] == "2"


@pytest.mark.django_db
def test_company_wide_admin_counts_every_office():
    make_user("everywhere-a@example.com", office=branch(0))
    make_user("everywhere-b@example.com", office=other_region_office(branch(0)))
    admin = company_admin("brokerage@example.com")

    payload = dashboard_metrics(admin)
    metric = next(
        item
        for group in payload["groups"]
        for item in group["metrics"]
        if item["key"] == "teamNewAgents"
    )
    assert metric["value"] == format_count(User.objects.filter(is_active=True).count())
    assert payload["scope"] == {"level": "company", "label": "Brokerage-wide"}


@pytest.mark.django_db
def test_new_agents_window_excludes_joins_outside_the_trailing_window():
    office = branch()
    stale = make_user("stale@example.com", office=office)
    User.objects.filter(pk=stale.pk).update(
        date_joined=timezone.now() - timedelta(days=45)
    )
    manager = branch_manager("window@example.com", office)

    payload = dashboard_metrics(manager)
    metric = next(
        item
        for group in payload["groups"]
        for item in group["metrics"]
        if item["key"] == "teamNewAgents"
    )
    assert metric["value"] == "1"


@pytest.mark.django_db
def test_inactive_users_are_not_counted_as_new_agents():
    office = branch()
    User.objects.create_user(
        email="deactivated@example.com",
        profile_completed=True,
        office=office,
        is_active=False,
    )
    manager = branch_manager("active-only@example.com", office)

    payload = dashboard_metrics(manager)
    metric = next(
        item
        for group in payload["groups"]
        for item in group["metrics"]
        if item["key"] == "teamNewAgents"
    )
    assert metric["value"] == "1"


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_unconnected_source_module_is_marked_rather_than_calculated():
    office = branch()
    manager = branch_manager("unavailable@example.com", office)
    payload = dashboard_metrics(manager)
    metric = next(
        item
        for group in payload["groups"]
        for item in group["metrics"]
        if item["key"] == "teamRoomUtilization"
    )
    assert metric["availability"] == Availability.UNAVAILABLE
    assert metric["value"] is None
    assert "rawValue" not in metric
    assert "asOf" in metric
    assert "not connected" in metric["unavailableReason"]
    # The destination is still offered: the metric is unmeasured, not forbidden.
    assert metric["drillDown"]["href"] == reverse("admin_reservations")


@pytest.mark.django_db
def test_zero_new_agents_is_available_zero_not_unavailable():
    """An empty trailing window is a measured zero, not an unconnected module."""
    office = branch()
    # The manager themselves joined "now" and would count; age them out of the
    # trailing window so the aggregate is genuinely empty.
    manager = branch_manager("zero-agents@example.com", office)
    User.objects.filter(pk=manager.pk).update(
        date_joined=timezone.now() - timedelta(days=45)
    )
    manager = User.objects.get(pk=manager.pk)

    at = timezone.now()
    payload = dashboard_metrics(manager, at=at)
    metric = next(
        item
        for group in payload["groups"]
        for item in group["metrics"]
        if item["key"] == "teamNewAgents"
    )
    assert metric["availability"] == Availability.AVAILABLE
    assert metric["value"] == "0"
    assert metric["rawValue"] == 0
    assert metric["unit"] == "count"
    assert metric["asOf"] == at.isoformat()
    # The prior window holds the aged-out manager, so the period-over-period
    # comparison is a real decline — reported honestly rather than flattened.
    assert metric["trend"] == "down"
    assert metric["delta"] == "-100%"
    assert metric["comparedTo"] == "1"


@pytest.mark.django_db
def test_omit_behavior_drops_an_unavailable_metric_from_the_payload(monkeypatch):
    """The other half of the availability policy, exercised on a real row."""
    original = METRIC_BY_KEY["teamRoomUtilization"]
    omitted = replace(original, unavailable_behavior=UnavailableBehavior.OMIT)
    patched = tuple(
        omitted if definition.key == original.key else definition
        for definition in METRIC_DEFINITIONS
    )
    monkeypatch.setattr("apps.web.metrics.METRIC_DEFINITIONS", patched)

    manager = branch_manager("omitted@example.com", branch())
    assert "teamRoomUtilization" not in payload_keys(dashboard_metrics(manager))


def test_available_module_flags_stay_in_step_with_the_registry():
    used = {definition.source_module for definition in METRIC_DEFINITIONS}
    assert used.issubset(set(SOURCE_MODULE_AVAILABILITY))
    # Anything already available must have a calculator that is actually wired.
    for definition in METRIC_DEFINITIONS:
        if SOURCE_MODULE_AVAILABILITY[definition.source_module]:
            assert definition.calculator is not pending_source


# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #


def test_format_count_keeps_whole_numbers_and_thousands_separators():
    assert format_count(0) == "0"
    assert format_count(4) == "4"
    assert format_count(1234) == "1,234"


def test_format_currency_shows_honest_cent_scale():
    assert format_currency(0) == "$0.00"
    assert format_currency(Decimal("1234.5")) == "$1,234.50"
    assert format_currency(Decimal("-10.1")) == "-$10.10"


def test_format_percent_avoids_fake_precision_by_default():
    assert format_percent(0) == "0%"
    assert format_percent(0.425) == "42%"
    assert format_percent(0.425, places=1) == "42.5%"


# --------------------------------------------------------------------------- #
# Windows, denominators, timezone
# --------------------------------------------------------------------------- #


def test_utilization_ratio_guards_its_denominator():
    assert utilization_ratio(90, 120) == pytest.approx(0.75)
    # No bookable minutes is unmeasured, not zero usage.
    assert utilization_ratio(0, 0) is None
    assert utilization_ratio(30, -10) is None
    # Double-booking is reported, not clamped away.
    assert utilization_ratio(130, 120) == pytest.approx(130 / 120)


@override_settings(TIME_ZONE="America/New_York", USE_TZ=True)
def test_year_to_date_start_follows_the_local_calendar_year():
    timezone.activate("America/New_York")
    try:
        at = timezone.now()
        start = year_to_date_start(at)
        local_start = timezone.localtime(start)
        assert (local_start.month, local_start.day) == (1, 1)
        assert (local_start.hour, local_start.minute) == (0, 0)
        assert local_start.year == timezone.localtime(at).year
        # 1 January local is 05:00 UTC in New York, not midnight UTC.
        assert start.utctimetuple().tm_hour == 5
    finally:
        timezone.deactivate()


# --------------------------------------------------------------------------- #
# Page payload
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_agent_dashboard_returns_only_self_metrics(client):
    payload = metrics_data(client, agent("page-agent@example.com", branch()))
    assert [group["key"] for group in payload["groups"]] == ["myPipeline", "myWork"]
    assert payload_keys(payload) == list(SELF_METRIC_KEYS)
    assert payload["scope"] == {"level": "self", "label": "My book of business"}
    for metric in (m for g in payload["groups"] for m in g["metrics"]):
        assert metric["scopeLevel"] == MetricScope.SELF
        assert metric["drillDown"] is None


@pytest.mark.django_db
def test_branch_manager_dashboard_labels_the_scope_it_aggregates(client):
    office = branch()
    payload = metrics_data(client, branch_manager("page-branch@example.com", office))
    assert payload["scope"] == {"level": "office", "label": office.name}
    assert [group["key"] for group in payload["groups"]] == [
        "myPipeline",
        "myWork",
        "teamOperations",
        "teamOversight",
    ]


@pytest.mark.django_db
def test_user_without_a_role_gets_an_empty_metric_widget(client):
    """No entitled figures is an empty state with a next step, not a blank card."""
    widget = metrics_props(client, make_user("page-nobody@example.com"))
    assert widget["status"] == "empty"
    assert widget["data"] is None
    assert widget["emptyState"]["title"] == "No metrics for your role yet"
