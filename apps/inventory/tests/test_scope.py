"""Scoped inventory query services."""

from __future__ import annotations

import pytest

from apps.inventory.models import InventoryItem
from apps.inventory.queries import InventoryFilters, agent_inventory, manager_inventory
from apps.inventory.taxonomy import ItemAvailabilityState
from apps.user.models import Office, UserRoleAssignment
from apps.user.services.role_assignments import get_effective_access
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, slug: str):
    return completed_user(email=email, office=office(slug))


def assign_role(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def make_item(owner_slug: str, name: str, *, state=ItemAvailabilityState.AVAILABLE):
    from apps.inventory.taxonomy import ItemCategory, ItemCondition, TrackingMode

    return InventoryItem.objects.create(
        owner_office=office(owner_slug),
        name=name,
        category=ItemCategory.OTHER,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=3,
        condition=ItemCondition.GOOD,
        availability_state=state,
    )


def manager_names(user) -> set[str]:
    access = get_effective_access(user)
    return set(manager_inventory(user, access=access).values_list("name", flat=True))


def agent_names(user) -> set[str]:
    return set(agent_inventory(user).values_list("name", flat=True))


def test_manager_with_no_grant_sees_nothing(seeded):
    make_item("fairfax-va", "Fairfax chair")
    agent = person("agent@example.com", "fairfax-va")
    assert manager_names(agent) == set()


def test_branch_manager_sees_own_office_inventory(seeded):
    manager = person("mgr@example.com", "fairfax-va")
    assign_role(manager, "branch_manager", "office", scope_office=office("fairfax-va"))
    make_item("fairfax-va", "Fairfax chair")
    make_item("harrisburg", "Harrisburg chair")
    assert manager_names(manager) == {"Fairfax chair"}


def test_regional_manager_sees_descendant_offices(seeded):
    manager = person("rm@example.com", "region-mid-atlantic")
    region = office("region-mid-atlantic")
    assign_role(manager, "regional_manager", "region", scope_office=region)
    make_item("fairfax-va", "Fairfax chair")
    make_item("harrisburg", "Harrisburg chair")
    assert manager_names(manager) == {"Fairfax chair", "Harrisburg chair"}


def test_company_admin_sees_all_inventory(seeded):
    admin = person("admin@example.com", "onest-head-office")
    assign_role(admin, "system_admin", "company")
    make_item("fairfax-va", "Fairfax chair")
    make_item("harrisburg", "Harrisburg chair")
    assert manager_names(admin) == {"Fairfax chair", "Harrisburg chair"}


def test_agent_sees_reservable_items_for_assigned_office_only(seeded):
    agent = person("agent@example.com", "fairfax-va")
    make_item("fairfax-va", "Reservable", state=ItemAvailabilityState.AVAILABLE)
    make_item("fairfax-va", "Damaged", state=ItemAvailabilityState.DAMAGED)
    make_item("harrisburg", "Other office")
    assert agent_names(agent) == {"Reservable"}


def test_retired_items_are_hidden_from_manager_catalog(seeded):
    admin = person("admin@example.com", "onest-head-office")
    assign_role(admin, "system_admin", "company")
    from django.utils import timezone

    from apps.inventory.taxonomy import ItemCategory, ItemCondition, TrackingMode

    InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Retired chair",
        category=ItemCategory.OTHER,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=1,
        condition=ItemCondition.GOOD,
        availability_state=ItemAvailabilityState.RETIRED,
        retired_at=timezone.now(),
    )
    make_item("fairfax-va", "Live chair")
    assert manager_names(admin) == {"Live chair"}


def test_filters_apply_category_and_search(seeded):
    admin = person("admin@example.com", "onest-head-office")
    assign_role(admin, "system_admin", "company")
    from apps.inventory.taxonomy import ItemCategory

    make_item("fairfax-va", "Blue signage kit")
    InventoryItem.objects.filter(name="Blue signage kit").update(
        category=ItemCategory.SIGNAGE
    )
    make_item("fairfax-va", "Desk lamp")
    access = get_effective_access(admin)
    filters = InventoryFilters(q="signage", category=ItemCategory.SIGNAGE)
    names = set(
        manager_inventory(admin, access=access, filters=filters).values_list(
            "name", flat=True
        )
    )
    assert names == {"Blue signage kit"}


