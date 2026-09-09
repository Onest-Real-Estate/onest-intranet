"""Room bookings as unified reservation summaries.

Only the signed-in owner's rows. The mapping here is one-directional on purpose:
this module turns a room lifecycle into the normalized vocabulary, and nothing
turns it back. Every action points at a room endpoint that re-authorizes and
re-validates on arrival.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.urls import reverse
from django.utils import timezone

from apps.reservations.models import Reservation
from apps.reservations.taxonomy import ReservationStatus
from apps.web.my_reservations.contract import (
    DisplayStatus,
    ReservationAction,
    ReservationSource,
    ReservationSummary,
)

MAX_ROWS = 200

#: Room lifecycle → normalized vocabulary. Every domain code is mapped
#: explicitly; an unmapped code is a bug, not a default.
DISPLAY_BY_STATUS: dict[str, str] = {
    ReservationStatus.REQUESTED: DisplayStatus.AWAITING_APPROVAL,
    ReservationStatus.CONFIRMED: DisplayStatus.CONFIRMED,
    ReservationStatus.COMPLETED: DisplayStatus.COMPLETED,
    ReservationStatus.CANCELLED: DisplayStatus.CANCELLED,
    ReservationStatus.DENIED: DisplayStatus.DENIED,
}

#: Owner self-service cancel is legal only from these states. The booking
#: service checks this again, plus the space's cancellation cutoff.
OWNER_CANCELABLE: frozenset[str] = frozenset(
    {ReservationStatus.REQUESTED, ReservationStatus.CONFIRMED}
)


def _actions(
    reservation: Reservation, *, now: datetime
) -> tuple[ReservationAction, ...]:
    if reservation.status not in OWNER_CANCELABLE:
        return ()
    cutoff = reservation.starts_at - timedelta(
        minutes=reservation.space.cancellation_cutoff_minutes
    )
    if now >= cutoff:
        # Past the cutoff an owner cannot cancel without an override they do not
        # hold. Offering the button anyway would be a promise the service breaks.
        return ()
    return (
        ReservationAction(
            key="cancel",
            label="Cancel booking",
            href=reverse("my_reservation_cancel", args=[reservation.public_id]),
            method="post",
            destructive=True,
            expected_status=reservation.status,
        ),
    )


def collect_room_reservations(user, *, now: datetime | None = None):
    """Every room booking owned by ``user``. Never accepts an owner selector."""
    if getattr(user, "is_anonymous", False):
        return []
    moment = now or timezone.now()
    rows = (
        Reservation.objects.for_owner(user)
        .select_related("space", "space__owner_office", "office")
        .order_by("-starts_at", "-pk")[:MAX_ROWS]
    )

    summaries: list[ReservationSummary] = []
    for reservation in rows:
        display = DISPLAY_BY_STATUS.get(reservation.status)
        if display is None:
            continue
        summaries.append(
            ReservationSummary(
                source=ReservationSource.ROOM,
                source_id=f"{ReservationSource.ROOM}:{reservation.public_id}",
                public_id=str(reservation.public_id),
                reference=reservation.reference,
                title=reservation.space_name,
                subtitle=reservation.space.get_space_type_display(),
                office_name=reservation.office_name,
                timezone=reservation.office.timezone,
                starts_at=reservation.starts_at,
                ends_at=reservation.ends_at,
                display_status=display,
                source_status=reservation.status,
                status_label=str(ReservationStatus(reservation.status).label),
                purpose=reservation.purpose,
                instructions=reservation.instructions_snapshot,
                detail_href=reverse(
                    "my_reservation_detail", args=[reservation.public_id]
                ),
                actions=_actions(reservation, now=moment),
            )
        )
    return summaries
