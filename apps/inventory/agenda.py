"""Inventory pickup/return windows as My Day agenda rows.

Only the signed-in owner's capacity-consuming reservations appear. Cancelled
and completed holds are omitted by the queryset — cancelled events must never
be emitted into the agenda contract.
"""

from __future__ import annotations

from django.urls import reverse

from apps.inventory.models import InventoryReservation
from apps.inventory.reservation_taxonomy import (
    CAPACITY_CONSUMING_STATES,
    ReservationStatus,
)
from apps.web.my_day.contract import (
    AgendaEvent,
    EventPriority,
    EventSource,
    EventSourceContext,
)

MAX_ROWS = 50


def collect_inventory_events(context: EventSourceContext) -> list[AgendaEvent]:
    user = context.user
    if getattr(user, "is_anonymous", False):
        return []

    rows = (
        InventoryReservation.objects.for_owner(user)
        .filter(
            status__in=sorted(CAPACITY_CONSUMING_STATES),
            starts_at__lt=context.window_end,
            ends_at__gt=context.window_start,
        )
        .order_by("starts_at", "pk")[:MAX_ROWS]
    )

    events: list[AgendaEvent] = []
    for reservation in rows:
        if reservation.status == ReservationStatus.CANCELLED:
            continue
        title = f"Pickup: {reservation.item_name}"
        if reservation.quantity > 1:
            title = f"{title} ×{reservation.quantity}"
        events.append(
            AgendaEvent(
                id=f"inventory_reservation:{reservation.public_id}",
                dedupe_key=f"inventory_reservation:{reservation.public_id}",
                source=EventSource.INVENTORY,
                title=title,
                start_at=reservation.starts_at,
                end_at=reservation.ends_at,
                all_day=True,
                local_date=reservation.starts_at.astimezone(context.timezone).date(),
                location=reservation.office_name
                or reservation.storage_location_snapshot,
                priority=EventPriority.NORMAL,
                # The status is real information here — checked out and
                # overdue change what the reader must do. The reference code is
                # not: it is for a support conversation, and on a six-row card
                # it displaces the line that says what the item is for.
                context=reservation.status_label,
                cta_label="Open reservation",
                cta_href=reverse(
                    "inventory_reservation_detail",
                    args=[str(reservation.public_id)],
                ),
                source_module="inventory",
                source_record_type="inventory_reservation",
                source_record_id=str(reservation.public_id),
            )
        )
    return events
