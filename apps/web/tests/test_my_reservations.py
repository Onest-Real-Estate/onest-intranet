"""Unified reservation aggregation: self-only scope, mapping, order, isolation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.inventory.reservation_taxonomy import ReservationStatus as InventoryStatus
from apps.reservations.taxonomy import ReservationStatus as RoomStatus
from apps.reservations.tests.factories import (
    assign_role,
    make_reservation,
    make_space,
    make_weekly_hours,
    office,
    person,
)
from apps.user.roles import ScopeType
from apps.web.my_reservations.contract import (
    DisplayStatus,
    ReservationBucket,
    ReservationSource,
)
from apps.web.my_reservations.registry import collect_reservations


def _page(response):
    return json.loads(response.content)


def _agent(email="agent@example.com", office_slug="fairfax-va"):
    user = person(email, office_slug)
    assign_role(user, "realtor", ScopeType.OFFICE, office(office_slug))
    return user


def _future_slot(days=3):
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


# --- self-only scope --------------------------------------------------------


def test_the_feed_returns_only_the_signed_in_users_rows(db):
    mine = _agent()
    theirs = _agent("other@example.com")
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(space=room, owner=mine, starts_at=starts_at, ends_at=ends_at)
    make_reservation(
        space=room,
        owner=theirs,
        starts_at=starts_at + timedelta(hours=2),
        ends_at=ends_at + timedelta(hours=2),
        reference="OTHER-1",
    )

    feed = collect_reservations(mine)

    assert [row.reference for row in feed.summaries] != []
    assert all(row.reference != "OTHER-1" for row in feed.summaries)


def test_the_route_accepts_no_owner_selector(client, db):
    mine = _agent()
    theirs = _agent("other@example.com")
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(
        space=room,
        owner=theirs,
        starts_at=starts_at,
        ends_at=ends_at,
        reference="OTHER-2",
    )
    client.force_login(mine)

    response = client.get(
        reverse("my_reservations"),
        {"owner": theirs.pk, "user": theirs.pk, "office": "harrisburg"},
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 200
    assert "OTHER-2" not in response.content.decode()


# --- normalization ----------------------------------------------------------


def test_a_room_booking_keeps_its_domain_status_beside_the_normalized_one(db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)

    row = collect_reservations(owner).summaries[0]

    assert row.source == ReservationSource.ROOM
    assert row.display_status == DisplayStatus.CONFIRMED
    assert row.source_status == RoomStatus.CONFIRMED
    assert row.status_label
    assert row.source_id == f"room:{row.public_id}"
    assert row.all_day is False


def test_every_room_status_maps_explicitly(db):
    from apps.reservations.summaries import DISPLAY_BY_STATUS

    assert set(DISPLAY_BY_STATUS) == {code for code, _ in RoomStatus.choices}


def test_every_inventory_status_maps_explicitly(db):
    from apps.inventory.reservation_taxonomy import STATUS_CODES
    from apps.inventory.summaries import DISPLAY_BY_STATUS

    assert set(DISPLAY_BY_STATUS) == set(STATUS_CODES)


def test_an_inventory_hold_is_all_day_and_carries_its_local_date(db):
    from apps.inventory.summaries import DISPLAY_BY_STATUS

    # The mapping is what makes a pickup window date-shaped rather than an
    # instant; assert it rather than constructing the whole inventory graph.
    assert DISPLAY_BY_STATUS[InventoryStatus.CHECKED_OUT] == DisplayStatus.IN_PROGRESS
    assert DISPLAY_BY_STATUS[InventoryStatus.OVERDUE] == DisplayStatus.OVERDUE


# --- bucketing and ordering -------------------------------------------------


def test_cancelled_rows_leave_the_time_axis(db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    booking = make_reservation(
        space=room, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    booking.status = RoomStatus.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at"])

    feed = collect_reservations(owner)

    assert feed.counts[ReservationBucket.CANCELLED] == 1
    assert feed.counts[ReservationBucket.UPCOMING] == 0


def test_upcoming_reads_soonest_first_with_a_stable_tiebreak(db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(
        space=room,
        owner=owner,
        starts_at=starts_at + timedelta(hours=2),
        ends_at=ends_at + timedelta(hours=2),
        reference="LATER",
    )
    make_reservation(
        space=room,
        owner=owner,
        starts_at=starts_at,
        ends_at=ends_at,
        reference="SOONER",
    )

    references = [row.reference for row in collect_reservations(owner).summaries]

    assert references == ["SOONER", "LATER"]


def test_ordering_is_deterministic_across_repeated_calls(db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    for index in range(4):
        make_reservation(
            space=room,
            owner=owner,
            starts_at=starts_at + timedelta(hours=index * 2),
            ends_at=ends_at + timedelta(hours=index * 2),
            reference=f"REF-{index}",
        )

    first = [row.source_id for row in collect_reservations(owner).summaries]
    second = [row.source_id for row in collect_reservations(owner).summaries]

    assert first == second


# --- partial provider failure ----------------------------------------------


def test_one_failing_source_does_not_blank_the_other(db, monkeypatch):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)

    def explode(*args, **kwargs):
        raise RuntimeError("inventory is down")

    monkeypatch.setattr(
        "apps.inventory.summaries.collect_inventory_reservations", explode
    )

    feed = collect_reservations(owner)

    assert len(feed.summaries) == 1
    assert feed.failed_sources == (ReservationSource.INVENTORY,)
    assert feed.is_degraded


def test_the_page_names_the_source_that_failed(client, db, monkeypatch):
    owner = _agent()
    client.force_login(owner)

    def explode(*args, **kwargs):
        raise RuntimeError("inventory is down")

    monkeypatch.setattr(
        "apps.inventory.summaries.collect_inventory_reservations", explode
    )

    response = client.get(reverse("my_reservations"), HTTP_X_INERTIA="true")

    degraded = _page(response)["props"]["degraded"]
    assert degraded is not None
    assert degraded["failedSources"] == ["Equipment"]


# --- actions delegate -------------------------------------------------------


def test_a_cancel_action_is_offered_only_while_the_domain_allows_it(db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day, cancellation_cutoff_minutes=0)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)

    row = collect_reservations(owner).summaries[0]

    assert [action.key for action in row.actions] == ["cancel"]
    assert row.actions[0].expected_status == RoomStatus.CONFIRMED


def test_no_cancel_is_offered_once_the_cutoff_has_passed(db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    # A cutoff wider than the lead time closes the window immediately.
    room = _room(local_day, cancellation_cutoff_minutes=60 * 24 * 30)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)

    row = collect_reservations(owner).summaries[0]

    assert row.actions == ()


def test_cancelling_delegates_to_the_room_service(client, db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day, cancellation_cutoff_minutes=0)
    booking = make_reservation(
        space=room, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    client.force_login(owner)

    response = client.post(
        reverse("my_reservation_cancel", args=[booking.public_id]),
        data=json.dumps({"expectedStatus": RoomStatus.CONFIRMED}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code in {302, 303}
    booking.refresh_from_db()
    assert booking.status == RoomStatus.CANCELLED


def test_a_stale_cancel_is_refused(client, db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day, cancellation_cutoff_minutes=0)
    booking = make_reservation(
        space=room, owner=owner, starts_at=starts_at, ends_at=ends_at
    )
    client.force_login(owner)

    response = client.post(
        reverse("my_reservation_cancel", args=[booking.public_id]),
        data=json.dumps({"expectedStatus": RoomStatus.REQUESTED}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code in {302, 303}
    booking.refresh_from_db()
    assert booking.status == RoomStatus.CONFIRMED


def test_a_user_cannot_cancel_someone_elses_reservation(client, db):
    mine = _agent()
    theirs = _agent("other@example.com")
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day, cancellation_cutoff_minutes=0)
    booking = make_reservation(
        space=room, owner=theirs, starts_at=starts_at, ends_at=ends_at
    )
    client.force_login(mine)

    response = client.post(
        reverse("my_reservation_cancel", args=[booking.public_id]),
        data=json.dumps({"expectedStatus": RoomStatus.CONFIRMED}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 404
    booking.refresh_from_db()
    assert booking.status == RoomStatus.CONFIRMED


# --- view surface -----------------------------------------------------------


def test_the_page_requires_authentication(client, db):
    response = client.get(reverse("my_reservations"))

    assert response.status_code in {302, 403}


def test_tabs_and_filters_come_from_the_url(client, db):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    make_reservation(space=room, owner=owner, starts_at=starts_at, ends_at=ends_at)
    client.force_login(owner)

    response = client.get(
        reverse("my_reservations"),
        {"tab": ReservationBucket.PAST, "source": ReservationSource.ROOM},
        HTTP_X_INERTIA="true",
    )

    props = _page(response)["props"]
    assert props["filters"]["tab"] == ReservationBucket.PAST
    assert props["filters"]["source"] == ReservationSource.ROOM
    # The booking is upcoming, so the Past tab is empty while the count stands.
    assert props["reservations"] == []
    assert props["counts"][ReservationBucket.UPCOMING] == 1


def test_an_unknown_tab_or_status_falls_back_instead_of_erroring(client, db):
    client.force_login(_agent())

    response = client.get(
        reverse("my_reservations"),
        {"tab": "../../etc", "status": "made-up", "source": "nonsense"},
        HTTP_X_INERTIA="true",
    )

    props = _page(response)["props"]["filters"]
    assert props["tab"] == ReservationBucket.UPCOMING
    assert props["status"] == ""
    assert props["source"] == ""


def test_the_feed_is_collected_in_a_bounded_number_of_queries(
    db, django_assert_num_queries
):
    owner = _agent()
    local_day, starts_at, ends_at = _future_slot()
    room = _room(local_day)
    for index in range(6):
        make_reservation(
            space=room,
            owner=owner,
            starts_at=starts_at + timedelta(hours=index * 2),
            ends_at=ends_at + timedelta(hours=index * 2),
            reference=f"Q-{index}",
        )

    with django_assert_num_queries(2):
        feed = collect_reservations(owner)
        assert len(feed.summaries) == 6


@pytest.mark.parametrize(
    "tab", [ReservationBucket.UPCOMING, ReservationBucket.PAST, "calendar"]
)
def test_every_tab_renders(client, db, tab):
    client.force_login(_agent())

    response = client.get(
        reverse("my_reservations"), {"tab": tab}, HTTP_X_INERTIA="true"
    )

    assert response.status_code == 200
    assert _page(response)["component"] == "MyReservations"
