"""Authoritative overdue definitions for inventory return deadlines.

Return dates are date-only at input and stored as half-open ``[starts_at,
ends_at)`` timestamps. The inclusive return calendar day is one day before
``ends_at`` in the active timezone. A reservation is overdue when it is
``checked_out`` past ``ends_at`` or already marked ``overdue``.

Metrics, dashboard widgets, action items, and notification schedules all import
from here so they cannot drift apart.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.inventory.models import InventoryReservation
from apps.inventory.reservation_taxonomy import ReservationStatus

REMINDER_SUPPRESSION_STATUSES = frozenset(
    {
        ReservationStatus.RETURNED,
        ReservationStatus.COMPLETED,
        ReservationStatus.CANCELLED,
        ReservationStatus.DENIED,
    }
)

DUE_SOON_STATUSES = frozenset({ReservationStatus.CHECKED_OUT})

OVERDUE_NOTICE_STATUSES = frozenset(
    {
        ReservationStatus.CHECKED_OUT,
        ReservationStatus.OVERDUE,
    }
)

LOST_DAMAGED_ESCALATION_STATUSES = frozenset(
    {
        ReservationStatus.LOST,
        ReservationStatus.DAMAGED,
    }
)


def return_calendar_day(
    reservation: InventoryReservation, *, at: date | None = None
) -> date:
    """Inclusive return day derived from exclusive ``ends_at``."""
    _ = at  # reserved for future office-timezone overrides
    local_end = timezone.localtime(reservation.ends_at)
    return (local_end - timedelta(microseconds=1)).date()


def days_until_return(
    reservation: InventoryReservation, *, today: date | None = None
) -> int:
    today = today or timezone.localdate()
    return (return_calendar_day(reservation) - today).days


def days_overdue(
    reservation: InventoryReservation, *, today: date | None = None
) -> int:
    today = today or timezone.localdate()
    return (today - return_calendar_day(reservation)).days


def is_overdue(reservation: InventoryReservation, *, now=None) -> bool:
    moment = now or timezone.now()
    if reservation.status in REMINDER_SUPPRESSION_STATUSES:
        return False
    if reservation.status in LOST_DAMAGED_ESCALATION_STATUSES:
        return False
    if reservation.status == ReservationStatus.OVERDUE:
        return True
    if reservation.status == ReservationStatus.CHECKED_OUT:
        return reservation.ends_at <= moment
    return False


def overdue_filter(*, now=None) -> Q:
    moment = now or timezone.now()
    return Q(status=ReservationStatus.OVERDUE) | Q(
        status=ReservationStatus.CHECKED_OUT,
        ends_at__lte=moment,
    )


def overdue_queryset(
    queryset: QuerySet[InventoryReservation], *, now=None
) -> QuerySet[InventoryReservation]:
    return queryset.filter(overdue_filter(now=now))


def due_soon_queryset(
    queryset: QuerySet[InventoryReservation],
    *,
    lead_days: tuple[int, ...],
    today: date | None = None,
) -> QuerySet[InventoryReservation]:
    today = today or timezone.localdate()
    ends_at_marks: list[datetime] = []
    for day in lead_days:
        if day <= 0:
            continue
        return_day = today + timedelta(days=day)
        exclusive_end = return_day + timedelta(days=1)
        ends_at_marks.append(
            timezone.make_aware(datetime.combine(exclusive_end, time.min))
        )
    if not ends_at_marks:
        return queryset.none()
    return queryset.filter(
        status=ReservationStatus.CHECKED_OUT,
        ends_at__gt=timezone.now(),
        ends_at__in=ends_at_marks,
    )
