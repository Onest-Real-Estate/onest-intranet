"""Quick Access: model constraints, audience resolution, grant boundary, and audit.

The dashboard panel is administered data. The properties worth pinning are the
ones that would let somebody see a tool they should not, reach a destination
nobody reviewed, or keep seeing a link after it was retired.
"""

import json

import pytest
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.user.models import Office
from apps.user.roles import ADMIN, BRANCH_MANAGER, MARKETING_TEAM, REALTOR, ScopeType
from apps.web.dashboard import WIDGET_BY_KEY, build_context, widget_payload
from apps.web.dashboard.envelope import WidgetStatus
from apps.web.models import (
    QuickAccessLink,
    QuickAccessLinkOfficeAudience,
    QuickAccessLinkRoleAudience,
)
from apps.web.quick_access.administration import (
    BroadExposureNotAcknowledged,
    StaleQuickAccessVersion,
    can_manage,
    create_link,
    grant_scope,
    link_version,
    manageable_link_queryset,
    reorder_links,
    set_link_state,
    update_link,
)
from apps.web.quick_access.catalog import ICON_KEYS, internal_destination_keys
from apps.web.quick_access.destinations import validate_destination
from apps.web.quick_access.resolution import (
    configuration_version,
    explain_visibility,
    invalidate_configuration_cache,
    visible_links_for,
)
from apps.web.tests.test_dashboard_metrics import (
    agent,
    assign,
    branch,
    branch_manager,
    company_admin,
    inertia_props,
    make_user,
    other_region_office,
    region_manager,
    region_of,
)

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _clear_configuration_cache():
    cache.clear()
    yield
    cache.clear()


def make_link(
    stable_key: str,
    *,
    name: str | None = None,
    company_wide: bool = False,
    offices: tuple[Office, ...] = (),
    roles: tuple[str, ...] = (),
    sort_order: int = 0,
    **fields,
) -> QuickAccessLink:
    link = QuickAccessLink.objects.create(
        stable_key=stable_key,
        name=name or stable_key.title(),
        destination_type=fields.pop("destination_type", "external_url"),
        destination_value=fields.pop("destination_value", "https://example.com/tool"),
        icon=fields.pop("icon", "app-window"),
        sort_order=sort_order,
        company_wide=company_wide,
        owner_scope="company" if company_wide else "scoped",
        **fields,
    )
    for office in offices:
        QuickAccessLinkOfficeAudience.objects.create(link=link, office=office)
    for role in roles:
        QuickAccessLinkRoleAudience.objects.create(link=link, role_code=role)
    return link


def clear_seeded_links() -> None:
    """Drop the migration's seed rows so a test owns the whole panel."""
    QuickAccessLink.objects.all().delete()


# --------------------------------------------------------------------------- #
# Destinations
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "//example.com",
        "javascript:alert(1)",
        "data:text/html,<script>",
        "https://",
        "ftp://example.com",
    ],
)
def test_only_https_external_destinations_are_accepted(value):
    with pytest.raises(ValidationError):
        validate_destination("external_url", value)


def test_an_external_destination_may_not_carry_credentials():
    with pytest.raises(ValidationError):
        validate_destination("external_url", "https://user:pw@example.com")
    with pytest.raises(ValidationError):
        validate_destination("external_url", "https://example.com/?token=abc123")
    # A parameter that merely *contains* a credential word is fine.
    assert validate_destination("external_url", "https://example.com/?tokenized=1")


def test_an_internal_destination_must_be_allowlisted():
    with pytest.raises(ValidationError):
        validate_destination("internal_route", "/operations/users")
    key = sorted(internal_destination_keys())[0]
    assert validate_destination("internal_route", key) == key


def test_an_unknown_destination_type_fails_closed():
    with pytest.raises(ValidationError):
        validate_destination("anything_else", "https://example.com")


def test_an_internal_link_renders_a_reversed_path():
    link = make_link(
        "hub-training",
        destination_type="internal_route",
        destination_value="hub:training-learning",
    )
    assert link.href() == reverse("coming_soon", args=["training-learning"])
    assert link.is_external is False


