"""Scheduled inventory return reminders, overdue notices, and escalation.

Beat tasks re-check status, version, recipient, and permission immediately
before publishing. Lifecycle transitions that leave a reservation non-actionable
expire outstanding reminder rows so the centre and email ledger stop pushing
them.

Due semantics: user-facing return dates are inclusive calendar days in the
active timezone. ``ends_at`` is exclusive midnight on the day after the return
date, so a reservation becomes overdue once ``ends_at <= now``.
"""

from __future__ import annotations

import logging
from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.events import publish as publish_event
from apps.inventory.models import InventoryReservation
from apps.inventory.notification_recipients import operational_staff_ids
from apps.inventory.overdue import (
    DUE_SOON_STATUSES,
    LOST_DAMAGED_ESCALATION_STATUSES,
    OVERDUE_NOTICE_STATUSES,
    days_overdue,
    days_until_return,
    due_soon_queryset,
    is_overdue,
    overdue_queryset,
    return_calendar_day,
)
from apps.inventory.reservation_lifecycle import sync_overdue_reservations
from apps.inventory.reservation_taxonomy import ReservationStatus
from apps.notifications.models import Notification

logger = logging.getLogger("apps.inventory")

SOURCE_MODULE = "inventory"
RECORD_TYPE = "inventory_reservation"

_REMINDER_EVENTS = frozenset(
    {
        "inventory.reservation.return_due_soon",
        "inventory.reservation.return_overdue",
        "inventory.reservation.return_overdue_staff",
        "inventory.reservation.lost_damaged_escalation",
    }
)


def _policy_version() -> int:
    return int(getattr(settings, "INVENTORY_NOTIFICATION_POLICY_VERSION", 1))


def _due_soon_days() -> tuple[int, ...]:
    raw = getattr(settings, "INVENTORY_RETURN_DUE_SOON_DAYS", (1, 3))
    return tuple(int(day) for day in raw if int(day) > 0)


def _overdue_agent_days() -> tuple[int, ...]:
    raw = getattr(settings, "INVENTORY_RETURN_OVERDUE_AGENT_DAYS", (1, 3, 7))
    return tuple(int(day) for day in raw if int(day) > 0)


def _overdue_staff_days() -> tuple[int, ...]:
    raw = getattr(settings, "INVENTORY_RETURN_OVERDUE_STAFF_DAYS", (1, 3, 7))
    return tuple(int(day) for day in raw if int(day) > 0)


def _lost_damaged_days() -> tuple[int, ...]:
    raw = getattr(settings, "INVENTORY_LOST_DAMAGED_STAFF_DAYS", (1, 3))
    return tuple(int(day) for day in raw if int(day) > 0)


def suppress_stale_reminders(reservation: InventoryReservation, *, now=None) -> int:
    """Expire unread inventory reminders once the reservation is settled."""
    moment = now or timezone.now()
    reservation_id = str(reservation.public_id)
    if reservation.status in DUE_SOON_STATUSES and not is_overdue(
        reservation, now=moment
    ):
        event_keys = {
            "inventory.reservation.return_overdue",
            "inventory.reservation.return_overdue_staff",
            "inventory.reservation.lost_damaged_escalation",
        }
    elif reservation.status in OVERDUE_NOTICE_STATUSES and is_overdue(
        reservation, now=moment
    ):
        event_keys = {
            "inventory.reservation.return_due_soon",
            "inventory.reservation.lost_damaged_escalation",
        }
    elif reservation.status in LOST_DAMAGED_ESCALATION_STATUSES:
        event_keys = {
            "inventory.reservation.return_due_soon",
            "inventory.reservation.return_overdue",
            "inventory.reservation.return_overdue_staff",
        }
    else:
        event_keys = _REMINDER_EVENTS

    return (
        Notification.objects.filter(
            source_module=SOURCE_MODULE,
            source_record_id=reservation_id,
            event_key__in=event_keys,
            archived_at__isnull=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=moment))
        .update(expires_at=moment)
    )


def _base_payload(reservation: InventoryReservation, *, moment, **extra) -> dict:
    payload = {
        "reservation_public_id": str(reservation.public_id),
        "office_id": str(reservation.office_id),
        "owner_id": str(reservation.owner_id),
        "policy_version": str(_policy_version()),
        "occurred_at": moment.isoformat(),
    }
    payload.update(extra)
    return payload


def _lock_reservation(pk: int) -> InventoryReservation | None:
    return (
        InventoryReservation.objects.select_for_update(of=("self",))
        .select_related("office", "office__region", "owner")
        .filter(pk=pk)
        .first()
    )


def publish_due_soon_reminders(*, as_of: date | None = None) -> int:
    """Notify agents before the inclusive return date at approved lead times."""
    today = as_of or timezone.localdate()
    moment = timezone.now()
    published = 0
    lead_days = _due_soon_days()
    candidates = due_soon_queryset(
        InventoryReservation.objects.all(),
        lead_days=lead_days,
        today=today,
    ).order_by("pk")[:300]
    for reservation in candidates:
        if reservation.status not in DUE_SOON_STATUSES:
            continue
        remaining = days_until_return(reservation, today=today)
        if remaining not in lead_days or remaining <= 0:
            continue
        with transaction.atomic():
            locked = _lock_reservation(reservation.pk)
            if locked is None or locked.status not in DUE_SOON_STATUSES:
                continue
            if days_until_return(locked, today=today) != remaining:
                continue
            if is_overdue(locked, now=moment):
                continue
            publish_event(
                "inventory.reservation.return_due_soon",
                actor_id="system",
                subject=str(locked.public_id),
                payload=_base_payload(
                    locked,
                    moment=moment,
                    lead_day=str(remaining),
                    return_day=return_calendar_day(locked).isoformat(),
                ),
            )
            published += 1
    if published:
        logger.info("inventory.return_due_soon published=%s", published)
    return published


