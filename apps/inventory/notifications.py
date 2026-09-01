"""Inventory reservation notices and the resolver that keeps them honest.

Scheduled reminders publish audit events consumed by ``apps.notifications``.
The resolver re-checks scope and lifecycle state at read time so stale rows
fail closed without rewriting history.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from apps.inventory.models import InventoryReservation
from apps.inventory.notification_schedule import SOURCE_MODULE
from apps.inventory.overdue import is_overdue
from apps.inventory.reservation_administration import managed_reservation_queryset
from apps.inventory.reservation_taxonomy import ReservationStatus
from apps.notifications.sources import SourceResolution, register_resolver

logger = logging.getLogger("apps.inventory")

SOURCE_MODULE_KEY = SOURCE_MODULE


def resolve_inventory_notifications(
    user, notifications: Sequence
) -> dict[UUID, SourceResolution]:
    """Whether each notice still points at something this reader may open."""
    wanted = {str(n.source_record_id) for n in notifications if n.source_record_id}
    if not wanted:
        return {}

    agent_rows = InventoryReservation.objects.filter(
        owner=user,
        public_id__in=wanted,
    ).values_list("public_id", "reference", "status", "ends_at")
    visible_agent = {
        str(public_id): (reference, status, ends_at)
        for public_id, reference, status, ends_at in agent_rows
    }

    staff_visible: dict[str, tuple[str, str, object]] = {}
    try:
        staff_visible = {
            str(public_id): (reference, status, ends_at)
            for public_id, reference, status, ends_at in managed_reservation_queryset(
                user
            )
            .filter(public_id__in=wanted)
            .values_list("public_id", "reference", "status", "ends_at")
        }
    except Exception:
        staff_visible = {}

    resolved: dict[UUID, SourceResolution] = {}
    for notification in notifications:
        record_id = str(notification.source_record_id)
        event_key = str(getattr(notification, "event_key", "") or "")
        found = visible_agent.get(record_id) or staff_visible.get(record_id)
        if found is None:
            resolved[notification.public_id] = SourceResolution.unavailable()
            continue
        reference, status, ends_at = found
        reservation = InventoryReservation(
            status=status,
            ends_at=ends_at,
            reference=reference,
        )
        if event_key == "inventory.reservation.return_due_soon":
            if status != ReservationStatus.CHECKED_OUT or is_overdue(reservation):
                resolved[notification.public_id] = SourceResolution.unavailable()
                continue
        elif event_key in {
            "inventory.reservation.return_overdue",
            "inventory.reservation.return_overdue_staff",
        }:
            if not is_overdue(reservation):
                resolved[notification.public_id] = SourceResolution.unavailable()
                continue
        elif (
            event_key == "inventory.reservation.lost_damaged_escalation"
            and status
            not in {
                ReservationStatus.LOST,
                ReservationStatus.DAMAGED,
            }
        ):
            resolved[notification.public_id] = SourceResolution.unavailable()
            continue
        detail = f"{reference} · {status.replace('_', ' ')}"
        action_available = record_id in visible_agent or record_id in staff_visible
        resolved[notification.public_id] = SourceResolution(
            available=True,
            detail=detail,
            action_available=action_available,
        )
    return resolved


register_resolver(SOURCE_MODULE_KEY, resolve_inventory_notifications)