def test_a_destination_key_that_left_the_allowlist_renders_empty():
    link = make_link(
        "retired",
        destination_type="internal_route",
        destination_value="hub:training-learning",
    )
    QuickAccessLink.objects.filter(pk=link.pk).update(
        destination_value="hub:not-a-section"
    )
    assert QuickAccessLink.objects.get(pk=link.pk).href() == ""


# --------------------------------------------------------------------------- #
# Model constraints
# --------------------------------------------------------------------------- #


def test_a_duplicate_stable_key_is_rejected_by_the_database():
    make_link("duplicate-me")
    with pytest.raises(IntegrityError), transaction.atomic():
        QuickAccessLink.objects.create(
            stable_key="duplicate-me",
            name="Second",
            destination_value="https://example.com",
        )


def test_a_stable_key_cannot_be_changed_after_creation():
    link = make_link("permanent")
    link.stable_key = "renamed"
    with pytest.raises(ValidationError) as exc:
        link.full_clean()
    assert "stable_key" in exc.value.message_dict


def test_an_unapproved_icon_is_rejected():
    link = make_link("bad-icon")
    link.icon = "https://example.com/logo.png"
    with pytest.raises(ValidationError) as exc:
        link.full_clean()
    assert "icon" in exc.value.message_dict
    assert "app-window" in ICON_KEYS


def test_a_publish_window_must_end_after_it_starts():
    from django.utils import timezone

    now = timezone.now()
    link = make_link("window")
    link.publish_start_at = now
    link.publish_end_at = now
    with pytest.raises(ValidationError) as exc:
        link.full_clean()
    assert "publish_end_at" in exc.value.message_dict


def test_sort_order_may_repeat_so_reordering_is_never_fragile():
    """Positions are not unique — ties break by name, deterministically."""
    clear_seeded_links()
    make_link("bravo", name="Bravo", sort_order=10, company_wide=True)
    make_link("alpha", name="Alpha", sort_order=10, company_wide=True)
    keys = list(
        QuickAccessLink.objects.order_by("sort_order", "name", "pk").values_list(
            "stable_key", flat=True
        )
    )
    assert keys == ["alpha", "bravo"]


def test_a_role_audience_row_is_unique_per_link():
    link = make_link("roles", roles=(REALTOR,))
    with pytest.raises(IntegrityError), transaction.atomic():
        QuickAccessLinkRoleAudience.objects.create(link=link, role_code=REALTOR)


# --------------------------------------------------------------------------- #
# Audience resolution
# --------------------------------------------------------------------------- #


def test_a_company_wide_link_reaches_every_office():
    clear_seeded_links()
    home = branch(0)
    away = other_region_office(home)
    make_link("everyone", company_wide=True)
    for office in (home, away):
        reader = agent(f"reader-{office.pk}@example.com", office=office)
        assert [link.stable_key for link in visible_links_for(reader)] == ["everyone"]


def test_an_office_link_reaches_only_that_office():
    clear_seeded_links()
    home = branch(0)
    away = other_region_office(home)
    make_link("home-only", offices=(home,))

    inside = agent("inside@example.com", office=home)
    outside = agent("outside@example.com", office=away)
    assert [link.stable_key for link in visible_links_for(inside)] == ["home-only"]
    assert list(visible_links_for(outside)) == []


def test_a_region_audience_covers_the_offices_beneath_it():
    clear_seeded_links()
    home = branch(0)
    make_link("region-wide", offices=(region_of(home),))
    reader = agent("under-region@example.com", office=home)
    assert [link.stable_key for link in visible_links_for(reader)] == ["region-wide"]


def test_an_ancestor_row_without_descendants_covers_only_itself():
    clear_seeded_links()
    home = branch(0)
    link = make_link("exact-node", offices=(region_of(home),))
    link.office_audiences.update(include_descendants=False)
    reader = agent("under-region@example.com", office=home)
    assert list(visible_links_for(reader)) == []


def test_a_role_audience_narrows_within_the_office_audience():
    clear_seeded_links()
    home = branch(0)
    make_link("managers-only", offices=(home,), roles=(BRANCH_MANAGER,))

    realtor = agent("realtor@example.com", office=home)
    manager = branch_manager("manager@example.com", home)
    assert list(visible_links_for(realtor)) == []
    assert [link.stable_key for link in visible_links_for(manager)] == ["managers-only"]


