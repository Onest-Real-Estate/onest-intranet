"""Lifecycle services: create, retire, transfer."""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.inventory.models import InventoryItem, InventoryTransfer
from apps.inventory.services import (
    ActorContext,
    create_item,
    retire_item,
    transfer_item,
)
from apps.inventory.taxonomy import (
    InventoryPermission,
    ItemCategory,
    ItemCondition,
    TrackingMode,
)
from apps.user.models import Office, UserRoleAssignment
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


def manager_actor(user) -> ActorContext:
    return ActorContext(
        user=user,
        permissions=frozenset(
            {
                InventoryPermission.VIEW,
                InventoryPermission.MANAGE,
                InventoryPermission.VIEW_SENSITIVE,
            }
        ),
    )


def test_create_item_requires_manage_permission(seeded):
    agent = person("agent@example.com", "fairfax-va")
    with pytest.raises(PermissionDenied):
        create_item(
            actor=ActorContext(user=agent, permissions=frozenset()),
            owner_office=office("fairfax-va"),
            name="Chair",
            category=ItemCategory.FURNITURE,
            tracking_mode=TrackingMode.POOLED,
            condition=ItemCondition.GOOD,
            total_quantity=2,
        )


def test_create_serialized_item(seeded):
    manager = person("mgr@example.com", "fairfax-va")
    item = create_item(
        actor=manager_actor(manager),
        owner_office=office("fairfax-va"),
        name="Laptop",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        condition=ItemCondition.GOOD,
        asset_id="LAP-200",
        serial_number="SN-200",
    )
    assert item.total_quantity == 1
    assert item.asset_id == "LAP-200"


def test_retire_item_preserves_row_and_blocks_reservations(seeded):
    manager = person("mgr@example.com", "fairfax-va")
    item = create_item(
        actor=manager_actor(manager),
        owner_office=office("fairfax-va"),
        name="Chair",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        condition=ItemCondition.GOOD,
        total_quantity=2,
    )
    retired = retire_item(actor=manager_actor(manager), item=item)
    assert retired.is_retired
    assert retired.retired_at is not None
    assert not retired.is_reservable
    assert InventoryItem.objects.filter(pk=item.pk).exists()


def test_retired_item_cannot_be_transferred(seeded):
    manager = person("mgr@example.com", "fairfax-va")
    item = create_item(
        actor=manager_actor(manager),
        owner_office=office("fairfax-va"),
        name="Chair",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        condition=ItemCondition.GOOD,
        total_quantity=1,
    )
    retire_item(actor=manager_actor(manager), item=item)
    with pytest.raises(ValidationError, match="Retired"):
        transfer_item(
            actor=manager_actor(manager),
            item=item,
            to_office=office("harrisburg"),
        )


def test_transfer_item_updates_owner_and_writes_audit_row(seeded):
    manager = person("mgr@example.com", "fairfax-va")
    assign_role(manager, "branch_manager", "office", scope_office=office("fairfax-va"))
    item = create_item(
        actor=manager_actor(manager),
        owner_office=office("fairfax-va"),
        name="Chair",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        condition=ItemCondition.GOOD,
        total_quantity=1,
    )
    destination = office("harrisburg")
    transfer = transfer_item(
        actor=manager_actor(manager),
        item=item,
        to_office=destination,
        reason="Branch consolidation",
    )
    item.refresh_from_db()
    assert item.owner_office.pk == destination.pk
    assert transfer.from_office.pk == office("fairfax-va").pk
    assert InventoryTransfer.objects.filter(item=item).count() == 1
