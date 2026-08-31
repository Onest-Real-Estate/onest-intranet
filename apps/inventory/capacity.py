"""Authoritative inventory capacity: locking, overlap, and peak demand.

Correctness for overlapping reservations lives here — never in a preflight
query, cache, or Celery task. Every create, status transition, reschedule,
quantity change, cancel/release, return, item quantity reduction, and
administrative override must go through these helpers inside one short
database transaction.

**Interval semantics.** Reservation windows are half-open
``[starts_at, ends_at)``. Two intervals overlap when
``a.starts_at < b.ends_at AND b.starts_at < a.ends_at``. Adjacent bookings
that meet at an endpoint do not overlap (return at noon frees capacity for
a pickup at noon).

**Capacity-consuming statuses.** See
:data:`~apps.inventory.reservation_taxonomy.CAPACITY_CONSUMING_STATES`.
Non-consuming states (returned, completed, cancelled, denied, lost, damaged)
do not hold quantity.

**Locking order** (deadlock prevention):

1. Lock :class:`~apps.inventory.models.InventoryItem` rows with
   ``select_for_update(of=("self",))`` in ascending primary-key order.
2. Lock :class:`~apps.inventory.models.InventoryReservation` rows the same
   way, also ascending by pk, after every required item lock is held.
3. Never combine ``select_for_update`` with ``select_related("owner_office")``
   (nullable join → PostgreSQL rejects ``FOR UPDATE`` on the outer side).
4. Do not call remote I/O, file storage, email, or event buses while holding
   locks. Schedule those with ``transaction.on_commit`` / ``log_on_commit``.

``total_quantity`` on the locked item row is the physical capacity ceiling.
Admin policy override may bypass horizon/hours/cutoff rules but must not
exceed that ceiling unless an explicit over-allocation record is written.
"""

from __future__ import annotations

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.inventory.availability import (
    DateTimeInterval,
    can_reserve_quantity,
)
from apps.inventory.models import InventoryItem, InventoryReservation
from apps.inventory.reservation_taxonomy import CAPACITY_CONSUMING_STATES

#: Actionable conflict copy — never names other reservation owners.
CAPACITY_CONFLICT_MESSAGE = _(
    "Not enough quantity is available for those dates. "
    "Choose another range and try again."
)

ITEM_UNAVAILABLE_MESSAGE = _("That item is not available to reserve right now.")


class AvailabilityConflict(ValidationError):
    """Requested quantity no longer fits the locked capacity window.

    Views map this to HTTP 409. Message dict never includes other owners.
    """

    def __init__(self, message: str | None = None) -> None:
        detail = {"form": [str(message or CAPACITY_CONFLICT_MESSAGE)]}
        super().__init__(detail)


def ensure_atomic() -> None:
    """Fail fast when capacity helpers are called outside a transaction."""
    if not transaction.get_connection().in_atomic_block:
        msg = "Capacity mutations require transaction.atomic()."
        raise RuntimeError(msg)


def lock_items(*item_ids: int) -> dict[int, InventoryItem]:
    """Lock capacity rows in ascending pk order. Must run inside ``atomic``."""
    ids = sorted({int(pk) for pk in item_ids if pk})
    if not ids:
        return {}
    locked = {
        item.pk: item
        for item in InventoryItem.objects.select_for_update(of=("self",)).filter(
            pk__in=ids
        )
    }
    missing = set(ids) - set(locked)
    if missing:
        msg = f"Inventory item(s) not found for capacity lock: {sorted(missing)}"
        raise InventoryItem.DoesNotExist(msg)
    return locked


def lock_item(item_id: int) -> InventoryItem:
    return lock_items(item_id)[item_id]