def test_an_agent_audience_is_just_the_realtor_role():
    clear_seeded_links()
    home = branch(0)
    make_link("agents-only", offices=(home,), roles=(REALTOR,))
    realtor = agent("agent-audience@example.com", office=home)
    assert [link.stable_key for link in visible_links_for(realtor)] == ["agents-only"]


def test_a_reader_without_an_office_sees_only_company_wide_links():
    clear_seeded_links()
    home = branch(0)
    make_link("office-scoped", offices=(home,))
    make_link("brokerage", company_wide=True)
    homeless = make_user("no-office@example.com")
    assert [link.stable_key for link in visible_links_for(homeless)] == ["brokerage"]


def test_inactive_archived_and_unpublished_links_stay_hidden():
    from datetime import timedelta

    from django.utils import timezone

    clear_seeded_links()
    now = timezone.now()
    make_link("live", company_wide=True, sort_order=10)
    make_link("inactive", company_wide=True, is_active=False, sort_order=20)
    make_link("archived", company_wide=True, is_archived=True, sort_order=30)
    make_link(
        "future",
        company_wide=True,
        publish_start_at=now + timedelta(days=1),
        sort_order=40,
    )
    make_link(
        "expired",
        company_wide=True,
        publish_end_at=now - timedelta(days=1),
        sort_order=50,
    )
    reader = agent("lifecycle@example.com", office=branch(0))
    assert [link.stable_key for link in visible_links_for(reader, at=now)] == ["live"]


def test_a_link_appears_once_however_many_audience_rows_it_has():
    """The EXISTS form is what keeps a four-office link from rendering four times."""
    clear_seeded_links()
    home = branch(0)
    make_link("many-rows", offices=(home, region_of(home)), roles=(REALTOR, ADMIN))
    reader = agent("dedupe@example.com", office=home)
    assert [link.stable_key for link in visible_links_for(reader)] == ["many-rows"]


def test_the_preview_explains_every_reason_a_link_is_hidden():
    clear_seeded_links()
    home = branch(0)
    away = other_region_office(home)
    link = make_link("hidden", offices=(away,), roles=(ADMIN,), is_active=False)
    reasons = explain_visibility(link, role_keys=[REALTOR], office=home)
    assert len(reasons) == 3, reasons
    assert any("Deactivated" in reason for reason in reasons)
    assert any("role audience" in reason for reason in reasons)
    assert any("office audience" in reason for reason in reasons)


# --------------------------------------------------------------------------- #
# Grant boundary
# --------------------------------------------------------------------------- #


def test_an_office_admin_may_not_publish_company_wide():
    home = branch(0)
    manager = branch_manager("scoped-admin@example.com", home)
    with pytest.raises(ValidationError) as exc:
        create_link(
            actor=manager,
            cleaned={
                "stable_key": "too-wide",
                "name": "Too wide",
                "destination_type": "external_url",
                "destination_value": "https://example.com",
                "icon": "app-window",
                "sort_order": 10,
            },
            role_codes=[],
            office_ids=[],
            company_wide=True,
            acknowledged=True,
        )
    assert "company_wide" in exc.value.message_dict


def test_an_office_admin_may_not_target_an_office_outside_their_scope():
    home = branch(0)
    away = other_region_office(home)
    manager = branch_manager("scoped-target@example.com", home)
    with pytest.raises(ValidationError) as exc:
        create_link(
            actor=manager,
            cleaned={
                "stable_key": "elsewhere",
                "name": "Elsewhere",
                "destination_type": "external_url",
                "destination_value": "https://example.com",
                "icon": "app-window",
                "sort_order": 10,
            },
            role_codes=[],
            office_ids=[away.pk],
            company_wide=False,
            acknowledged=True,
        )
    assert "offices" in exc.value.message_dict


