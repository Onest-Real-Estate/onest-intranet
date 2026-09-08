"""Field-level serialization permissions."""

from __future__ import annotations

import pytest

from apps.inventory.payloads import serialize_item
from apps.inventory.taxonomy import InventoryPermission


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


@pytest.fixture
def item(seeded):
    from decimal import Decimal

    from apps.inventory.models import InventoryItem
    from apps.inventory.taxonomy import ItemCategory, ItemCondition, TrackingMode
    from apps.user.models import Office

    return InventoryItem.objects.create(
        owner_office=Office.objects.get(slug="fairfax-va"),
        name="Laptop",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        asset_id="LAP-300",
        serial_number="SN-300",
        condition=ItemCondition.GOOD,
        internal_notes="Insurance rider on file",
        replacement_value=Decimal("1200.00"),
        replacement_currency="USD",
    )


def test_sensitive_fields_hidden_without_grant(item):
    payload = serialize_item(item, permissions=frozenset({InventoryPermission.VIEW}))
    assert "assetId" not in payload
    assert "serialNumber" not in payload
    assert "internalNotes" not in payload
    assert "replacementValue" not in payload


def test_sensitive_fields_included_with_grant(item):
    payload = serialize_item(
        item,
        permissions=frozenset(
            {InventoryPermission.VIEW, InventoryPermission.VIEW_SENSITIVE}
        ),
    )
    assert payload["assetId"] == "LAP-300"
    assert payload["serialNumber"] == "SN-300"
    assert payload["internalNotes"] == "Insurance rider on file"
    assert payload["replacementValue"] == "1200.00"