def lock_reservations(*reservation_ids: int) -> dict[int, InventoryReservation]:
    """Lock reservation rows in ascending pk order after item locks."""
    ids = sorted({int(pk) for pk in reservation_ids if pk})
    if not ids:
        return {}
    locked = {
        row.pk: row
        for row in InventoryReservation.objects.select_for_update(of=("self",)).filter(
            pk__in=ids
        )
    }
    missing = set(ids) - set(locked)
    if missing:
        msg = f"Reservation(s) not found for capacity lock: {sorted(missing)}"
        raise InventoryReservation.DoesNotExist(msg)
    return locked


def lock_reservation(reservation_id: int) -> InventoryReservation:
    return lock_reservations(reservation_id)[reservation_id]


def overlapping_capacity_queryset(
    *,
    item_id: int,
    starts_at: datetime,
    ends_at: datetime,
    exclude_reservation_id: int | None = None,
) -> QuerySet[InventoryReservation]:
    """Capacity-consuming rows that overlap ``[starts_at, ends_at)``."""
    qs = InventoryReservation.objects.overlapping(
        item_id=item_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    if exclude_reservation_id is not None:
        qs = qs.exclude(pk=exclude_reservation_id)
    return qs.only("pk", "item_id", "quantity", "starts_at", "ends_at", "status")


def load_overlapping_windows(
    *,
    item_id: int,
    interval: DateTimeInterval,
    exclude_reservation_id: int | None = None,
) -> tuple[InventoryReservation, ...]:
    return tuple(
        overlapping_capacity_queryset(
            item_id=item_id,
            starts_at=interval.start,
            ends_at=interval.end,
            exclude_reservation_id=exclude_reservation_id,
        )
    )


def assert_capacity_available(
    item: InventoryItem,
    interval: DateTimeInterval,
    quantity: int,
    *,
    exclude_reservation_id: int | None = None,
    require_reservable: bool = True,
) -> tuple[InventoryReservation, ...]:
    """Recalculate overlap under the held item lock; raise on shortfall.

    Caller must already hold ``select_for_update`` on ``item``.
    """
    if require_reservable and not item.is_reservable:
        raise AvailabilityConflict(str(ITEM_UNAVAILABLE_MESSAGE))

    windows = load_overlapping_windows(
        item_id=item.pk,
        interval=interval,
        exclude_reservation_id=exclude_reservation_id,
    )
    if not can_reserve_quantity(item, interval, quantity, reservations=windows):
        raise AvailabilityConflict()
    return windows


def peak_committed_quantity(
    item: InventoryItem,
    *,
    exclude_reservation_id: int | None = None,
) -> int:
    """Maximum overlapping capacity-consuming quantity for ``item``.

    Sweep-line over half-open intervals: end events sort before start events
    at the same instant so adjacent bookings do not inflate the peak.
    """
    qs = InventoryReservation.objects.filter(
        item_id=item.pk,
        status__in=sorted(CAPACITY_CONSUMING_STATES),
    ).only("quantity", "starts_at", "ends_at")
    if exclude_reservation_id is not None:
        qs = qs.exclude(pk=exclude_reservation_id)

    # kind: 0 = end (release), 1 = start (acquire). Ends first at equal time.
    events: list[tuple[datetime, int, int]] = []
    for row in qs:
        qty = max(int(row.quantity), 0)
        if qty == 0:
            continue
        events.append((row.starts_at, 1, qty))
        events.append((row.ends_at, 0, qty))

    events.sort(key=lambda event: (event[0], event[1]))
    current = 0
    peak = 0
    for _when, kind, qty in events:
        if kind == 0:
            current -= qty
        else:
            current += qty
            if current > peak:
                peak = current
    return peak


def assert_quantity_supports_commitments(
    item: InventoryItem,
    new_quantity: int,
    *,
    exclude_reservation_id: int | None = None,
) -> int:
    """Refuse reducing physical capacity below peak overlapping demand."""
    peak = peak_committed_quantity(item, exclude_reservation_id=exclude_reservation_id)
    if new_quantity < peak:
        raise AvailabilityConflict(
            str(
                _(
                    "Cannot reduce below %(peak)s units already committed "
                    "to overlapping reservations."
                )
                % {"peak": peak}
            )
        )
    return peak