def test_a_region_admin_may_target_offices_beneath_their_region():
    home = branch(0)
    manager = region_manager("regional@example.com", region_of(home))
    assert grant_scope(manager).covers(home.pk)
    link = create_link(
        actor=manager,
        cleaned={
            "stable_key": "region-tool",
            "name": "Region tool",
            "destination_type": "external_url",
            "destination_value": "https://example.com",
            "icon": "app-window",
            "sort_order": 10,
        },
        role_codes=[],
        office_ids=[home.pk],
        company_wide=False,
        acknowledged=True,
    )
    assert link.owner_scope == QuickAccessLink.OwnerScope.SCOPED


def test_an_office_admin_cannot_edit_a_company_owned_definition():
    home = branch(0)
    manager = branch_manager("no-company-edit@example.com", home)
    company_link = make_link("company-tool", company_wide=True)
    assert can_manage(manager, company_link) is False
    assert company_link.pk not in set(
        manageable_link_queryset(manager).values_list("pk", flat=True)
    )
    with pytest.raises(PermissionDenied):
        set_link_state(actor=manager, link=company_link, action="deactivate")


def test_an_office_admin_cannot_edit_a_link_reaching_beyond_their_scope():
    home = branch(0)
    away = other_region_office(home)
    manager = branch_manager("partial-scope@example.com", home)
    link = make_link("shared-tool", offices=(home, away))
    assert can_manage(manager, link) is False


def test_a_user_without_the_permission_manages_nothing():
    reader = agent("no-grant@example.com", office=branch(0))
    assert list(manageable_link_queryset(reader)) == []


def test_a_company_admin_manages_company_owned_links():
    admin = company_admin("brokerage@example.com")
    link = make_link("company-tool", company_wide=True)
    assert can_manage(admin, link) is True


def test_a_marketing_manager_may_scope_a_link_but_not_publish_brokerage_wide():
    """The two grants are separate on purpose: one is strictly wider."""
    home = branch(0)
    marketer = make_user("marketing@example.com", office=home)
    assign(marketer, MARKETING_TEAM, ScopeType.COMPANY)
    assert grant_scope(marketer).company_wide is True
    with pytest.raises(ValidationError):
        create_link(
            actor=marketer,
            cleaned={
                "stable_key": "marketing-wide",
                "name": "Marketing wide",
                "destination_type": "external_url",
                "destination_value": "https://example.com",
                "icon": "app-window",
                "sort_order": 10,
            },
            role_codes=[],
            office_ids=[],
            company_wide=True,
            acknowledged=True,
        )


# --------------------------------------------------------------------------- #
# Confirmation of widening changes
# --------------------------------------------------------------------------- #


def _create(actor, key, *, offices, roles=(), acknowledged=True):
    return create_link(
        actor=actor,
        cleaned={
            "stable_key": key,
            "name": key.title(),
            "destination_type": "external_url",
            "destination_value": "https://example.com/one",
            "icon": "app-window",
            "sort_order": 10,
        },
        role_codes=list(roles),
        office_ids=[office.pk for office in offices],
        company_wide=False,
        acknowledged=acknowledged,
    )


def test_creating_a_link_without_acknowledgement_is_refused():
    home = branch(0)
    manager = branch_manager("confirm-create@example.com", home)
    with pytest.raises(BroadExposureNotAcknowledged):
        _create(manager, "unconfirmed", offices=(home,), acknowledged=False)
    assert not QuickAccessLink.objects.filter(stable_key="unconfirmed").exists()


def test_widening_the_audience_without_acknowledgement_is_refused():
    home = branch(0)
    sibling = branch(1)
    manager = region_manager("confirm-widen@example.com", region_of(home))
    link = _create(manager, "widening", offices=(home,))

    with pytest.raises(BroadExposureNotAcknowledged) as exc:
        update_link(
            actor=manager,
            link=link,
            cleaned={},
            role_codes=[],
            office_ids=[home.pk, sibling.pk],
            company_wide=False,
            expected_version=link_version(link),
            acknowledged=False,
        )
    assert any(change["label"] == "Offices added" for change in exc.value.changes)
    link.refresh_from_db()
    assert link.office_audiences.count() == 1


