from datetime import UTC, datetime

from apps.reservations.models import SpaceAvailabilityException
from apps.reservations.queries import (
    agent_spaces,
    exceptions_for_reader,
    manager_spaces,
    space_for_agent,
    space_payload,
)
from apps.reservations.taxonomy import (
    ExceptionKind,
    ExceptionVisibility,
    SpacePermission,
    SpaceStatus,
)
from apps.reservations.tests.factories import assign_role, make_space, office, person
from apps.user.roles import ScopeType
from apps.user.services.role_assignments import EffectiveAccess, get_effective_access


def test_agent_sees_only_active_reservable_spaces_at_own_office(seeded):
    agent = person("agent@example.com", "fairfax-va")
    visible = make_space(name="Visible room")
    make_space(name="Inactive room", status=SpaceStatus.INACTIVE, is_reservable=False)
    make_space(owner_slug="harrisburg", name="Other office")

    assert set(agent_spaces(agent).values_list("name", flat=True)) == {"Visible room"}
    assert space_for_agent(agent, public_id=visible.public_id) == visible
    foreign = make_space(owner_slug="harrisburg", name="Hidden foreign room")
    assert space_for_agent(agent, public_id=foreign.public_id) is None


def test_scoped_manager_cannot_discover_another_office(seeded):
    manager = person("manager@example.com", "fairfax-va")
    assign_role(
        manager,
        "branch_manager",
        ScopeType.OFFICE,
        scope_office=office("fairfax-va"),
    )
    make_space(name="Fairfax room")
    make_space(owner_slug="harrisburg", name="Harrisburg room")
    access = get_effective_access(manager)

    assert set(
        manager_spaces(manager, access=access).values_list("name", flat=True)
    ) == {"Fairfax room"}


def test_manager_query_fails_closed_without_view_permission(seeded):
    user = person("limited@example.com", "fairfax-va")
    make_space()
    access = EffectiveAccess(
        assignments=(),
        role_keys=(),
        permissions=frozenset(),
        region_keys=frozenset(),
        office_keys=frozenset({"fairfax-va"}),
        company_wide=False,
    )

    assert not manager_spaces(user, access=access).exists()


def test_sensitive_field_is_deferred_and_absent_from_payload_without_grant(seeded):
    user = person("viewer@example.com", "fairfax-va")
    space = make_space(access_instructions="Use the lockbox code")
    access = EffectiveAccess(
        assignments=(),
        role_keys=(),
        permissions=frozenset({SpacePermission.VIEW}),
        region_keys=frozenset(),
        office_keys=frozenset({"fairfax-va"}),
        company_wide=False,
    )

    loaded = manager_spaces(user, access=access).get(pk=space.pk)
    assert "access_instructions" in loaded.get_deferred_fields()
    payload = space_payload(user, loaded, access=access)
    assert payload is not None
    assert "accessInstructions" not in payload


def test_sensitive_payload_requires_permission_and_scope(seeded):
    manager = person("manager@example.com", "fairfax-va")
    assign_role(
        manager,
        "branch_manager",
        ScopeType.OFFICE,
        scope_office=office("fairfax-va"),
    )
    space = make_space(access_instructions="Use the staffed reception entrance")
    access = get_effective_access(manager)
    loaded = manager_spaces(manager, access=access, include_sensitive=True).get(
        pk=space.pk
    )

    payload = space_payload(manager, loaded, access=access)
    assert payload is not None
    assert payload["accessInstructions"] == "Use the staffed reception entrance"


