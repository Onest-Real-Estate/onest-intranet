"""Room bookings as My Day agenda rows.

Only the signed-in owner's capacity-holding bookings appear. A cancelled or
denied booking is not an obligation and must never reach the agenda contract —
the queryset excludes it rather than the loop, so it cannot leak through a later
edit here.

Unlike an inventory pickup window, a room booking is a timed instant: it has a
real start and end on the clock, so it is emitted as a timed row.
"""

from __future__ import annotations

from django.urls import reverse

from apps.reservations.booking import CAPACITY_STATUSES
from apps.reservations.models import Reservation
from apps.reservations.taxonomy import ReservationStatus
from apps.web.my_day.contract import (
    AgendaEvent,
    EventPriority,
    EventSource,
    EventSourceContext,
    EventStatus,
)

MAX_ROWS = 50


def collect_room_events(context: EventSourceContext) -> list[AgendaEvent]:
    user = context.user
    if getattr(user, "is_anonymous", False):
        return []

    rows = (
        Reservation.objects.for_owner(user)
        .filter(
            status__in=sorted(CAPACITY_STATUSES),
            starts_at__lt=context.window_end,
            ends_at__gt=context.window_start,
        )
        .select_related("space", "office")
        .order_by("starts_at", "pk")[:MAX_ROWS]
    )

    events: list[AgendaEvent] = []
    for reservation in rows:
        events.append(
            AgendaEvent(
                id=f"room_reservation:{reservation.public_id}",
                dedupe_key=f"room_reservation:{reservation.public_id}",
                source=EventSource.ROOM_BOOKING,
                title=reservation.space_name,
                start_at=reservation.starts_at,
                end_at=reservation.ends_at,
                location=reservation.office_name,
                priority=EventPriority.NORMAL,
                # A booking awaiting approval is not yet a commitment, and the
                # card renders that as a chip. A confirmed one carries no chip
                # at all — the payload layer strips the default state, and
                # restating it here would put it straight back.
                status=(
                    EventStatus.TENTATIVE
                    if reservation.status == ReservationStatus.REQUESTED
                    else EventStatus.CONFIRMED
                ),
                # The supporting line answers "what is this?", not "which record
                # is this?". A reference code is for support conversations, and
                # on an agenda row it crowds out the only line that helps the
                # reader recognise their own meeting. The purpose is the owner's
                # own text and they are the only reader of this agenda.
                context=reservation.purpose,
                cta_label="Open reservation",
                cta_href=reverse(
                    "my_reservation_detail", args=[str(reservation.public_id)]
                ),
                source_module="reservations",
                source_record_type="room_reservation",
                source_record_id=str(reservation.public_id),
            )
        )
    return events