def test_narrowing_the_audience_needs_no_confirmation():
    home = branch(0)
    sibling = branch(1)
    manager = region_manager("narrowing@example.com", region_of(home))
    link = _create(manager, "narrowing", offices=(home, sibling))

    update_link(
        actor=manager,
        link=link,
        cleaned={},
        role_codes=[],
        office_ids=[home.pk],
        company_wide=False,
        expected_version=link_version(link),
        acknowledged=False,
    )
    link.refresh_from_db()
    assert link.office_audiences.count() == 1


def test_changing_the_destination_needs_confirmation():
    home = branch(0)
    manager = branch_manager("confirm-destination@example.com", home)
    link = _create(manager, "redirect", offices=(home,))
    with pytest.raises(BroadExposureNotAcknowledged) as exc:
        update_link(
            actor=manager,
            link=link,
            cleaned={"destination_value": "https://elsewhere.example.com"},
            role_codes=[],
            office_ids=[home.pk],
            company_wide=False,
            expected_version=link_version(link),
            acknowledged=False,
        )
    assert any(change["label"] == "Destination" for change in exc.value.changes)


def test_a_stale_version_is_a_conflict_not_a_silent_overwrite():
    home = branch(0)
    manager = branch_manager("stale@example.com", home)
    link = _create(manager, "concurrent", offices=(home,))
    with pytest.raises(StaleQuickAccessVersion):
        update_link(
            actor=manager,
            link=link,
            cleaned={"name": "Renamed"},
            role_codes=[],
            office_ids=[home.pk],
            company_wide=False,
            expected_version="1999-01-01T00:00:00+00:00",
            acknowledged=True,
        )


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


def test_reordering_reuses_the_positions_the_links_already_held():
    clear_seeded_links()
    home = branch(0)
    admin = company_admin("orderer@example.com")
    first = make_link("first", offices=(home,), sort_order=10)
    second = make_link("second", offices=(home,), sort_order=20)
    third = make_link("third", offices=(home,), sort_order=30)

    reorder_links(actor=admin, link_ids=[third.pk, first.pk, second.pk])
    assert list(
        QuickAccessLink.objects.order_by("sort_order").values_list(
            "stable_key", "sort_order"
        )
    ) == [("third", 10), ("first", 20), ("second", 30)]


def test_reordering_never_moves_a_link_the_actor_does_not_manage():
    clear_seeded_links()
    home = branch(0)
    manager = branch_manager("scoped-order@example.com", home)
    company = make_link("company", company_wide=True, sort_order=20)
    mine_a = make_link("mine-a", offices=(home,), sort_order=10)
    mine_b = make_link("mine-b", offices=(home,), sort_order=30)

    reorder_links(actor=manager, link_ids=[mine_b.pk, mine_a.pk])
    company.refresh_from_db()
    assert company.sort_order == 20
    assert list(
        QuickAccessLink.objects.filter(pk__in=[mine_a.pk, mine_b.pk])
        .order_by("sort_order")
        .values_list("stable_key", flat=True)
    ) == ["mine-b", "mine-a"]


def test_reordering_a_link_outside_scope_is_denied():
    clear_seeded_links()
    home = branch(0)
    manager = branch_manager("denied-order@example.com", home)
    mine = make_link("mine", offices=(home,), sort_order=10)
    company = make_link("company", company_wide=True, sort_order=20)
    with pytest.raises(PermissionDenied):
        reorder_links(actor=manager, link_ids=[company.pk, mine.pk])
    company.refresh_from_db()
    assert company.sort_order == 20


def test_tied_positions_are_separated_rather_than_left_ambiguous():
    clear_seeded_links()
    home = branch(0)
    admin = company_admin("tied@example.com")
    left = make_link("left", offices=(home,), sort_order=10)
    right = make_link("right", offices=(home,), sort_order=10)
    reorder_links(actor=admin, link_ids=[right.pk, left.pk])
    left.refresh_from_db()
    right.refresh_from_db()
    assert right.sort_order < left.sort_order


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #


def test_archiving_keeps_the_record_and_takes_it_off_the_dashboard():
    clear_seeded_links()
    home = branch(0)
    admin = company_admin("archiver@example.com")
    link = make_link("retired", offices=(home,))
    set_link_state(actor=admin, link=link, action="archive")
    link.refresh_from_db()

    assert QuickAccessLink.objects.filter(pk=link.pk).exists()
    assert link.is_archived is True
    assert link.archived_at is not None
    reader = agent("after-archive@example.com", office=home)
    assert list(visible_links_for(reader)) == []


