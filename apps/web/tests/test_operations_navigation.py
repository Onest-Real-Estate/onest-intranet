import json
import re

import pytest
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from apps.user.models import Office, User
from apps.user.roles import (
    ADMIN,
    AGENT,
    BRANCH_MANAGER,
    REGION_MANAGER,
    ScopeType,
    role_group_name,
    seed_brokerage_roles,
)
from apps.user.services.role_assignments import (
    create_role_assignment,
    get_effective_permissions,
)
from apps.web.authorization import ROUTE_POLICIES
from apps.web.operations import (
    OPERATIONS_DESTINATIONS,
    OPERATIONS_FEATURES,
    ROLE_OPERATION_PERMISSIONS,
    operations_policy_key,
)


def user(email: str) -> User:
    return User.objects.create_user(email=email, profile_completed=True)


def branch_office() -> Office:
    office = Office.assignable_queryset().filter(kind=Office.Kind.BRANCH).first()
    assert office is not None
    return office


def permission(codename: str) -> Permission:
    return Permission.objects.get(
        content_type__app_label="web",
        content_type__model="operationspermission",
        codename=codename.removeprefix("web."),
    )


def inertia_props(response) -> dict:
    return json.loads(response.content)["props"]


@pytest.mark.django_db
def test_registry_has_exact_destinations_order_routes_and_permissions():
    assert [destination.label for destination in OPERATIONS_DESTINATIONS] == [
        "Users",
        "New Agent List",
        "Add New User",
        "Assign User Roles",
        "Agent Contracts",
        "Contract Templates",
        "Transactions",
        "Inventory",
        "Reservations",
        "Announcements",
        "Training",
        "Marketing Resources",
        "Documents",
        "Quick Access",
        "Compliance",
        "Feedback",
        "Tasks",
        "Platform Tasks",
        "Office Resources",
        "Offices",
        "IT Support",
    ]
    assert [destination.order for destination in OPERATIONS_DESTINATIONS] == [
        10,
        20,
        30,
        40,
        50,
        55,
        60,
        70,
        80,
        90,
        100,
        105,
        110,
        120,
        130,
        140,
        145,
        150,
        35,
        160,
        170,
    ]
    assert [destination.section for destination in OPERATIONS_DESTINATIONS] == [
        *("People" for _ in range(6)),
        *("Operations" for _ in range(3)),
        *("Content" for _ in range(5)),
        *("Governance & support" for _ in range(4)),
        *("Content" for _ in range(1)),
        *("Governance & support" for _ in range(2)),
    ]
    assert len({destination.key for destination in OPERATIONS_DESTINATIONS}) == 21
    assert (
        len({destination.route_name for destination in OPERATIONS_DESTINATIONS}) == 21
    )
    assert (
        len({destination.permission for destination in OPERATIONS_DESTINATIONS}) == 21
    )
    for destination in OPERATIONS_DESTINATIONS:
        assert reverse(destination.route_name) == f"/{destination.path}"
        assert destination.feature in OPERATIONS_FEATURES
        # Only destinations with a real page behind them are enabled; the
        # rest still render the placeholder.
        assert OPERATIONS_FEATURES[destination.feature] is (
            destination.route_name
            in {
                "admin_users",
                "admin_new_agents",
                "admin_quick_access",
                "admin_assign_roles",
                "admin_agent_contracts",
                "admin_office_resources",
                "admin_offices",
                "admin_announcements",
                "admin_training",
                "admin_marketing_resources",
                "admin_contract_templates",
                "operational_tasks",
                "admin_feedback",
                "admin_it_support",
                "admin_inventory",
                "admin_reservations",
                "admin_transactions",
                "admin_compliance",
                "admin_documents",
            }
        )


@pytest.mark.django_db
def test_every_destination_policy_matches_its_minimum_permission_and_scope():
    for destination in OPERATIONS_DESTINATIONS:
        policy = ROUTE_POLICIES[operations_policy_key(destination)]
        assert policy.route_names == (destination.route_name,)
        assert policy.all_permissions == (destination.permission,)
        assert policy.scope_rule == destination.scope_rule
        assert policy.access == "permission_protected"


@pytest.mark.django_db
def test_admin_group_receives_all_operations_permissions():
    seed_brokerage_roles(sync_permissions=True)
    group = Group.objects.get(name=role_group_name(ADMIN))
    actual = {
        f"{app_label}.{codename}"
        for app_label, codename in group.permissions.values_list(
            "content_type__app_label", "codename"
        )
    }
    assert actual.issuperset(ROLE_OPERATION_PERMISSIONS[ADMIN])


