"""Scoped administration services: permission, scope, impact, and overlap safety."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.reservations.administration import (
    ImpactRequiresAcknowledgement,
    StaleEdit,
    cancel_reservation_as_admin,
    future_impact,
    move_reservation,
    remove_availability_exception,
    replace_weekly_schedule,
    set_space_activation,
    update_availability_exception,
    update_space,
)
from apps.reservations.models import Occupancy
from apps.reservations.services import create_availability_exception
from apps.reservations.taxonomy import (
    ExceptionKind,
    ExceptionVisibility,
    ReservationStatus,
    SpaceStatus,
)
from apps.reservations.tests.factories import (
    assign_role,
    make_reservation,
    make_space,
    make_weekly_hours,
    office,
    person,
)
from apps.user.roles import ScopeType

NOW = datetime(2026, 3, 1, 15, tzinfo=UTC)
NINE = datetime(2026, 3, 2, 14, tzinfo=UTC)
TEN = NINE + timedelta(hours=1)
ELEVEN = NINE + timedelta(hours=2)


def _admin(email="branch@example.com", office_slug="fairfax-va"):
    user = person(email, office_slug)
    assign_role(user, "branch_manager", ScopeType.OFFICE, office(office_slug))
    return user


def _agent(email="agent@example.com", office_slug="fairfax-va"):
    user = person(email, office_slug)
    assign_role(user, "realtor", ScopeType.OFFICE, office(office_slug))
    return user


def _room(**fields):
    room = make_space(**fields)
    make_weekly_hours(room, weekday=0, starts_at=time(9), ends_at=time(17))
    return room


# --- identity and policy edits ---------------------------------------------


def test_update_space_edits_policy_and_audits_the_change(seeded):
    actor = _admin()
    room = _room()

    updated, report = update_space(
        actor=actor,
        space=room,
        name="Harbor boardroom",
        minimum_notice_minutes=45,
    )

    assert updated.name == "Harbor boardroom"
    assert updated.minimum_notice_minutes == 45
    assert report.is_empty


def test_an_agent_cannot_reach_the_write_path(seeded):
    actor = _agent()
    room = _room()

    with pytest.raises(PermissionDenied):
        update_space(actor=actor, space=room, name="Renamed by an agent")


def test_an_admin_cannot_edit_a_room_outside_their_hierarchy(seeded):
    actor = _admin(office_slug="fairfax-va")
    foreign = make_space(owner_slug="charlottesville-va", name="Foreign room")

    with pytest.raises(PermissionDenied):
        update_space(actor=actor, space=foreign, name="Reached across scope")


def test_unknown_fields_are_refused_rather_than_silently_written(seeded):
    actor = _admin()
    room = _room()

    with pytest.raises(ValidationError) as caught:
        update_space(actor=actor, space=room, owner_office_id=999)

    assert "cannot be edited here" in str(caught.value)


def test_a_stale_edit_is_detected_before_it_overwrites(seeded):
    actor = _admin()
    room = _room()
    loaded_at = room.updated_at

    update_space(actor=actor, space=room, name="First writer wins")

    with pytest.raises(StaleEdit):
        update_space(
            actor=actor,
            space=room,
            expected_updated_at=loaded_at,
            name="Second writer clobbers",
        )


def test_a_policy_change_that_strands_a_booking_needs_acknowledgement(seeded):
    actor = _admin()
    owner = _agent()
    room = _room(minimum_duration_minutes=30)
    make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises(ImpactRequiresAcknowledgement) as caught:
        update_space(actor=actor, space=room, minimum_duration_minutes=120, now=NOW)

    assert caught.value.report.total == 1
    assert "Shorter than the new minimum" in caught.value.report.bookings[0].reason

    updated, report = update_space(
        actor=actor,
        space=room,
        minimum_duration_minutes=120,
        acknowledge_impact=True,
        now=NOW,
    )
    assert updated.minimum_duration_minutes == 120
    assert report.total == 1


def test_a_harmless_policy_change_does_not_ask_for_acknowledgement(seeded):
    actor = _admin()
    owner = _agent()
    room = _room(minimum_duration_minutes=30)
    make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    _, report = update_space(
        actor=actor, space=room, minimum_duration_minutes=15, now=NOW
    )

    assert report.is_empty


# --- activation and retirement ---------------------------------------------


def test_deactivation_requires_a_reason_and_shows_the_bookings_it_strands(seeded):
    actor = _admin()
    owner = _agent()
    room = _room()
    make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises(ValidationError):
        set_space_activation(actor=actor, space=room, active=False)

    with pytest.raises(ImpactRequiresAcknowledgement) as caught:
        set_space_activation(
            actor=actor, space=room, active=False, reason="Ceiling repair", now=NOW
        )
    assert caught.value.report.total == 1

    updated, report = set_space_activation(
        actor=actor,
        space=room,
        active=False,
        reason="Ceiling repair",
        acknowledge_impact=True,
        now=NOW,
    )
    assert updated.status == SpaceStatus.INACTIVE
    assert updated.is_reservable is False
    assert report.total == 1


def test_reactivation_needs_no_reason_and_strands_nothing(seeded):
    actor = _admin()
    room = _room()
    set_space_activation(
        actor=actor,
        space=room,
        active=False,
        reason="Temporary",
        acknowledge_impact=True,
    )

    updated, report = set_space_activation(actor=actor, space=room, active=True)

    assert updated.status == SpaceStatus.ACTIVE
    assert report.is_empty


# --- schedules --------------------------------------------------------------


def test_replacing_a_schedule_refuses_overlapping_intervals(seeded):
    actor = _admin()
    room = _room()

    with pytest.raises(ValidationError) as caught:
        replace_weekly_schedule(
            actor=actor,
            space=room,
            intervals=[(0, time(9), time(12)), (0, time(11), time(15))],
        )

    assert "Overlapping intervals" in str(caught.value)


def test_narrowing_hours_surfaces_the_bookings_that_fall_outside(seeded):
    actor = _admin()
    owner = _agent()
    room = _room()
    make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises(ImpactRequiresAcknowledgement) as caught:
        replace_weekly_schedule(
            actor=actor, space=room, intervals=[(0, time(13), time(17))], now=NOW
        )

    assert caught.value.report.total == 1
    assert "outside the new opening hours" in caught.value.report.bookings[0].reason


def test_a_schedule_change_that_keeps_every_booking_valid_applies_cleanly(seeded):
    actor = _admin()
    owner = _agent()
    room = _room()
    make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    updated, report = replace_weekly_schedule(
        actor=actor, space=room, intervals=[(0, time(8), time(18))], now=NOW
    )

    assert report.is_empty
    assert updated.weekly_availability.count() == 1


def test_schedule_editing_needs_the_schedule_permission(seeded):
    actor = _agent()
    room = _room()

    with pytest.raises(PermissionDenied):
        replace_weekly_schedule(
            actor=actor, space=room, intervals=[(0, time(9), time(17))]
        )


# --- maintenance blocks -----------------------------------------------------


def _block(room, actor, **fields):
    """Create a block the way the workspace does, through the service."""
    return create_availability_exception(
        actor=actor,
        space=room,
        kind=fields.pop("kind", ExceptionKind.MAINTENANCE),
        starts_at=fields.pop("starts_at", NINE),
        ends_at=fields.pop("ends_at", TEN),
        reason=fields.pop("reason", "Alarm service"),
        visibility=fields.pop("visibility", ExceptionVisibility.INTERNAL),
    )


def test_moving_a_block_keeps_its_ledger_row_in_step(seeded):
    actor = _admin()
    room = _room()
    block = _block(room, actor)

    updated = update_availability_exception(
        actor=actor, exception=block, starts_at=TEN, ends_at=ELEVEN
    )

    updated.refresh_from_db()
    assert updated.occupancy.starts_at == TEN
    assert updated.occupancy.ends_at == ELEVEN


def test_removing_a_block_releases_the_time_it_held(seeded):
    actor = _admin()
    room = _room()
    block = _block(room, actor)
    occupancy_id = block.occupancy_id

    remove_availability_exception(actor=actor, exception=block)

    assert not Occupancy.objects.filter(pk=occupancy_id).exists()
    assert not Occupancy.objects.overlapping(
        space_id=room.pk, starts_at=NINE, ends_at=TEN
    ).exists()


def test_a_block_cannot_be_created_over_a_protected_booking(seeded):
    actor = _admin()
    owner = _agent()
    room = _room()
    make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises(ValidationError):
        _block(room, actor, starts_at=NINE, ends_at=TEN)


# --- reservation operations -------------------------------------------------


def test_moving_a_booking_to_another_room_is_audited_and_overlap_safe(seeded):
    actor = _admin()
    owner = _agent()
    origin = _room()
    destination = _room(name="Cedar room")
    booking = make_reservation(space=origin, owner=owner, starts_at=NINE, ends_at=TEN)

    moved = move_reservation(
        actor=actor,
        reservation=booking,
        destination=destination,
        reason="Projector failure",
    )

    assert moved.space_id == destination.pk
    assert moved.space_name == destination.name
    assert Occupancy.objects.overlapping(
        space_id=destination.pk, starts_at=NINE, ends_at=TEN
    ).exists()
    assert not Occupancy.objects.overlapping(
        space_id=origin.pk, starts_at=NINE, ends_at=TEN
    ).exists()


def test_a_move_requires_a_reason(seeded):
    actor = _admin()
    owner = _agent()
    origin = _room()
    destination = _room(name="Cedar room")
    booking = make_reservation(space=origin, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises(ValidationError):
        move_reservation(
            actor=actor, reservation=booking, destination=destination, reason="  "
        )


def test_a_move_into_an_occupied_room_is_refused(seeded):
    actor = _admin()
    owner = _agent()
    other = _agent("other@example.com")
    origin = _room()
    destination = _room(name="Cedar room")
    booking = make_reservation(space=origin, owner=owner, starts_at=NINE, ends_at=TEN)
    make_reservation(space=destination, owner=other, starts_at=NINE, ends_at=TEN)

    with pytest.raises(ValidationError):
        move_reservation(
            actor=actor,
            reservation=booking,
            destination=destination,
            reason="Projector failure",
        )


def test_a_move_cannot_cross_into_another_office(seeded):
    actor = _admin()
    owner = _agent()
    origin = _room()
    foreign = make_space(owner_slug="charlottesville-va", name="Foreign room")
    make_weekly_hours(foreign, weekday=0, starts_at=time(9), ends_at=time(17))
    booking = make_reservation(space=origin, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises((ValidationError, PermissionDenied)):
        move_reservation(
            actor=actor, reservation=booking, destination=foreign, reason="Anywhere"
        )


def test_a_move_is_refused_when_the_destination_is_closed_then(seeded):
    actor = _admin()
    owner = _agent()
    origin = _room()
    destination = make_space(name="Cedar room")
    make_weekly_hours(destination, weekday=0, starts_at=time(15), ends_at=time(17))
    booking = make_reservation(space=origin, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises(ValidationError) as caught:
        move_reservation(
            actor=actor,
            reservation=booking,
            destination=destination,
            reason="Projector failure",
        )

    assert "not open" in str(caught.value)


def test_an_admin_cancellation_releases_capacity_and_needs_a_reason(seeded):
    actor = _admin()
    owner = _agent()
    room = _room()
    booking = make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises(ValidationError):
        cancel_reservation_as_admin(actor=actor, reservation=booking, reason="")

    cancelled = cancel_reservation_as_admin(
        actor=actor, reservation=booking, reason="Room flooded"
    )

    assert cancelled.status == ReservationStatus.CANCELLED
    assert cancelled.cancelled_by_id == actor.pk
    assert not Occupancy.objects.overlapping(
        space_id=room.pk, starts_at=NINE, ends_at=TEN
    ).exists()


def test_an_agent_cannot_cancel_another_agents_booking(seeded):
    actor = _agent("nosy@example.com")
    owner = _agent()
    room = _room()
    booking = make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    with pytest.raises(PermissionDenied):
        cancel_reservation_as_admin(
            actor=actor, reservation=booking, reason="I want the room"
        )


# --- impact reporting -------------------------------------------------------


def test_future_impact_ignores_bookings_that_already_started(seeded):
    owner = _agent()
    room = _room()
    make_reservation(space=room, owner=owner, starts_at=NINE, ends_at=TEN)

    after = future_impact(room, now=ELEVEN)

    assert after.is_empty