# --------------------------------------------------------------------------- #
# Cache invalidation
# --------------------------------------------------------------------------- #


def test_a_save_changes_the_configuration_stamp():
    before = configuration_version()
    make_link("new-tool", company_wide=True)
    invalidate_configuration_cache()
    assert configuration_version() != before


def test_an_audience_change_alone_changes_the_stamp():
    home = branch(0)
    link = make_link("audience-stamp", offices=(home,))
    invalidate_configuration_cache()
    before = configuration_version()
    QuickAccessLinkRoleAudience.objects.create(link=link, role_code=REALTOR)
    invalidate_configuration_cache()
    assert configuration_version() != before


def test_a_dashboard_reader_sees_a_change_without_waiting_for_the_ttl():
    clear_seeded_links()
    home = branch(0)
    reader = agent("cache-reader@example.com", office=home)
    make_link("before-save", company_wide=True)

    definition = WIDGET_BY_KEY["quick_access"]
    first = widget_payload(definition, build_context(reader))
    assert [tool["id"] for tool in first["data"]] == ["before-save"]

    admin = company_admin("cache-admin@example.com")
    link = QuickAccessLink.objects.get(stable_key="before-save")
    set_link_state(actor=admin, link=link, action="deactivate")
    invalidate_configuration_cache()

    second = widget_payload(definition, build_context(reader))
    assert second["status"] == WidgetStatus.EMPTY


def test_two_readers_in_different_offices_get_different_panels():
    clear_seeded_links()
    home = branch(0)
    away = other_region_office(home)
    make_link("home-tool", offices=(home,))
    make_link("away-tool", offices=(away,))

    definition = WIDGET_BY_KEY["quick_access"]
    here = agent("here@example.com", office=home)
    there = agent("there@example.com", office=away)
    assert [
        tool["id"] for tool in widget_payload(definition, build_context(here))["data"]
    ] == ["home-tool"]
    assert [
        tool["id"] for tool in widget_payload(definition, build_context(there))["data"]
    ] == ["away-tool"]


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


def events(action: str):
    return AuditEvent.objects.filter(action=action)


def test_creating_a_link_records_an_audit_event_with_the_new_values():
    home = branch(0)
    manager = branch_manager("audited-create@example.com", home)
    _create(manager, "audited", offices=(home,))
    event = events("web.quick_access.created").get()
    assert event.target_label == "audited"
    assert event.after["stable_key"] == "audited"
    assert event.after["audience"]["offices"] == [home.stable_key]


def test_an_audience_change_records_before_and_after():
    home = branch(0)
    manager = branch_manager("audited-audience@example.com", home)
    link = _create(manager, "audience-audit", offices=(home,))
    update_link(
        actor=manager,
        link=link,
        cleaned={},
        role_codes=[REALTOR],
        office_ids=[home.pk],
        company_wide=False,
        expected_version=link_version(link),
        acknowledged=True,
    )
    event = events("web.quick_access.audience_changed").get()
    assert event.before["audience"]["roles"] == []
    assert event.after["audience"]["roles"] == [REALTOR]


def test_an_activation_change_is_audited_as_its_own_action():
    home = branch(0)
    admin = company_admin("audited-state@example.com")
    link = make_link("state-audit", offices=(home,))
    set_link_state(actor=admin, link=link, action="deactivate")
    event = events("web.quick_access.activation_changed").get()
    assert event.before["is_active"] is True
    assert event.after["is_active"] is False


def test_a_reorder_is_audited_with_the_old_and_new_sequence():
    clear_seeded_links()
    home = branch(0)
    admin = company_admin("audited-order@example.com")
    first = make_link("one", offices=(home,), sort_order=10)
    second = make_link("two", offices=(home,), sort_order=20)
    reorder_links(actor=admin, link_ids=[second.pk, first.pk])
    event = events("web.quick_access.reordered").get()
    assert event.before["order"] == ["one", "two"]
    assert event.after["order"] == ["two", "one"]