@pytest.mark.django_db
def test_scoped_management_role_permission_matrix():
    expected = {
        REGION_MANAGER: {
            "Users",
            "New Agent List",
            "Contract Templates",
            "Transactions",
            "Inventory",
            "Reservations",
            "Announcements",
            "Training",
            "Marketing Resources",
            "Documents",
            "Quick Access",
            "Tasks",
            "Office Resources",
            "Offices",
        },
        BRANCH_MANAGER: {
            "Users",
            "New Agent List",
            "Contract Templates",
            "Inventory",
            "Reservations",
            "Announcements",
            "Training",
            "Marketing Resources",
            "Documents",
            "Quick Access",
            "Tasks",
            "Office Resources",
            "Offices",
        },
    }
    for role, labels in expected.items():
        allowed = ROLE_OPERATION_PERMISSIONS[role]
        assert {
            destination.label
            for destination in OPERATIONS_DESTINATIONS
            if destination.permission in allowed
        } == labels
    assert "web.assign_user_roles" not in ROLE_OPERATION_PERMISSIONS[BRANCH_MANAGER]


@pytest.mark.django_db
def test_brokerage_admin_can_reach_every_registered_destination(client):
    seed_brokerage_roles(sync_permissions=True)
    actor = User.objects.create_superuser(email="system@example.com")
    admin = user("broker-admin@example.com")
    create_role_assignment(
        actor=actor,
        target_user=admin,
        role=ADMIN,
        scope_type=ScopeType.COMPANY,
    )
    assert get_effective_permissions(admin).issuperset(
        ROLE_OPERATION_PERMISSIONS[ADMIN]
    )
    client.force_login(admin)

    dashboard = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    assert {destination.feature for destination in OPERATIONS_DESTINATIONS}.issubset(
        inertia_props(dashboard)["features"]
    )

    for destination in OPERATIONS_DESTINATIONS:
        response = client.get(
            reverse(destination.route_name),
            HTTP_X_INERTIA="true",
        )
        assert response.status_code == 200, destination.route_name
        props = inertia_props(response)
        if destination.route_name == "admin_users":
            assert "users" in props
            assert "summary" in props
            assert "filterOptions" in props
            continue
        if destination.route_name == "admin_new_agents":
            assert "agents" in props
            assert "filterOptions" in props
            continue
        if destination.route_name == "admin_quick_access":
            assert "links" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_assign_roles":
            assert "users" in props
            assert "filterOptions" in props
            continue
        if destination.route_name == "admin_offices":
            assert "offices" in props
            assert "filterOptions" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_office_resources":
            assert "resources" in props
            assert "filterOptions" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_inventory":
            assert "items" in props
            assert "filterOptions" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_reservations":
            assert "reservations" in props
            assert "filterOptions" in props
            assert "can" in props
            continue
        if destination.route_name == "admin_announcements":
            assert "announcements" in props
            assert "filterOptions" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_training":
            assert "trainings" in props
            assert "filterOptions" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_marketing_resources":
            assert "assets" in props
            assert "filterOptions" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_agent_contracts":
            assert "contracts" in props
            assert "capabilities" in props
            assert "statusOptions" in props
            continue
        if destination.route_name == "admin_contract_templates":
            assert "templates" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_feedback":
            assert "tickets" in props
            assert "filterOptions" in props
            assert "summary" in props
            continue
        if destination.route_name == "operational_tasks":
            assert "tasks" in props
            assert "board" in props
            assert "filterOptions" in props
            assert "summary" in props
            continue
        if destination.route_name == "admin_it_support":
            assert "tickets" in props
            assert "metrics" in props
            assert "options" in props
            assert "offices" in props
            continue
        if destination.route_name == "admin_compliance":
            assert "policies" in props
            assert "filterOptions" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_documents":
            assert "documents" in props
            assert "filterOptions" in props
            assert "capabilities" in props
            continue
        if destination.route_name == "admin_transactions":
            assert "items" in props
            assert "capabilities" in props
            continue
        assert "title" in props, (
            f"{destination.route_name} missing title; keys={sorted(props)}"
        )
        assert props["title"] == destination.label
        assert props["administrative"] is True
        assert props["scope"] == {
            "level": "brokerage",
            "label": "Brokerage-wide",
        }
        assert "count" not in props
        assert "records" not in props


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route_name", "permission_name"),
    [
        ("admin_add_user", "web.add_users"),
        ("admin_assign_roles", "web.assign_user_roles"),
        ("admin_compliance", "web.view_compliance"),
        ("admin_platform_tasks", "web.view_platform_tasks"),
        ("admin_it_support", "web.view_it_support"),
    ],
)
def test_high_risk_direct_routes_require_their_own_permission(
    client,
    route_name,
    permission_name,
):
    account = user(f"{route_name}@example.com")
    account.user_permissions.add(permission("web.view_users"))
    client.force_login(account)

    denied = client.get(reverse(route_name), HTTP_X_INERTIA="true")
    assert denied.status_code == 403
    assert json.loads(denied.content)["component"] == "PermissionDenied"

    account.user_permissions.add(permission(permission_name))
    allowed = client.get(reverse(route_name), HTTP_X_INERTIA="true")
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_feature_availability_never_grants_permission(client, monkeypatch):
    account = user("no-permission@example.com")
    client.force_login(account)
    monkeypatch.setitem(OPERATIONS_FEATURES, "admin-compliance", True)

    response = client.get(reverse("admin_compliance"), HTTP_X_INERTIA="true")

    assert response.status_code == 403
    assert b"Compliance" not in response.content