def test_internal_exception_is_hidden_without_sensitive_grant(seeded):
    user = person("viewer@example.com", "fairfax-va")
    space = make_space()
    public = SpaceAvailabilityException.objects.create(
        space=space,
        kind=ExceptionKind.HOLIDAY,
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
        ends_at=datetime(2026, 1, 2, tzinfo=UTC),
        reason="Office closed",
        visibility=ExceptionVisibility.PUBLIC,
    )
    SpaceAvailabilityException.objects.create(
        space=space,
        kind=ExceptionKind.MAINTENANCE,
        starts_at=datetime(2026, 1, 3, tzinfo=UTC),
        ends_at=datetime(2026, 1, 4, tzinfo=UTC),
        reason="Security system work",
        visibility=ExceptionVisibility.INTERNAL,
    )
    access = EffectiveAccess(
        assignments=(),
        role_keys=(),
        permissions=frozenset({SpacePermission.VIEW}),
        region_keys=frozenset(),
        office_keys=frozenset({"fairfax-va"}),
        company_wide=False,
    )

    assert list(exceptions_for_reader(user, space=space, access=access)) == [public]


def test_exception_query_fails_closed_for_a_foreign_space(seeded):
    user = person("agent@example.com", "fairfax-va")
    foreign = make_space(owner_slug="harrisburg")
    SpaceAvailabilityException.objects.create(
        space=foreign,
        kind=ExceptionKind.HOLIDAY,
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
        ends_at=datetime(2026, 1, 2, tzinfo=UTC),
        reason="Office closed",
        visibility=ExceptionVisibility.PUBLIC,
    )

    assert not exceptions_for_reader(user, space=foreign).exists()


# ---------------------------------------------------------------------------
# Office-chain inheritance
#
# Agent visibility used to be an exact `owner_office` match, so a room shared
# by two offices had to be entered twice — the Space table still carries those
# duplicates — and a branch with no rooms of its own showed an empty calendar.
# ---------------------------------------------------------------------------


def test_agent_books_a_room_published_at_the_head_office(seeded):
    agent = person("agent@example.com", "fairfax-va")
    shared = make_space(owner_slug="onest-head-office", name="Brokerage boardroom")

    assert set(agent_spaces(agent).values_list("name", flat=True)) == {
        "Brokerage boardroom"
    }
    assert space_for_agent(agent, public_id=shared.public_id) == shared


def test_the_payload_gate_agrees_with_the_queryset(seeded):
    # These are two gates on the same question — a list and a single record.
    # When the rule lived in both places separately they drifted: the queryset
    # listed an inherited room and the payload then answered `None`.
    agent = person("agent@example.com", "fairfax-va")
    shared = make_space(owner_slug="onest-head-office", name="Brokerage boardroom")

    assert shared in list(agent_spaces(agent))
    assert space_payload(agent, shared) is not None


def test_the_payload_names_the_office_that_owns_the_room(seeded):
    agent = person("agent@example.com", "fairfax-va")
    shared = make_space(owner_slug="onest-head-office", name="Brokerage boardroom")

    payload = space_payload(agent, shared)
    assert payload is not None
    assert payload["officeId"] == office("onest-head-office").stable_key


def test_inheritance_does_not_reach_a_sibling_branch(seeded):
    agent = person("agent@example.com", "fairfax-va")
    foreign = make_space(owner_slug="harrisburg", name="Harrisburg room")

    assert set(agent_spaces(agent).values_list("name", flat=True)) == set()
    assert space_payload(agent, foreign) is None


def test_a_reader_at_a_parent_office_does_not_inherit_the_branches(seeded):
    staff = person("staff@example.com", "onest-head-office")
    branch_room = make_space(owner_slug="fairfax-va", name="Fairfax room")
    make_space(owner_slug="onest-head-office", name="Brokerage boardroom")

    assert set(agent_spaces(staff).values_list("name", flat=True)) == {
        "Brokerage boardroom"
    }
    assert space_payload(staff, branch_room) is None


def test_an_inherited_room_that_is_not_reservable_stays_hidden(seeded):
    agent = person("agent@example.com", "fairfax-va")
    make_space(
        owner_slug="onest-head-office",
        name="Retired brokerage room",
        status=SpaceStatus.INACTIVE,
        is_reservable=False,
    )
    assert set(agent_spaces(agent).values_list("name", flat=True)) == set()
