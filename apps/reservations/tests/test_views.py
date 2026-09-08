from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone

from apps.reservations.models import Reservation
from apps.reservations.tests.factories import (
    assign_role,
    make_occupancy,
    make_space,
    make_weekly_hours,
    office,
    person,
)
from apps.user.roles import ScopeType


def _inertia_page(response):
    return json.loads(response.content)


def _booker():
    user = person("agent@example.com", "fairfax-va")
    assign_role(user, "realtor", ScopeType.OFFICE, office("fairfax-va"))
    return user


def _future_slot():
    zone = ZoneInfo("America/New_York")
    local_day = timezone.now().astimezone(zone).date() + timedelta(days=2)
    starts_at = datetime.combine(local_day, time(10), zone).astimezone(UTC)
    return local_day, starts_at, starts_at + timedelta(hours=1)


def _scheduled_room(local_day):
    room = make_space()
    make_weekly_hours(
        room, weekday=local_day.weekday(), starts_at=time(9), ends_at=time(17)
    )
    return room


def test_calendar_page_is_permission_protected_bounded_and_no_store(client, seeded):
    actor = _booker()
    local_day, _, _ = _future_slot()
    _scheduled_room(local_day)
    client.force_login(actor)

    response = client.get(
        reverse("room_availability"),
        {"date": local_day.isoformat(), "view": "day"},
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store, max-age=0"
    page = _inertia_page(response)
    assert page["component"] == "RoomAvailability"
    assert page["props"]["calendar"]["view"] == "day"
    assert page["props"]["office"]["key"] == "fairfax-va"


def test_calendar_denies_a_user_without_booking_permission(client, seeded):
    actor = person("limited@example.com", "fairfax-va")
    client.force_login(actor)

    response = client.get(reverse("room_availability"))

    assert response.status_code == 403


def test_calendar_does_not_disclose_foreign_office(client, seeded):
    actor = _booker()
    client.force_login(actor)

    response = client.get(reverse("room_availability"), {"office": "harrisburg"})

    assert response.status_code == 403


def test_json_booking_post_revalidates_and_is_idempotent(client, seeded):
    actor = _booker()
    local_day, starts_at, ends_at = _future_slot()
    room = _scheduled_room(local_day)
    client.force_login(actor)
    body = {
        "space": str(room.public_id),
        "startsAt": starts_at.isoformat(),
        "endsAt": ends_at.isoformat(),
        "purpose": "Team planning",
        "attendeeCount": 4,
        "submissionKey": "browser-submit-1",
    }

    response = client.post(
        reverse("room_reservation_create"),
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )
    repeated = client.post(
        reverse("room_reservation_create"),
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 302
    assert repeated.status_code == 302
    assert Reservation.objects.filter(submission_key="browser-submit-1").count() == 1


def test_stale_calendar_submission_returns_private_safe_conflict(client, seeded):
    actor = _booker()
    local_day, starts_at, ends_at = _future_slot()
    room = _scheduled_room(local_day)
    make_occupancy(room, starts_at=starts_at, ends_at=ends_at)
    client.force_login(actor)

    response = client.post(
        reverse("room_reservation_create"),
        data=json.dumps(
            {
                "space": str(room.public_id),
                "startsAt": starts_at.isoformat(),
                "endsAt": ends_at.isoformat(),
                "purpose": "Client meeting",
                "submissionKey": "stale-submit",
            }
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 409
    assert b"That time is no longer available" in response.content
    assert b"competing" not in response.content.lower()


def test_booking_validation_errors_keep_camel_case_inertia_field_names(client, seeded):
    actor = _booker()
    local_day, starts_at, ends_at = _future_slot()
    room = _scheduled_room(local_day)
    client.force_login(actor)

    response = client.post(
        reverse("room_reservation_create"),
        data=json.dumps(
            {
                "space": str(room.public_id),
                "startsAt": starts_at.isoformat(),
                "endsAt": ends_at.isoformat(),
                "purpose": "Client meeting",
                "attendeeCount": room.capacity + 1,
                "submissionKey": "capacity-validation",
            }
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    page = _inertia_page(response)
    assert "attendeeCount" in page["props"]["errors"]["fields"]
    assert "attendee_count" not in page["props"]["errors"]["fields"]
