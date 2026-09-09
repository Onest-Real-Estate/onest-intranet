"""Inventory holds as unified reservation summaries.

Only the signed-in owner's rows. Pickup/return windows are **date-shaped**: the
reader collects an item during a day, not at an instant, so these rows are
all-day and carry their local date. Rendering them as a clock time is how a
Friday pickup becomes Thursday night for a reader one zone west.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import InventoryReservation
from apps.inventory.policy import agent_may_cancel
from apps.inventory.reservation_taxonomy import STATUS_LABELS, ReservationStatus
from apps.web.my_reservations.contract import (
    DisplayStatus,
    ReservationAction,
    ReservationSource,
    ReservationSummary,
)

MAX_ROWS = 200

#: Inventory lifecycle → normalized vocabulary. Mapped explicitly so a new
#: domain state cannot silently inherit someone else's meaning.
DISPLAY_BY_STATUS: dict[str, str] = {
    ReservationStatus.REQUESTED: DisplayStatus.AWAITING_APPROVAL,
    ReservationStatus.CONFIRMED: DisplayStatus.CONFIRMED,
    ReservationStatus.READY_FOR_PICKUP: DisplayStatus.CONFIRMED,
    ReservationStatus.CHECKED_OUT: DisplayStatus.IN_PROGRESS,
    ReservationStatus.OVERDUE: DisplayStatus.OVERDUE,
    ReservationStatus.RETURNED: DisplayStatus.COMPLETED,
    ReservationStatus.COMPLETED: DisplayStatus.COMPLETED,
    ReservationStatus.CANCELLED: DisplayStatus.CANCELLED,
    ReservationStatus.DENIED: DisplayStatus.DENIED,
    ReservationStatus.LOST: DisplayStatus.NEEDS_ATTENTION,
    ReservationStatus.DAMAGED: DisplayStatus.NEEDS_ATTENTION,
}


def _actions(
    reservation: InventoryReservation, *, now: datetime
) -> tuple[ReservationAction, ...]:
    # The domain owns the rule; asking it here keeps the button and the service
    # from drifting apart, and the service checks it again on arrival.
    if not agent_may_cancel(
        status=reservation.status, starts_at=reservation.starts_at, now=now
    ):
        return ()
    return (
        ReservationAction(
            key="cancel",
            label="Cancel hold",
            href=reverse("my_reservation_cancel", args=[reservation.public_id]),
            method="post",
            destructive=True,
            expected_status=reservation.status,
        ),
    )


def collect_inventory_reservations(user, *, now: datetime | None = None):
    """Every inventory hold owned by ``user``. Never accepts an owner selector."""
    if getattr(user, "is_anonymous", False):
        return []
    moment = now or timezone.now()
    rows = (
        InventoryReservation.objects.for_owner(user)
        .select_related("item", "office")
        .order_by("-starts_at", "-pk")[:MAX_ROWS]
    )

    summaries: list[ReservationSummary] = []
    for reservation in rows:
        display = DISPLAY_BY_STATUS.get(reservation.status)
        if display is None:
            continue
        zone = ZoneInfo(reservation.office.timezone)
        subtitle = f"Quantity {reservation.quantity}" if reservation.quantity else ""
        summaries.append(
            ReservationSummary(
                source=ReservationSource.INVENTORY,
                source_id=f"{ReservationSource.INVENTORY}:{reservation.public_id}",
                public_id=str(reservation.public_id),
                reference=reservation.reference,
                title=reservation.item_name,
                subtitle=subtitle,
                office_name=reservation.office_name,
                timezone=reservation.office.timezone,
                starts_at=reservation.starts_at,
                ends_at=reservation.ends_at,
                display_status=display,
                source_status=reservation.status,
                status_label=str(STATUS_LABELS.get(reservation.status, "")),
                purpose=reservation.purpose,
                quantity=reservation.quantity,
                instructions=reservation.instructions_snapshot,
                contact=reservation.storage_location_snapshot,
                all_day=True,
                local_date=reservation.starts_at.astimezone(zone).date(),
                detail_href=reverse(
                    "my_reservation_detail", args=[reservation.public_id]
                ),
                actions=_actions(reservation, now=moment),
            )
        )
    return summaries