@pytest.mark.django_db
def test_permission_revocation_takes_effect_on_the_next_nested_visit(client):
    account = user("revoked@example.com")
    granted = permission("web.view_users")
    account.user_permissions.add(granted)
    client.force_login(account)
    assert client.get(reverse("admin_users")).status_code == 200

    account.user_permissions.remove(granted)
    response = client.get(reverse("admin_users"), HTTP_X_INERTIA="true")

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("persona", "role", "scope_type", "permission_name", "route_name"),
    [
        (
            "regional-coordinator",
            REGION_MANAGER,
            ScopeType.REGION,
            "web.view_transactions",
            "admin_transactions",
        ),
        (
            "branch-admin",
            BRANCH_MANAGER,
            ScopeType.OFFICE,
            "web.view_users",
            "admin_users",
        ),
        (
            # Compliance has a real workspace now, so the specialty persona is
            # checked against a destination that still renders the placeholder.
            # Its scoped workspace access is covered by
            # ``apps/compliance/tests/``.
            "compliance",
            AGENT,
            ScopeType.OFFICE,
            "web.view_platform_tasks",
            "admin_platform_tasks",
        ),
        (
            "accountant",
            AGENT,
            ScopeType.OFFICE,
            "web.view_transactions",
            "admin_transactions",
        ),
        (
            # Announcements has a real workspace now, so the marketing persona
            # is checked against a destination that still renders the
            # placeholder. Its scoped workspace access is covered by
            # ``apps/announcements/tests/test_administration.py``.
            "marketing",
            AGENT,
            ScopeType.OFFICE,
            "web.add_users",
            "admin_add_user",
        ),
        (
            # Documents has a real workspace now, so the specialty persona is
            # checked against a destination that still renders the
            # placeholder. Scoped document access is covered by
            # ``apps/documents/tests/test_administration.py``.
            "it-support",
            AGENT,
            ScopeType.OFFICE,
            "web.add_users",
            "admin_add_user",
        ),
    ],
)
def test_scoped_and_specialty_personas_reach_only_authorized_scope(
    client,
    persona,
    role,
    scope_type,
    permission_name,
    route_name,
):
    actor = User.objects.create_superuser(email=f"system-{persona}@example.com")
    office = branch_office()
    scope_office = office.region if scope_type == ScopeType.REGION else office
    assert scope_office is not None
    account = user(f"{persona}@example.com")
    account.office = office
    account.save(update_fields=["office"])
    create_role_assignment(
        actor=actor,
        target_user=account,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
    )
    account.user_permissions.add(permission(permission_name))
    client.force_login(account)

    response = client.get(reverse(route_name), HTTP_X_INERTIA="true")

    assert response.status_code == 200
    props = inertia_props(response)
    scope = props["scope"]
    expected_level = "region" if scope_type == ScopeType.REGION else "office"
    assert scope["level"] == expected_level
    assert scope["label"] == scope_office.name
    assert "members" not in props
    if route_name == "admin_transactions":
        # Live list: confirm the shell is the scoped list, not Coming Soon.
        assert "items" in props
        assert "capabilities" in props
    else:
        assert "items" not in props


@pytest.mark.django_db
def test_platform_tasks_and_it_support_return_no_internal_operational_data(client):
    account = user("support@example.com")
    account.user_permissions.add(
        permission("web.view_platform_tasks"),
        permission("web.view_it_support"),
    )
    client.force_login(account)

    for route_name in ("admin_platform_tasks", "admin_it_support"):
        props = inertia_props(client.get(reverse(route_name), HTTP_X_INERTIA="true"))
        serialized = json.dumps(props).lower()
        # Word boundaries: CSRF/request tokens can contain "log" as a substring.
        for forbidden in ("secret", "traceback", "worker", "log", "queue"):
            assert re.search(rf"\b{re.escape(forbidden)}\b", serialized) is None
