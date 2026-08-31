"""Interval-based availability contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from apps.inventory.availability import (
    DateTimeInterval,
    available_quantity_for_range,
    can_reserve_quantity,
    reserved_quantity_for_range,
)
from apps.inventory.taxonomy import ItemAvailabilityState, TrackingMode


@dataclass
class FakeReservation:
    item_id: int
    quantity: int
    starts_at: datetime
    ends_at: datetime


def _interval(start_hours: int = 0, duration_hours: int = 2) -> DateTimeInterval:
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC) + timedelta(hours=start_hours)
    return DateTimeInterval(start=start, end=start + timedelta(hours=duration_hours))


def test_pooled_available_quantity_subtracts_overlapping_reservations(pooled_item):
    interval = _interval()
    reservations = (
        FakeReservation(
            item_id=pooled_item.pk,
            quantity=3,
            starts_at=interval.start,
            ends_at=interval.end,
        ),
    )
    assert (
        reserved_quantity_for_range(pooled_item, interval, reservations=reservations)
        == 3
    )
    assert (
        available_quantity_for_range(pooled_item, interval, reservations=reservations)
        == 7
    )


def test_serialized_available_quantity_is_zero_or_one(serialized_item):
    interval = _interval()
    assert available_quantity_for_range(serialized_item, interval) == 1
    reservations = (
        FakeReservation(
            item_id=serialized_item.pk,
            quantity=1,
            starts_at=interval.start,
            ends_at=interval.end,
        ),
    )
    assert (
        available_quantity_for_range(
            serialized_item, interval, reservations=reservations
        )
        == 0
    )


def test_retired_item_has_zero_available_quantity(serialized_item):
    from django.utils import timezone

    serialized_item.availability_state = ItemAvailabilityState.RETIRED
    serialized_item.retired_at = timezone.now()
    assert available_quantity_for_range(serialized_item, _interval()) == 0


def test_can_reserve_quantity_rejects_invalid_amounts(pooled_item):
    interval = _interval()
    assert can_reserve_quantity(pooled_item, interval, 5) is True
    assert can_reserve_quantity(pooled_item, interval, 11) is False


def test_interval_end_must_follow_start():
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="end must be after start"):
        DateTimeInterval(start=start, end=start)


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


@pytest.fixture
def branch(seeded):
    from apps.user.models import Office

    return Office.objects.get(slug="fairfax-va")


@pytest.fixture
def serialized_item(branch):
    from apps.inventory.models import InventoryItem
    from apps.inventory.taxonomy import ItemCategory, ItemCondition

    return InventoryItem.objects.create(
        owner_office=branch,
        name="Camera",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        asset_id="CAM-1",
        condition=ItemCondition.GOOD,
    )


@pytest.fixture
def pooled_item(branch):
    from apps.inventory.models import InventoryItem
    from apps.inventory.taxonomy import ItemCategory, ItemCondition

    return InventoryItem.objects.create(
        owner_office=branch,
        name="Signs",
        category=ItemCategory.SIGNAGE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=10,
        condition=ItemCondition.GOOD,
    )