def test_a_denied_management_attempt_is_audited():
    home = branch(0)
    manager = branch_manager("denied-audit@example.com", home)
    company_link = make_link("company-only", company_wide=True)
    with pytest.raises(PermissionDenied):
        set_link_state(actor=manager, link=company_link, action="archive")
    event = events("security.quick_access.denied").get()
    assert event.outcome == AuditEvent.Outcome.DENIED


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


def test_an_agent_cannot_reach_the_management_pages(client):
    reader = agent("no-access@example.com", office=branch(0))
    client.force_login(reader)
    for name, args in (
        ("admin_quick_access", ()),
        ("quick_access_new", ()),
    ):
        assert client.get(reverse(name, args=args)).status_code == 403


def test_an_agent_cannot_mutate_a_link(client):
    home = branch(0)
    link = make_link("guarded", offices=(home,))
    reader = agent("no-mutate@example.com", office=home)
    client.force_login(reader)
    response = client.post(
        reverse("quick_access_state", args=[link.pk]), {"action": "archive"}
    )
    assert response.status_code == 403
    link.refresh_from_db()
    assert link.is_archived is False


def test_a_link_outside_scope_is_a_404_not_a_403(client):
    """Confirming that an id exists is itself a disclosure across a boundary."""
    home = branch(0)
    manager = branch_manager("scoped-404@example.com", home)
    company_link = make_link("hidden-company", company_wide=True)
    client.force_login(manager)
    assert (
        client.get(reverse("quick_access_edit", args=[company_link.pk])).status_code
        == 404
    )


