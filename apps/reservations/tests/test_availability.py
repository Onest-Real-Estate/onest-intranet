from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from apps.reservations.availability import (
    AvailabilityWindow,
    availability_windows_for_date,
    resolve_wall_time,
    scheduled_windows_for_date,
)
from apps.reservations.models import SpaceAvailabilityException, WeeklyAvailability
from apps.reservations.taxonomy import (
    ExceptionKind,
    ExceptionVisibility,
    WallTimeBoundary,
    Weekday,
)
from apps.reservations.tests.factories import make_space


def test_weekly_schedule_resolves_in_office_timezone(seeded):
    space = make_space()
    WeeklyAvailability.objects.create(
        space=space,
        weekday=Weekday.MONDAY,
        starts_at=time(9),
        ends_at=time(17),
    )

    assert scheduled_windows_for_date(space, date(2026, 1, 5)) == [
        AvailabilityWindow(
            datetime(2026, 1, 5, 14, tzinfo=UTC),
            datetime(2026, 1, 5, 22, tzinfo=UTC),
        )
    ]


def test_exception_subtracts_a_half_open_block(seeded):
    space = make_space()
    WeeklyAvailability.objects.create(
        space=space,
        weekday=Weekday.MONDAY,
        starts_at=time(9),
        ends_at=time(17),
    )
    SpaceAvailabilityException.objects.create(
        space=space,
        kind=ExceptionKind.MAINTENANCE,
        starts_at=datetime(2026, 1, 5, 17, tzinfo=UTC),
        ends_at=datetime(2026, 1, 5, 18, tzinfo=UTC),
        reason="HVAC service",
        visibility=ExceptionVisibility.INTERNAL,
    )

    assert availability_windows_for_date(space, date(2026, 1, 5)) == [
        AvailabilityWindow(
            datetime(2026, 1, 5, 14, tzinfo=UTC),
            datetime(2026, 1, 5, 17, tzinfo=UTC),
        ),
        AvailabilityWindow(
            datetime(2026, 1, 5, 18, tzinfo=UTC),
            datetime(2026, 1, 5, 22, tzinfo=UTC),
        ),
    ]


def test_nonexistent_spring_wall_time_advances_to_first_valid_minute():
    resolved = resolve_wall_time(
        date(2026, 3, 8),
        time(2, 30),
        ZoneInfo("America/New_York"),
        boundary=WallTimeBoundary.START,
    )

    assert resolved.isoformat() == "2026-03-08T03:00:00-04:00"


def test_ambiguous_fall_wall_time_uses_earliest_start_and_latest_end():
    zone = ZoneInfo("America/New_York")
    start = resolve_wall_time(
        date(2026, 11, 1),
        time(1, 30),
        zone,
        boundary=WallTimeBoundary.START,
    )
    end = resolve_wall_time(
        date(2026, 11, 1),
        time(1, 30),
        zone,
        boundary=WallTimeBoundary.END,
    )

    assert start.astimezone(UTC) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert end.astimezone(UTC) == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
