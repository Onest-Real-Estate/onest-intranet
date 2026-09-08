"""Room administration views: the role/scope/action matrix at the HTTP edge."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.reservations.models import Space
from apps.reservations.taxonomy import ReservationStatus, SpaceStatus
from apps.reservations.tests.factories import (
    assign_role,
    make_reservation,
    make_space,
    make_weekly_hours,
    office,
    person,
)
from apps.user.roles import ScopeType


def _page(response):
    return json.loads(response.content)


def _admin(email="branch@example.com", office_slug="fairfax-va"):
    user = person(email, office_slug)
    assign_role(user, "branch_manager", ScopeType.OFFICE, office(office_slug))
    return user


def _agent(email="agent@example.com", office_slug="fairfax-va"):
    user = person(email, office_slug)
    assign_role(user, "realtor", ScopeType.OFFICE, office(office_slug))
    return user


def _future_slot():
    zone = ZoneInfo("America/New_York")
    local_day = timezone.now().astimezone(zone).date() + timedelta(days=3)
    starts_at = datetime.combine(local_day, time(10), zone).astimezone(UTC)
    return local_day, starts_at, starts_at + timedelta(hours=1)


def _room(local_day=None, **fields):
    room = make_space(**fields)
    weekday = local_day.weekday() if local_day else 0
    make_weekly_hours(room, weekday=weekday, starts_at=time(9), ends_at=time(17))
    return room


def _edit_payload(space: Space, **overrides):
    payload = {
        "name": space.name,
        "spaceType": space.space_type,
        "capacity": space.capacity,
        "description": space.description,
        "location": space.location,
        "accessInstructions": "",
        "displayOrder": space.display_order,
        "minimumDurationMinutes": space.minimum_duration_minutes,
        "maximumDurationMinutes": space.maximum_duration_minutes,
        "bookingHorizonDays": space.booking_horizon_days,
        "minimumNoticeMinutes": space.minimum_notice_minutes,
        "bufferBeforeMinutes": space.buffer_before_minutes,
        "bufferAfterMinutes": space.buffer_after_minutes,
        "cancellationCutoffMinutes": space.cancellation_cutoff_minutes,
        "requiresApproval": space.requires_approval,
        "isReservable": space.is_reservable,
    }
    payload.update(overrides)
    return payload


# --- read surface -----------------------------------------------------------


def test_the_list_renders_only_rooms_inside_the_actors_hierarchy(client, seeded):
    actor = _admin()
    mine = _room(name="Fairfax boardroom")
    make_space(owner_slug="charlottesville-va", name="Someone else's room")
    client.force_login(actor)

    response = client.get(reverse("space_administration"), HTTP_X_INERTIA="true")

    assert response.status_code == 200
    page = _page(response)
    assert page["component"] == "SpaceAdministration"
    names = [item["name"] for item in page["props"]["spaces"]]
    assert names == [mine.name]


def test_an_agent_cannot_open_the_administration_list(client, seeded):
    client.force_login(_agent())

    response = client.get(reverse("space_administration"), HTTP_X_INERTIA="true")

    assert response.status_code == 403


def test_the_list_filters_by_type_status_and_capacity(client, seeded):
    actor = _admin()
    _room(name="Large room", capacity=20)
    _room(name="Small room", capacity=4)
    client.force_login(actor)

    response = client.get(
        reverse("space_administration"), {"capacity": 10}, HTTP_X_INERTIA="true"
    )

    names = [item["name"] for item in _page(response)["props"]["spaces"]]
    assert names == ["Large room"]


def test_the_workspace_hides_access_instructions_without_the_grant(client, seeded):
    actor = _admin()
    room = _room(access_instructions="Door code 4321")
    client.force_login(actor)

    response = client.get(
        reverse("space_administration_workspace", args=[room.public_id]),
        HTTP_X_INERTIA="true",
    )

    page = _page(response)
    assert page["component"] == "SpaceAdministrationWorkspace"
    capabilities = page["props"]["capabilities"]
    if not capabilities["canViewSensitive"]:
        assert page["props"]["space"]["accessInstructions"] == ""
        assert "4321" not in response.content.decode()


def test_a_room_outside_scope_is_not_found_rather_than_forbidden(client, seeded):
    actor = _admin()
    foreign = make_space(owner_slug="charlottesville-va", name="Foreign room")
    client.force_login(actor)

    response = client.get(
        reverse("space_administration_workspace", args=[foreign.public_id]),
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 404


# --- write surface ----------------------------------------------------------


def test_an_agent_cannot_reach_any_write_endpoint(client, seeded):
    room = _room()
    client.force_login(_agent())

    for name, payload in (
        ("space_administration_update", _edit_payload(room)),
        ("space_administration_activation", {"active": "", "reason": "no"}),
        ("space_administration_retire", {"reason": "no"}),
        ("space_administration_schedule", {"intervals": "[]"}),
    ):
        response = client.post(
            reverse(name, args=[room.public_id]), payload, HTTP_X_INERTIA="true"
        )
        assert response.status_code == 403, name


def test_a_json_edit_saves_and_redirects(client, seeded):
    actor = _admin()
    room = _room()
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_update", args=[room.public_id]),
        data=json.dumps(_edit_payload(room, name="Harbor boardroom")),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code in {302, 303}
    room.refresh_from_db()
    assert room.name == "Harbor boardroom"


def test_a_stale_edit_is_rejected_at_the_edge(client, seeded):
    actor = _admin()
    room = _room()
    client.force_login(actor)
    stale = (room.updated_at - timedelta(minutes=5)).isoformat()

    response = client.post(
        reverse("space_administration_update", args=[room.public_id]),
        data=json.dumps(_edit_payload(room, name="Clobbered", expectedUpdatedAt=stale)),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    room.refresh_from_db()
    assert room.name != "Clobbered"


def test_a_change_that_strands_bookings_returns_409_with_an_impact_preview(
    client, seeded
):
    actor = _admin()
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day, minimum_duration_minutes=30)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_update", args=[room.public_id]),
        data=json.dumps(_edit_payload(room, minimumDurationMinutes=180)),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 409
    impact = _page(response)["props"]["impact"]
    assert impact["total"] == 1
    assert impact["bookings"][0]["reason"]
    room.refresh_from_db()
    assert room.minimum_duration_minutes == 30


def test_acknowledging_the_impact_applies_the_change(client, seeded):
    actor = _admin()
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day, minimum_duration_minutes=30)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_update", args=[room.public_id]),
        data=json.dumps(
            _edit_payload(room, minimumDurationMinutes=180, acknowledgeImpact=True)
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code in {302, 303}
    room.refresh_from_db()
    assert room.minimum_duration_minutes == 180


def test_deactivation_requires_a_reason_at_the_edge(client, seeded):
    actor = _admin()
    room = _room()
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_activation", args=[room.public_id]),
        data=json.dumps({"active": False, "reason": ""}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    room.refresh_from_db()
    assert room.status == SpaceStatus.ACTIVE


def test_replacing_the_schedule_accepts_a_json_interval_list(client, seeded):
    actor = _admin()
    room = _room()
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_schedule", args=[room.public_id]),
        data=json.dumps(
            {
                "intervals": [
                    {"weekday": 1, "startsAt": "08:00", "endsAt": "12:00"},
                    {"weekday": 1, "startsAt": "13:00", "endsAt": "17:00"},
                ]
            }
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code in {302, 303}
    assert room.weekly_availability.count() == 2


def test_a_block_over_a_booking_is_refused_with_409(client, seeded):
    actor = _admin()
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_block_create", args=[room.public_id]),
        data=json.dumps(
            {
                "kind": "maintenance",
                "startsAt": starts_at.isoformat(),
                "endsAt": ends_at.isoformat(),
                "reason": "Alarm service",
                "visibility": "internal",
            }
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 409


def test_a_booking_move_re_scopes_the_destination(client, seeded):
    actor = _admin()
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    origin = _room(local_day)
    foreign = make_space(owner_slug="charlottesville-va", name="Foreign room")
    booking = make_reservation(
        space=origin, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_booking_move", args=[booking.public_id]),
        data=json.dumps({"destination": str(foreign.public_id), "reason": "Anywhere"}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 404
    booking.refresh_from_db()
    assert booking.space_id == origin.pk


def test_a_booking_move_within_scope_succeeds(client, seeded):
    actor = _admin()
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    origin = _room(local_day)
    destination = _room(local_day, name="Cedar room")
    booking = make_reservation(
        space=origin, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_booking_move", args=[booking.public_id]),
        data=json.dumps(
            {"destination": str(destination.public_id), "reason": "Projector failure"}
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code in {302, 303}
    booking.refresh_from_db()
    assert booking.space_id == destination.pk


def test_an_admin_cancellation_requires_a_reason_and_releases_the_slot(client, seeded):
    actor = _admin()
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    booking = make_reservation(
        space=room, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    client.force_login(actor)

    blank = client.post(
        reverse("space_administration_booking_cancel", args=[booking.public_id]),
        data=json.dumps({"reason": ""}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )
    assert blank.status_code == 422

    response = client.post(
        reverse("space_administration_booking_cancel", args=[booking.public_id]),
        data=json.dumps({"reason": "Room flooded"}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code in {302, 303}
    booking.refresh_from_db()
    assert booking.status == ReservationStatus.CANCELLED


@pytest.mark.parametrize(
    "route",
    [
        "space_administration_update",
        "space_administration_activation",
        "space_administration_schedule",
    ],
)
def test_write_endpoints_reject_get(client, seeded, route):
    actor = _admin()
    room = _room()
    client.force_login(actor)

    response = client.get(reverse(route, args=[room.public_id]))

    assert response.status_code in {403, 405}


def test_creating_a_room_requires_an_office_the_actor_administers(client, seeded):
    actor = _admin()
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_create"),
        data=json.dumps(
            {
                "office": "charlottesville-va",
                "name": "Reached across scope",
                "spaceType": "meeting_room",
                "capacity": 6,
            }
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 403
    assert not Space.objects.filter(name="Reached across scope").exists()


def test_creating_a_room_in_scope_succeeds(client, seeded):
    actor = _admin()
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_create"),
        data=json.dumps(
            {
                "office": "fairfax-va",
                "name": "New boardroom",
                "spaceType": "conference_room",
                "capacity": 10,
            }
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code in {302, 303}
    assert Space.objects.filter(name="New boardroom").exists()


def test_bookings_from_other_users_are_listed_without_their_purpose(client, seeded):
    actor = _admin()
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(
        space=room,
        owner=owner,
        starts_at=starts_at,
        ends_at=ends_at,
        purpose="Confidential listing strategy",
    )
    client.force_login(actor)

    response = client.get(
        reverse("space_administration_workspace", args=[room.public_id]),
        HTTP_X_INERTIA="true",
    )

    body = response.content.decode()
    assert "Confidential listing strategy" not in body
    assert _page(response)["props"]["upcomingBookings"][0]["reference"]


def test_reservation_rows_are_scoped_to_the_actors_hierarchy(client, seeded):
    actor = _admin()
    owner = _agent("cville@example.com", "charlottesville-va")
    foreign_room = make_space(owner_slug="charlottesville-va", name="Foreign room")
    make_weekly_hours(foreign_room, weekday=0, starts_at=time(9), ends_at=time(17))
    _, starts_at, ends_at = _future_slot()
    booking = make_reservation(
        space=foreign_room, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    client.force_login(actor)

    response = client.post(
        reverse("space_administration_booking_cancel", args=[booking.public_id]),
        data=json.dumps({"reason": "Reaching across scope"}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 404
    booking.refresh_from_db()
    assert booking.status != ReservationStatus.CANCELLED