def test_the_index_lists_only_manageable_links(client):
    clear_seeded_links()
    home = branch(0)
    make_link("mine", offices=(home,))
    make_link("theirs", company_wide=True)
    manager = branch_manager("index@example.com", home)
    client.force_login(manager)

    response = client.get(reverse("admin_quick_access"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    keys = [row["stableKey"] for row in inertia_props(response)["links"]["items"]]
    assert keys == ["mine"]


def test_the_preview_refuses_an_office_outside_the_actor_scope(client):
    home = branch(0)
    away = other_region_office(home)
    manager = branch_manager("preview-scope@example.com", home)
    client.force_login(manager)
    response = client.get(
        reverse("admin_quick_access"),
        {"previewRole": REALTOR, "previewOffice": str(away.pk)},
        HTTP_X_INERTIA="true",
    )
    assert inertia_props(response)["preview"]["outOfScope"] is True


def test_the_preview_answers_for_a_role_and_office_in_scope(client):
    clear_seeded_links()
    home = branch(0)
    make_link("for-realtors", offices=(home,), roles=(REALTOR,))
    make_link("for-managers", offices=(home,), roles=(BRANCH_MANAGER,))
    manager = branch_manager("preview@example.com", home)
    client.force_login(manager)

    response = client.get(
        reverse("admin_quick_access"),
        {"previewRole": REALTOR, "previewOffice": str(home.pk)},
        HTTP_X_INERTIA="true",
    )
    preview = inertia_props(response)["preview"]
    visible = {row["stableKey"]: row["visible"] for row in preview["links"]}
    assert visible == {"for-realtors": True, "for-managers": False}


def test_an_invalid_destination_is_rejected_by_the_server(client):
    home = branch(0)
    manager = branch_manager("bad-post@example.com", home)
    client.force_login(manager)
    response = client.post(
        reverse("quick_access_create"),
        {
            "stable_key": "insecure",
            "name": "Insecure",
            "destination_type": "external_url",
            "destination_value": "http://example.com",
            "icon": "app-window",
            "sort_order": "10",
            "offices": [str(home.pk)],
            "acknowledge_exposure": "on",
        },
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    assert not QuickAccessLink.objects.filter(stable_key="insecure").exists()
    body = json.loads(response.content)
    assert "destination_value" in body["props"]["errors"]["fields"]


def test_a_duplicate_stable_key_is_rejected_by_the_server(client):
    home = branch(0)
    make_link("taken", offices=(home,))
    manager = branch_manager("dup-post@example.com", home)
    client.force_login(manager)
    response = client.post(
        reverse("quick_access_create"),
        {
            "stable_key": "taken",
            "name": "Taken",
            "destination_type": "external_url",
            "destination_value": "https://example.com",
            "icon": "app-window",
            "sort_order": "10",
            "offices": [str(home.pk)],
            "acknowledge_exposure": "on",
        },
    )
    assert response.status_code == 422
    assert QuickAccessLink.objects.filter(stable_key="taken").count() == 1


def test_a_full_create_reaches_the_dashboard(client):
    clear_seeded_links()
    home = branch(0)
    manager = branch_manager("end-to-end@example.com", home)
    client.force_login(manager)
    response = client.post(
        reverse("quick_access_create"),
        {
            "stable_key": "new-crm",
            "name": "New CRM",
            "description": "Where leads live",
            "destination_type": "external_url",
            "destination_value": "https://crm.example.com",
            "icon": "contact",
            "sort_order": "10",
            "is_active": "on",
            "offices": [str(home.pk)],
            "roles": [REALTOR],
            "acknowledge_exposure": "on",
        },
    )
    assert response.status_code == 302

    reader = agent("crm-reader@example.com", office=home)
    payload = widget_payload(WIDGET_BY_KEY["quick_access"], build_context(reader))
    assert [tool["id"] for tool in payload["data"]] == ["new-crm"]
    assert payload["data"][0]["icon"] == "contact"
    assert payload["data"][0]["external"] is True


# --------------------------------------------------------------------------- #
# The icon allowlist is a two-sided contract
# --------------------------------------------------------------------------- #


def test_every_approved_icon_has_a_mark_in_the_bundle():
    """An approved key with no component renders as a generic window instead.

    The fallback keeps the panel from breaking, which is exactly why the
    mismatch needs a test: nothing at runtime would report it.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "lib"
        / "quick-access-icons.ts"
    ).read_text()
    # Keys that are valid JS identifiers appear unquoted; the rest are quoted.
    missing = [
        key
        for key in sorted(ICON_KEYS)
        if f'"{key}"' not in source and f"\n  {key}:" not in source
    ]
    assert missing == [], missing


def test_the_form_page_offers_only_offices_inside_the_actor_scope(client):
    home = branch(0)
    away = other_region_office(home)
    manager = branch_manager("form-scope@example.com", home)
    client.force_login(manager)

    response = client.get(reverse("quick_access_new"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    props = inertia_props(response)
    offered = {option["value"] for option in props["officeOptions"]}
    assert home.pk in offered
    assert away.pk not in offered
    assert props["capabilities"]["companyWide"] is False


def test_the_edit_page_echoes_a_version_for_optimistic_concurrency(client):
    home = branch(0)
    link = make_link("versioned", offices=(home,))
    manager = branch_manager("form-version@example.com", home)
    client.force_login(manager)

    response = client.get(
        reverse("quick_access_edit", args=[link.pk]), HTTP_X_INERTIA="true"
    )
    assert response.status_code == 200
    assert inertia_props(response)["link"]["version"] == link_version(link)


def test_the_index_cost_does_not_grow_with_the_number_of_rows():
    """A per-row authority check would put the office tree on an N+1."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.web.quick_access.payloads import index_props

    clear_seeded_links()
    home = branch(0)
    manager = branch_manager("query-count@example.com", home)

    def cost() -> int:
        with CaptureQueriesContext(connection) as captured:
            props = index_props(manager)
        assert props["links"]["items"]
        return len(captured.captured_queries)

    make_link("tool-0", offices=(home,), sort_order=0)
    make_link("tool-1", offices=(home,), sort_order=10)
    two_rows = cost()
    for index in range(2, 8):
        make_link(f"tool-{index}", offices=(home,), sort_order=index * 10)
    eight_rows = cost()

    assert eight_rows == two_rows, (two_rows, eight_rows)


def test_a_link_naming_no_office_is_nobody_else_to_manage():
    """ "Every office it names is in scope" must not be vacuously true."""
    home = branch(0)
    orphan = make_link("orphan")
    manager = branch_manager("orphan-scope@example.com", home)
    assert can_manage(manager, orphan) is False
    assert orphan.pk not in set(
        manageable_link_queryset(manager).values_list("pk", flat=True)
    )
