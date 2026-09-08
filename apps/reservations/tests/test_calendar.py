from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.reservations.calendar import CalendarFilters, build_calendar
from apps.reservations.models import Amenity, SpaceAvailabilityException
from apps.reservations.taxonomy import (
    AmenityCategory,
    CalendarView,
    ExceptionKind,
    ExceptionVisibility,
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
from apps.user.tests.test_profile import completed_user

NOW = datetime(2026, 3, 1, 15, tzinfo=UTC)
MONDAY = date(2026, 3, 2)


def _viewer(email="viewer@example.com"):
    user = person(email, "fairfax-va")
    assign_role(user, "realtor", ScopeType.OFFICE, office("fairfax-va"))
    return user


def _room(name="Blue room", **fields):
    room = make_space(name=name, **fields)
    make_weekly_hours(room, weekday=0, starts_at=time(9), ends_at=time(12))
    return room


def test_calendar_projects_open_busy_and_buffer_safe_slots_without_private_titles(
    seeded,
):
    viewer = _viewer()
    other = _viewer("other@example.com")
    room = _room(buffer_after_minutes=15)
    make_reservation(
        space=room,
        owner=other,
        starts_at=datetime(2026, 3, 2, 15, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 16, tzinfo=UTC),
        purpose="Private acquisition discussion",
    )

    payload = build_calendar(
        user=viewer,
        filters=CalendarFilters(view=CalendarView.DAY, start_date=MONDAY),
        now=NOW,
    )
    day = payload["calendar"]["spaces"][0]["days"][0]

    assert day["openIntervals"] == [
        {
            "startsAt": "2026-03-02T14:00:00+00:00",
            "endsAt": "2026-03-02T17:00:00+00:00",
        }
    ]
    assert day["busyIntervals"][0]["label"] == "Busy"
    assert "Private acquisition" not in str(payload)
    starts = {slot["startsAt"] for slot in day["candidateSlots"]}
    assert "2026-03-02T14:45:00+00:00" not in starts
    assert "2026-03-02T16:00:00+00:00" in starts


def test_internal_block_reason_is_coarsened_but_public_reason_is_visible(seeded):
    viewer = _viewer()
    room = _room()
    SpaceAvailabilityException.objects.create(
        space=room,
        kind=ExceptionKind.MAINTENANCE,
        starts_at=datetime(2026, 3, 2, 14, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 14, 30, tzinfo=UTC),
        reason="Alarm vendor access code reset",
        visibility=ExceptionVisibility.INTERNAL,
    )
    SpaceAvailabilityException.objects.create(
        space=room,
        kind=ExceptionKind.CLOSURE,
        starts_at=datetime(2026, 3, 2, 16, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 17, tzinfo=UTC),
        reason="Office closes early",
        visibility=ExceptionVisibility.PUBLIC,
    )
    payload = build_calendar(
        user=viewer,
        filters=CalendarFilters(view=CalendarView.DAY, start_date=MONDAY),
        now=NOW,
    )
    labels = [
        item["label"]
        for item in payload["calendar"]["spaces"][0]["days"][0]["busyIntervals"]
    ]
    assert labels == ["Unavailable", "Office closes early"]
    assert "Alarm vendor" not in str(payload)


def test_filters_are_governed_and_combined(seeded):
    viewer = _viewer()
    screen = Amenity.objects.create(
        code="presentation-screen",
        name="Presentation screen",
        category=AmenityCategory.AUDIO_VISUAL,
    )
    matching = _room(capacity=12)
    matching.amenities.add(screen)
    _room(name="Small room", capacity=4)

    payload = build_calendar(
        user=viewer,
        filters=CalendarFilters(
            view=CalendarView.DAY,
            start_date=MONDAY,
            minimum_capacity=8,
            amenity_codes=("presentation-screen",),
        ),
        now=NOW,
    )
    assert [item["name"] for item in payload["calendar"]["spaces"]] == [matching.name]


def test_cross_office_selection_fails_without_explicit_scope(seeded):
    viewer = _viewer()
    with pytest.raises(PermissionDenied):
        build_calendar(
            user=viewer,
            filters=CalendarFilters(
                view=CalendarView.DAY,
                start_date=MONDAY,
                office_key="harrisburg",
            ),
            now=NOW,
        )


def test_calendar_range_is_bounded(seeded):
    viewer = _viewer()
    with pytest.raises(ValidationError):
        build_calendar(
            user=viewer,
            filters=CalendarFilters(
                view=CalendarView.WEEK,
                start_date=MONDAY + timedelta(days=400),
            ),
            now=NOW,
        )


def test_calendar_resolves_spring_dst_hours_in_the_office_timezone(seeded):
    viewer = _viewer()
    room = make_space(name="DST room")
    make_weekly_hours(room, weekday=6, starts_at=time(1), ends_at=time(3))

    payload = build_calendar(
        user=viewer,
        filters=CalendarFilters(
            view=CalendarView.DAY,
            start_date=date(2026, 3, 8),
        ),
        now=datetime(2026, 3, 7, 15, tzinfo=UTC),
    )

    assert payload["calendar"]["spaces"][0]["days"][0]["openIntervals"] == [
        {
            "startsAt": "2026-03-08T06:00:00+00:00",
            "endsAt": "2026-03-08T07:00:00+00:00",
        }
    ]


def test_no_office_payload_keeps_the_page_contract_stable(seeded):
    viewer = completed_user(email="unassigned@example.com", office=None)

    payload = build_calendar(
        user=viewer,
        filters=CalendarFilters(view=CalendarView.DAY, start_date=MONDAY),
        now=NOW,
    )

    assert payload["calendar"] is None
    assert payload["empty"]["kind"] == "no-office"
    assert payload["filterOptions"] == {
        "spaceTypes": [],
        "amenities": [],
        "rooms": [],
    }
    assert payload["capabilities"] == {
        "canBook": False,
        "canChangeOffice": False,
    }


def test_calendar_query_count_does_not_scale_per_space(seeded):
    viewer = _viewer()
    for index in range(8):
        _room(name=f"Room {index}")
    with CaptureQueriesContext(connection) as captured:
        build_calendar(
            user=viewer,
            filters=CalendarFilters(view=CalendarView.WEEK, start_date=MONDAY),
            now=NOW,
        )
    assert len(captured) <= 22


def test_closed_days_expose_no_open_intervals_or_candidate_slots(seeded):
    viewer = _viewer()
    _room()

    payload = build_calendar(
        user=viewer,
        filters=CalendarFilters(view=CalendarView.WEEK, start_date=MONDAY),
        now=NOW,
    )
    days = payload["calendar"]["spaces"][0]["days"]

    assert [day["isClosed"] for day in days] == [False, *([True] * 6)]
    for day in days[1:]:
        assert day["openIntervals"] == []
        assert day["availableIntervals"] == []
        assert day["candidateSlots"] == []


def test_local_midnight_keeps_each_block_on_a_single_local_day(seeded):
    viewer = _viewer()
    room = _room()
    SpaceAvailabilityException.objects.create(
        space=room,
        kind=ExceptionKind.CLOSURE,
        starts_at=datetime(2026, 3, 3, 4, tzinfo=UTC),
        ends_at=datetime(2026, 3, 3, 5, tzinfo=UTC),
        reason="Monday late-night deep clean",
        visibility=ExceptionVisibility.PUBLIC,
    )
    SpaceAvailabilityException.objects.create(
        space=room,
        kind=ExceptionKind.CLOSURE,
        starts_at=datetime(2026, 3, 3, 5, tzinfo=UTC),
        ends_at=datetime(2026, 3, 3, 6, tzinfo=UTC),
        reason="Tuesday overnight network cutover",
        visibility=ExceptionVisibility.PUBLIC,
    )

    payload = build_calendar(
        user=viewer,
        filters=CalendarFilters(view=CalendarView.WEEK, start_date=MONDAY),
        now=NOW,
    )
    days = payload["calendar"]["spaces"][0]["days"]

    assert [item["label"] for item in days[0]["busyIntervals"]] == [
        "Monday late-night deep clean"
    ]
    assert [item["label"] for item in days[1]["busyIntervals"]] == [
        "Tuesday overnight network cutover"
    ]


def test_calendar_keeps_the_whole_fall_back_hour_in_the_office_timezone(seeded):
    viewer = _viewer()
    room = make_space(name="Fall back room")
    make_weekly_hours(room, weekday=6, starts_at=time(1), ends_at=time(3))

    payload = build_calendar(
        user=viewer,
        filters=CalendarFilters(view=CalendarView.DAY, start_date=date(2026, 11, 1)),
        now=datetime(2026, 10, 31, 15, tzinfo=UTC),
    )

    assert payload["calendar"]["spaces"][0]["days"][0]["openIntervals"] == [
        {
            "startsAt": "2026-11-01T05:00:00+00:00",
            "endsAt": "2026-11-01T08:00:00+00:00",
        }
    ]
