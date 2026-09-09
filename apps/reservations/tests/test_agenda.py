"""Room bookings as My Day rows: self-only, trimmed, and honest about state."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.reservations.agenda import collect_room_events
from apps.reservations.taxonomy import ReservationStatus
from apps.reservations.tests.factories import (
    assign_role,
    make_reservation,
    make_space,
    make_weekly_hours,
    office,
    person,
)
from apps.user.roles import ScopeType
from apps.user.services.role_assignments import get_effective_access
from apps.web.my_day.contract import EventSource, EventSourceContext, EventStatus
from apps.web.my_day.registry import EVENT_SOURCE_DEFINITIONS


def _agent(email="agent@example.com", office_slug="fairfax-va"):
    user = person(email, office_slug)
    assign_role(user, "realtor", ScopeType.OFFICE, office(office_slug))
    return user


def _context(user, *, now=None):
    moment = now or timezone.now()
    return EventSourceContext(
        user=user,
        access=get_effective_access(user),
        now=moment,
        window_start=moment - timedelta(days=1),
        window_end=moment + timedelta(days=7),
        timezone=ZoneInfo("UTC"),
    )


def _future_slot(days=2):
    zone = ZoneInfo("America/New_York")
    local_day = timezone.now().astimezone(zone).date() + timedelta(days=days)
    starts_at = datetime.combine(local_day, time(10), zone).astimezone(UTC)
    return local_day, starts_at, starts_at + timedelta(hours=1)


def _room(local_day, **fields):
    room = make_space(**fields)
    make_weekly_hours(
        room, weekday=local_day.weekday(), starts_at=time(9), ends_at=time(17)
    )
    return room


def test_the_room_source_is_registered_and_live(seeded):
    definition = next(
        item
        for item in EVENT_SOURCE_DEFINITIONS
        if item.key == EventSource.ROOM_BOOKING
    )

    assert definition.available is True
    assert definition.collector is not None


def test_a_booking_appears_as_a_timed_row_pointing_at_the_unified_page(seeded):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day, name="Harbor boardroom")
    make_reservation(
        space=room,
        owner=owner,
        starts_at=starts_at,
        ends_at=ends_at,
        purpose="Buyer consultation",
    )

    events = collect_room_events(_context(owner))

    assert len(events) == 1
    row = events[0]
    assert row.source == EventSource.ROOM_BOOKING
    assert row.title == "Harbor boardroom"
    # A room booking is an instant, unlike an inventory pickup window.
    assert row.all_day is False
    assert "/hub/my-reservations/" in row.cta_href


def test_the_row_carries_the_purpose_rather_than_a_reference_code(seeded):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    reservation = make_reservation(
        space=room,
        owner=owner,
        starts_at=starts_at,
        ends_at=ends_at,
        purpose="Buyer consultation",
        reference="ROOM-NOISE1",
    )

    row = collect_room_events(_context(owner))[0]

    assert row.context == "Buyer consultation"
    # The reference belongs in a support conversation, not on a six-row card.
    assert reservation.reference not in row.context


def test_a_confirmed_booking_claims_no_status_chip(seeded):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)

    row = collect_room_events(_context(owner))[0]

    # The payload layer strips a "Confirmed" label; restating it in the row
    # would put the default state straight back on the card.
    assert row.status == EventStatus.CONFIRMED


def test_a_booking_awaiting_approval_reads_as_tentative(seeded):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day, requires_approval=True)
    booking = make_reservation(
        space=room, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    booking.status = ReservationStatus.REQUESTED
    booking.approved_at = None
    booking.approved_by = None
    booking.save(update_fields=["status", "approved_at", "approved_by"])

    row = collect_room_events(_context(owner))[0]

    assert row.status == EventStatus.TENTATIVE


def test_a_cancelled_booking_never_reaches_the_agenda(seeded):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    booking = make_reservation(
        space=room, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    booking.status = ReservationStatus.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at"])

    assert collect_room_events(_context(owner)) == []


def test_only_the_readers_own_bookings_appear(seeded):
    mine = _agent()
    theirs = _agent("other@example.com")
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(
        space=room,
        owner=theirs,
        starts_at=starts_at,
        ends_at=ends_at,
        reference="OTHER-AGENDA",
    )

    assert collect_room_events(_context(mine)) == []


def test_a_booking_outside_the_window_is_not_collected(seeded):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot(days=2)
    room = _room(local_day)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)

    # A window that closes before the booking starts must return nothing.
    moment = timezone.now()
    narrow = EventSourceContext(
        user=owner,
        access=get_effective_access(owner),
        now=moment,
        window_start=moment,
        window_end=moment + timedelta(hours=1),
        timezone=ZoneInfo("UTC"),
    )

    assert collect_room_events(narrow) == []
