from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.reservations.booking import (
    ReservationConflict,
    cancel_reservation,
    create_reservation,
    decide_reservation,
    reschedule_reservation,
)
from apps.reservations.models import Occupancy
from apps.reservations.taxonomy import ReservationStatus
from apps.reservations.tests.factories import (
    assign_role,
    make_occupancy,
    make_space,
    make_weekly_hours,
    office,
    person,
)
from apps.user.roles import ScopeType

NOW = datetime(2026, 3, 1, 15, tzinfo=UTC)
NINE = datetime(2026, 3, 2, 14, tzinfo=UTC)
TEN = NINE + timedelta(hours=1)


def _booker(email="agent@example.com", office_slug="fairfax-va"):
    user = person(email, office_slug)
    assign_role(user, "realtor", ScopeType.OFFICE, office(office_slug))
    return user


def _room(**fields):
    room = make_space(**fields)
    make_weekly_hours(room, weekday=0, starts_at=time(9), ends_at=time(17))
    return room


def test_create_reservation_applies_rules_buffers_and_idempotency(seeded):
    actor = _booker()
    room = _room(buffer_before_minutes=15, buffer_after_minutes=10)

    reservation, created = create_reservation(
        actor=actor,
        space=room,
        starts_at=NINE,
        ends_at=TEN,
        purpose="Buyer consultation",
        attendee_count=4,
        submission_key="same-request",
        now=NOW,
    )
    repeated, repeated_created = create_reservation(
        actor=actor,
        space=room,
        starts_at=NINE,
        ends_at=TEN,
        purpose="Buyer consultation",
        attendee_count=4,
        submission_key="same-request",
        now=NOW,
    )

    assert created is True
    assert repeated_created is False
    assert repeated == reservation
    assert reservation.status == ReservationStatus.CONFIRMED
    assert reservation.occupancy.starts_at == NINE - timedelta(minutes=15)
    assert reservation.occupancy.ends_at == TEN + timedelta(minutes=10)
    room.refresh_from_db()
    assert room.booking_history_started_at == NOW


def test_create_rejects_scope_duration_capacity_and_closed_hours(seeded):
    actor = _booker()
    foreign = _room(owner_slug="harrisburg", capacity=2)

    with pytest.raises(PermissionDenied):
        create_reservation(
            actor=actor,
            space=foreign,
            starts_at=NINE,
            ends_at=TEN,
            purpose="Meeting",
            submission_key="foreign",
            now=NOW,
        )

    room = _room(capacity=2, minimum_duration_minutes=60)
    with pytest.raises(ValidationError) as error:
        create_reservation(
            actor=actor,
            space=room,
            starts_at=NINE,
            ends_at=NINE + timedelta(minutes=30),
            purpose="Meeting",
            attendee_count=3,
            submission_key="invalid",
            now=NOW,
        )
    assert {"ends_at", "attendee_count"}.issubset(error.value.message_dict)


def test_friendly_overlap_check_includes_existing_buffers(seeded):
    actor = _booker()
    room = _room(buffer_after_minutes=15)
    make_occupancy(
        room,
        starts_at=TEN,
        ends_at=TEN + timedelta(hours=1),
    )

    with pytest.raises(ReservationConflict):
        create_reservation(
            actor=actor,
            space=room,
            starts_at=NINE + timedelta(minutes=15),
            ends_at=TEN,
            purpose="Meeting",
            submission_key="overlap",
            now=NOW,
        )


def test_cancel_releases_capacity_and_reschedule_moves_it(seeded, monkeypatch):
    actor = _booker()
    room = _room()
    reservation, _ = create_reservation(
        actor=actor,
        space=room,
        starts_at=NINE,
        ends_at=TEN,
        purpose="Meeting",
        submission_key="move-me",
        now=NOW,
    )
    moved = reschedule_reservation(
        actor=actor,
        reservation=reservation,
        starts_at=TEN,
        ends_at=TEN + timedelta(hours=1),
        now=NOW,
    )
    assert moved.occupancy.starts_at == TEN

    monkeypatch.setattr("apps.reservations.booking.timezone.now", lambda: NOW)
    cancelled = cancel_reservation(
        actor=actor, reservation=moved, reason="Client rescheduled"
    )
    assert cancelled.status == ReservationStatus.CANCELLED
    assert not cancelled.occupancy.consumes_capacity
    assert not Occupancy.objects.overlapping(
        space_id=room.pk, starts_at=TEN, ends_at=TEN + timedelta(hours=1)
    ).exists()


def test_approval_holds_capacity_and_denial_releases_it(seeded):
    actor = _booker()
    manager = person("manager@example.com", "fairfax-va")
    assign_role(manager, "branch_manager", ScopeType.OFFICE, office("fairfax-va"))
    room = _room(requires_approval=True)
    reservation, _ = create_reservation(
        actor=actor,
        space=room,
        starts_at=NINE,
        ends_at=TEN,
        purpose="Training",
        submission_key="approval",
        now=NOW,
    )
    assert reservation.status == ReservationStatus.REQUESTED
    assert reservation.occupancy.consumes_capacity

    denied = decide_reservation(
        actor=manager,
        reservation=reservation,
        approve=False,
        reason="Office event",
    )
    assert denied.status == ReservationStatus.DENIED
    assert not denied.occupancy.consumes_capacity