def test_superuser_writable_scope_includes_assignable_offices(seeded):
    from apps.inventory.administration import inventory_scope, writable_offices

    superuser = person("super@example.com", "fairfax-va")
    superuser.is_superuser = True
    superuser.save(update_fields=["is_superuser"])
    scope = inventory_scope(superuser)
    assert scope.office_ids
    assert office("fairfax-va").pk in scope.office_ids
    assert writable_offices(superuser).filter(pk=office("fairfax-va").pk).exists()


# ---------------------------------------------------------------------------
# Office-chain inheritance
#
# The agent catalogue used to be an exact `owner_office` match, so there was no
# way to publish one record for the whole brokerage — an administrator had to
# re-create it per branch — and any office holding no records of its own showed
# its agents an empty catalogue. Scope is now the office chain, downward only.
# ---------------------------------------------------------------------------


def test_agent_sees_company_wide_stock_published_once(seeded):
    agent = person("agent@example.com", "fairfax-va")
    make_item("onest-head-office", "Brokerage lockbox")
    assert agent_names(agent) == {"Brokerage lockbox"}


def test_own_office_and_inherited_stock_appear_together(seeded):
    agent = person("agent@example.com", "fairfax-va")
    make_item("onest-head-office", "Brokerage lockbox")
    make_item("fairfax-va", "Fairfax chair")
    assert agent_names(agent) == {"Brokerage lockbox", "Fairfax chair"}


def test_a_node_that_cannot_own_stock_does_not_break_the_chain(seeded):
    # Fairfax's chain is branch → ro-virginia → region-mid-atlantic → head
    # office, and the two middle nodes are not assignable, so nothing can be
    # owned there. The head office above them still reaches the branch.
    agent = person("agent@example.com", "fairfax-va")
    assert office("ro-virginia").is_assignable is False
    make_item("onest-head-office", "Brokerage lockbox")
    assert agent_names(agent) == {"Brokerage lockbox"}


def test_inheritance_does_not_reach_a_sibling_branch(seeded):
    agent = person("agent@example.com", "fairfax-va")
    make_item("harrisburg", "Harrisburg pole")
    make_item("onest-head-office", "Brokerage lockbox")
    # The chain runs up, never across or down.
    assert agent_names(agent) == {"Brokerage lockbox"}


def test_a_reader_at_a_parent_office_does_not_inherit_the_branches(seeded):
    # Descendant reach is manager reach and lives behind `web.view_inventory`
    # on the administration surface. The agent catalogue must not grant it, or
    # head-office staff could reserve a lockbox physically held in another city.
    staff = person("staff@example.com", "onest-head-office")
    make_item("fairfax-va", "Fairfax chair")
    make_item("onest-head-office", "Brokerage lockbox")
    assert agent_names(staff) == {"Brokerage lockbox"}


def test_inherited_items_still_respect_the_reservable_catalog(seeded):
    agent = person("agent@example.com", "fairfax-va")
    make_item(
        "onest-head-office", "Damaged company kit", state=ItemAvailabilityState.DAMAGED
    )
    assert agent_names(agent) == set()


def test_a_reader_without_an_office_has_no_chain(seeded):
    agent = person("agent@example.com", "fairfax-va")
    agent.office = None
    agent.save(update_fields=["office"])
    make_item("onest-head-office", "Brokerage lockbox")
    assert agent_names(agent) == set()


def test_a_reader_whose_office_is_inactive_has_no_chain(seeded):
    agent = person("agent@example.com", "fairfax-va")
    branch = office("fairfax-va")
    branch.is_active = False
    branch.save(update_fields=["is_active"])
    make_item("onest-head-office", "Brokerage lockbox")
    agent.refresh_from_db()
    assert agent_names(agent) == set()