def publish_overdue_agent_reminders(*, as_of: date | None = None) -> int:
    """Notify agents on an approved cadence while a return stays overdue."""
    sync_overdue_reservations()
    today = as_of or timezone.localdate()
    moment = timezone.now()
    published = 0
    escalation_days = _overdue_agent_days()
    candidates = overdue_queryset(
        InventoryReservation.objects.all(), now=moment
    ).order_by("pk")[:300]
    for reservation in candidates:
        overdue_days = days_overdue(reservation, today=today)
        if overdue_days not in escalation_days or overdue_days <= 0:
            continue
        with transaction.atomic():
            locked = _lock_reservation(reservation.pk)
            if locked is None or not is_overdue(locked, now=moment):
                continue
            if days_overdue(locked, today=today) != overdue_days:
                continue
            publish_event(
                "inventory.reservation.return_overdue",
                actor_id="system",
                subject=str(locked.public_id),
                payload=_base_payload(
                    locked,
                    moment=moment,
                    overdue_day=str(overdue_days),
                    return_day=return_calendar_day(locked).isoformat(),
                ),
            )
            published += 1
    if published:
        logger.info("inventory.return_overdue published=%s", published)
    return published


def publish_overdue_staff_escalations(*, as_of: date | None = None) -> int:
    """Escalate overdue returns to authorized office staff."""
    sync_overdue_reservations()
    today = as_of or timezone.localdate()
    moment = timezone.now()
    published = 0
    escalation_days = _overdue_staff_days()
    candidates = overdue_queryset(
        InventoryReservation.objects.all(), now=moment
    ).order_by("pk")[:300]
    for reservation in candidates:
        overdue_days = days_overdue(reservation, today=today)
        if overdue_days not in escalation_days or overdue_days <= 0:
            continue
        with transaction.atomic():
            locked = _lock_reservation(reservation.pk)
            if locked is None or not is_overdue(locked, now=moment):
                continue
            if days_overdue(locked, today=today) != overdue_days:
                continue
            staff_ids = operational_staff_ids(locked)
            if not staff_ids:
                continue
            publish_event(
                "inventory.reservation.return_overdue_staff",
                actor_id="system",
                subject=str(locked.public_id),
                payload={
                    **_base_payload(
                        locked,
                        moment=moment,
                        overdue_day=str(overdue_days),
                        return_day=return_calendar_day(locked).isoformat(),
                    ),
                    "staff_ids": [str(staff_id) for staff_id in staff_ids],
                },
            )
            published += 1
    if published:
        logger.info("inventory.return_overdue_staff published=%s", published)
    return published


def _days_since_status(reservation: InventoryReservation, *, today: date) -> int:
    moment_field = {
        ReservationStatus.LOST: reservation.lost_at,
        ReservationStatus.DAMAGED: reservation.damaged_at,
    }.get(reservation.status)
    if moment_field is None:
        return 0
    marked = timezone.localtime(moment_field).date()
    return (today - marked).days


def publish_lost_damaged_escalations(*, as_of: date | None = None) -> int:
    """Escalate lost/damaged reservations to office staff on an approved cadence."""
    today = as_of or timezone.localdate()
    moment = timezone.now()
    published = 0
    escalation_days = _lost_damaged_days()
    candidates = InventoryReservation.objects.filter(
        status__in=sorted(LOST_DAMAGED_ESCALATION_STATUSES)
    ).order_by("pk")[:300]
    for reservation in candidates:
        elapsed = _days_since_status(reservation, today=today)
        if elapsed not in escalation_days or elapsed < 0:
            continue
        with transaction.atomic():
            locked = _lock_reservation(reservation.pk)
            if locked is None or locked.status not in LOST_DAMAGED_ESCALATION_STATUSES:
                continue
            if _days_since_status(locked, today=today) != elapsed:
                continue
            staff_ids = operational_staff_ids(locked)
            if not staff_ids:
                continue
            publish_event(
                "inventory.reservation.lost_damaged_escalation",
                actor_id="system",
                subject=str(locked.public_id),
                payload={
                    **_base_payload(
                        locked,
                        moment=moment,
                        escalation_day=str(elapsed),
                        status=locked.status,
                    ),
                    "staff_ids": [str(staff_id) for staff_id in staff_ids],
                },
            )
            published += 1
    if published:
        logger.info("inventory.lost_damaged_escalation published=%s", published)
    return published


def publish_inventory_return_notifications(*, as_of: date | None = None) -> int:
    """Beat entrypoint: due-soon, overdue agent, staff escalation, lost/damaged."""
    total = 0
    total += publish_due_soon_reminders(as_of=as_of)
    total += publish_overdue_agent_reminders(as_of=as_of)
    total += publish_overdue_staff_escalations(as_of=as_of)
    total += publish_lost_damaged_escalations(as_of=as_of)
    return total
