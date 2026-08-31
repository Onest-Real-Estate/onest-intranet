"""Dashboard action items for overdue inventory reservations.

Agents see their own overdue checkouts. Authorized office staff see overdue
holds in scope they may operate on. Completion is derived from reservation
status — returned, completed, or cancelled rows are never emitted.
"""

from __future__ import annotations

from django.urls import reverse

from apps.inventory.models import InventoryReservation
from apps.inventory.overdue import is_overdue, overdue_queryset, return_calendar_day
from apps.inventory.reservation_administration import (
    can_approve_reservations,
    managed_reservation_queryset,
)
from apps.web.action_items.contract import (
    ActionItem,
    ActionPriority,
    ActionSourceContext,
    ActionType,
)

_ACTION_TYPE = ActionType.INVENTORY
_MAX_ROWS = 50


def _agent_items(context: ActionSourceContext) -> list[ActionItem]:
    user = context.user
    if getattr(user, "is_anonymous", False):
        return []
    rows = overdue_queryset(
        InventoryReservation.objects.for_owner(user), now=context.now
    ).order_by("ends_at", "pk")[:_MAX_ROWS]
    items: list[ActionItem] = []
    for reservation in rows:
        if not is_overdue(reservation, now=context.now):
            continue
        return_day = return_calendar_day(reservation)
        items.append(
            ActionItem(
                id=f"inventory_reservation:{reservation.public_id}",
                dedupe_key=f"inventory_reservation:{reservation.public_id}",
                title=f"Return {reservation.item_name}",
                type=_ACTION_TYPE,
                priority=ActionPriority.HIGH,
                due_at=reservation.ends_at,
                source_module="inventory",
                source_record_type="inventory_reservation",
                source_record_id=str(reservation.public_id),
                context=(
                    f"Overdue since {return_day.isoformat()} · {reservation.reference}"
                ),
                cta_label="Open reservation",
                cta_href=reverse(
                    "inventory_reservation_detail",
                    args=[str(reservation.public_id)],
                ),
                assignee_id=user.pk,
            )
        )
    return items


def _staff_items(context: ActionSourceContext) -> list[ActionItem]:
    user = context.user
    if getattr(user, "is_anonymous", False) or not can_approve_reservations(user):
        return []
    rows = overdue_queryset(
        managed_reservation_queryset(user),
        now=context.now,
    ).order_by("ends_at", "pk")[:_MAX_ROWS]
    items: list[ActionItem] = []
    for reservation in rows:
        if not is_overdue(reservation, now=context.now):
            continue
        owner = reservation.owner
        owner_name = owner.get_full_name() or owner.email
        return_day = return_calendar_day(reservation)
        items.append(
            ActionItem(
                id=f"inventory_reservation_staff:{reservation.public_id}",
                dedupe_key=f"inventory_reservation_staff:{reservation.public_id}",
                title=f"Overdue return · {reservation.item_name}",
                type=_ACTION_TYPE,
                priority=ActionPriority.HIGH,
                due_at=reservation.ends_at,
                source_module="inventory",
                source_record_type="inventory_reservation",
                source_record_id=str(reservation.public_id),
                context=(
                    f"{owner_name} · due {return_day.isoformat()} · "
                    f"{reservation.office_name}"
                ),
                cta_label="Open reservation",
                cta_href=reverse(
                    "admin_reservation_detail",
                    args=[str(reservation.public_id)],
                ),
                assignee_id=user.pk,
            )
        )
    return items


def collect_inventory_actions(context: ActionSourceContext) -> list[ActionItem]:
    return _agent_items(context) + _staff_items(context)
