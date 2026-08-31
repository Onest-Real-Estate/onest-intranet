"""Interval-based availability for pooled and serialized inventory.

``total_quantity`` on :class:`~apps.inventory.models.InventoryItem` is the
authoritative on-hand count. Available quantity for a requested window is
always derived here — never stored as a global counter that drifts between
reservations.

Reservation rows ship in a later issue; this module defines the contract those
rows will plug into.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from apps.inventory.models import InventoryItem
from apps.inventory.taxonomy import ItemAvailabilityState, TrackingMode


@dataclass(frozen=True)
class DateTimeInterval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            msg = "Interval end must be after start."
            raise ValueError(msg)


class ReservationWindow(Protocol):
    """Shape future reservation rows must expose."""

    item_id: int
    quantity: int
    starts_at: datetime
    ends_at: datetime


def intervals_overlap(left: DateTimeInterval, right: DateTimeInterval) -> bool:
    return left.start < right.end and right.start < left.end


def _overlaps_requested(
    reservation: ReservationWindow, interval: DateTimeInterval
) -> bool:
    return reservation.starts_at < interval.end and interval.start < reservation.ends_at


def reserved_quantity_for_range(
    item: InventoryItem,
    interval: DateTimeInterval,
    *,
    reservations: tuple[ReservationWindow, ...] = (),
) -> int:
    """Sum overlapping reservation quantity for ``item`` in ``interval``."""
    total = 0
    for reservation in reservations:
        if reservation.item_id != item.pk:
            continue
        if not _overlaps_requested(reservation, interval):
            continue
        total += max(reservation.quantity, 0)
    return total


def available_quantity_for_range(
    item: InventoryItem,
    interval: DateTimeInterval,
    *,
    reservations: tuple[ReservationWindow, ...] = (),
) -> int:
    """Return how many units may be reserved in ``interval``.

    Returns zero when the item is not in a reservable catalog state or is
    retired. For serialized stock the result is ``0`` or ``1``.
    """
    if not item.is_reservable:
        return 0

    if item.availability_state not in {
        ItemAvailabilityState.ACTIVE,
        ItemAvailabilityState.AVAILABLE,
    }:
        return 0

    reserved = reserved_quantity_for_range(item, interval, reservations=reservations)
    capacity = item.effective_quantity
    available = capacity - reserved
    if item.tracking_mode == TrackingMode.SERIALIZED:
        return 1 if available >= 1 else 0
    return max(available, 0)


def can_reserve_quantity(
    item: InventoryItem,
    interval: DateTimeInterval,
    quantity: int,
    *,
    reservations: tuple[ReservationWindow, ...] = (),
) -> bool:
    if quantity < 1:
        return False
    if item.tracking_mode == TrackingMode.SERIALIZED and quantity != 1:
        return False
    return (
        available_quantity_for_range(item, interval, reservations=reservations)
        >= quantity
    )
