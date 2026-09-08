"""Model validation, constraints, and identifier uniqueness."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.inventory.models import InventoryItem
from apps.inventory.taxonomy import (
    ItemAvailabilityState,
    ItemCategory,
    ItemCondition,
    TrackingMode,
)
from apps.user.models import Office


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def serialized_item(owner: Office, asset_id: str, **kwargs) -> InventoryItem:
    item = InventoryItem(
        owner_office=owner,
        name=kwargs.pop("name", "Laptop"),
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        asset_id=asset_id,
        condition=ItemCondition.GOOD,
        **kwargs,
    )
    item.full_clean()
    item.save()
    return item


def pooled_item(owner: Office, quantity: int = 10, **kwargs) -> InventoryItem:
    item = InventoryItem(
        owner_office=owner,
        name=kwargs.pop("name", "Open house signs"),
        category=ItemCategory.SIGNAGE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=quantity,
        condition=ItemCondition.GOOD,
        **kwargs,
    )
    item.full_clean()
    item.save()
    return item


def test_serialized_item_requires_asset_id(seeded):
    branch = office("fairfax-va")
    item = InventoryItem(
        owner_office=branch,
        name="Camera",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        asset_id="",
        condition=ItemCondition.GOOD,
    )
    with pytest.raises(ValidationError, match="asset id"):
        item.full_clean()


def test_serialized_item_quantity_must_be_one(seeded):
    branch = office("fairfax-va")
    item = InventoryItem(
        owner_office=branch,
        name="Camera",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        asset_id="CAM-001",
        total_quantity=2,
        condition=ItemCondition.GOOD,
    )
    with pytest.raises(ValidationError, match="quantity"):
        item.full_clean()


def test_pooled_item_rejects_asset_and_serial_identifiers(seeded):
    branch = office("fairfax-va")
    item = InventoryItem(
        owner_office=branch,
        name="Signs",
        category=ItemCategory.SIGNAGE,
        tracking_mode=TrackingMode.POOLED,
        asset_id="SIG-1",
        total_quantity=5,
        condition=ItemCondition.GOOD,
    )
    with pytest.raises(ValidationError, match="identifiers"):
        item.full_clean()


def test_pooled_item_requires_positive_quantity(seeded):
    branch = office("fairfax-va")
    item = InventoryItem(
        owner_office=branch,
        name="Signs",
        category=ItemCategory.SIGNAGE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=0,
        condition=ItemCondition.GOOD,
    )
    with pytest.raises(ValidationError):
        item.full_clean()


def test_duplicate_asset_id_per_office_is_rejected(seeded):
    branch = office("fairfax-va")
    serialized_item(branch, "LAP-100")
    duplicate = InventoryItem(
        owner_office=branch,
        name="Other laptop",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        asset_id="LAP-100",
        condition=ItemCondition.GOOD,
    )
    with pytest.raises(ValidationError, match="unique_asset_id"):
        duplicate.full_clean()


def test_same_asset_id_at_different_offices_is_allowed(seeded):
    fairfax = office("fairfax-va")
    harrisburg = office("harrisburg")
    serialized_item(fairfax, "LAP-100", name="Fairfax laptop")
    serialized_item(harrisburg, "LAP-100", name="Harrisburg laptop")


def test_duplicate_serial_number_per_office_is_rejected(seeded):
    branch = office("fairfax-va")
    serialized_item(branch, "LAP-101", serial_number="SN-9")
    duplicate = InventoryItem(
        owner_office=branch,
        name="Clone",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        asset_id="LAP-102",
        serial_number="SN-9",
        condition=ItemCondition.GOOD,
    )
    with pytest.raises(ValidationError, match="unique_serial"):
        duplicate.full_clean()


def test_non_assignable_office_cannot_own_inventory(seeded):
    region = office("region-mid-atlantic")
    assert not region.is_assignable
    item = InventoryItem(
        owner_office=region,
        name="Region chair",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=1,
        condition=ItemCondition.GOOD,
    )
    with pytest.raises(ValidationError, match="assignable"):
        item.full_clean()


def test_retired_state_requires_retired_at(seeded):
    branch = office("fairfax-va")
    item = serialized_item(branch, "RET-1")
    item.availability_state = ItemAvailabilityState.RETIRED
    with pytest.raises(ValidationError, match="retirement"):
        item.full_clean()


def test_negative_replacement_value_is_rejected(seeded):
    branch = office("fairfax-va")
    item = serialized_item(branch, "VAL-1")
    item.replacement_value = Decimal("-1.00")
    with pytest.raises(ValidationError, match="nonnegative"):
        item.full_clean()
