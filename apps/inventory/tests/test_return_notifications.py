"""Inventory return reminder schedule, producers, and stale suppression."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.inventory.models import InventoryReservation
from apps.inventory.notification_schedule import (
    publish_due_soon_reminders,
    publish_overdue_agent_reminders,
)
from apps.inventory.overdue import days_overdue, days_until_return, is_overdue
from apps.inventory.reservation_common import ActorContext
from apps.inventory.reservation_lifecycle import reservation_version, transition
from apps.inventory.reservation_taxonomy import (
    ReservationAction,
    ReservationPermission,
    ReservationStatus,
)
from apps.inventory.reservations import create_reservation
from apps.inventory.taxonomy import (
    ItemAvailabilityState,
    ItemCategory,
    ItemCondition,
    TrackingMode,
)
from apps.notifications.models import Notification
from apps.notifications.producers import (
    EVENT_PRODUCERS,
    inventory_return_due_soon,
    inventory_return_overdue_staff,
    notifications_for_event,
)
from apps.notifications.service import deliver_many
from apps.user.models import Office
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str = "fairfax-va") -> Office:
    return Office.objects.get(slug=slug)


def agent(email: str = "agent@example.com", slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def manager(email: str = "manager@example.com", slug: str = "fairfax-va"):
    user = completed_user(email=email, office=office(slug))
    approve = Permission.objects.get(
        content_type__app_label="inventory", codename="approve_reservations"
    )
    view = Permission.objects.get(
        content_type__app_label="web", codename="view_reservations"
    )
    user.user_permissions.add(approve, view)
    return user


def actor(user, *extra: str) -> ActorContext:
    perms = set(user.get_all_permissions())
    perms.update(extra)
    return ActorContext(user=user, permissions=frozenset(perms))


def make_item(name: str = "Kit"):
    from apps.inventory.models import InventoryItem

    return InventoryItem.objects.create(
        owner_office=office(),
        name=name,
        category=ItemCategory.OTHER,
        tracking_mode=TrackingMode.POOLED,
        condition=ItemCondition.GOOD,
        availability_state=ItemAvailabilityState.AVAILABLE,
        total_quantity=3,
    )


def future_dates(start_offset: int = 3, length_days: int = 2):
    today = timezone.localdate()
    pickup = today + timedelta(days=start_offset)
    while pickup.weekday() >= 5:
        pickup += timedelta(days=1)
    return_day = pickup + timedelta(days=length_days - 1)
    while return_day.weekday() >= 5:
        return_day += timedelta(days=1)
    return pickup.isoformat(), return_day.isoformat()


def checked_out_reservation(seeded, *, owner=None, admin=None):
    owner = owner or agent()
    admin = admin or manager()
    item = make_item()
    pickup, return_day = future_dates()
    reservation, _ = create_reservation(
        actor=actor(owner),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    reservation = transition(
        actor=actor(admin, ReservationPermission.APPROVE, ReservationPermission.VIEW),
        reservation=reservation,
        action=ReservationAction.MARK_READY.value,
        expected_version=reservation_version(reservation),
        expected_status=reservation.status,
    )
    reservation = transition(
        actor=actor(admin, ReservationPermission.APPROVE, ReservationPermission.VIEW),
        reservation=reservation,
        action=ReservationAction.CHECK_OUT.value,
        expected_version=reservation_version(reservation),
        expected_status=reservation.status,
    )
    return reservation, owner, admin


def _ends_at_for_return_day(return_day):
    exclusive = return_day + timedelta(days=1)
    return timezone.make_aware(datetime.combine(exclusive, time.min))


def _envelope(name: str, payload: dict) -> EventEnvelope:
    return EventEnvelope(
        id=uuid4(),
        name=name,
        version=1,
        occurred_at=timezone.now(),
        actor_id="system",
        subject=payload.get("reservation_public_id", ""),
        organization_id="",
        correlation_id=None,
        causation_id=None,
        payload=payload,
    )


def _set_return_day(reservation: InventoryReservation, return_day) -> None:
    starts_at = _ends_at_for_return_day(return_day - timedelta(days=2))
    ends_at = _ends_at_for_return_day(return_day)
    InventoryReservation.objects.filter(pk=reservation.pk).update(
        starts_at=starts_at,
        ends_at=ends_at,
    )


@pytest.mark.django_db
def test_inventory_notification_events_registered():
    for key in (
        "inventory.reservation.return_due_soon",
        "inventory.reservation.return_overdue",
        "inventory.reservation.return_overdue_staff",
        "inventory.reservation.lost_damaged_escalation",
    ):
        assert key in EVENT_PRODUCERS


@pytest.mark.django_db
def test_due_soon_dedupes_per_lead_day(seeded):
    reservation_id = str(uuid4())
    envelope = _envelope(
        "inventory.reservation.return_due_soon",
        {
            "reservation_public_id": reservation_id,
            "office_id": "1",
            "owner_id": "42",
            "lead_day": "1",
            "policy_version": "1",
        },
    )
    [request] = inventory_return_due_soon(envelope)
    assert "lead:day:1" in request.dedupe_key
    assert request.recipient_id == 42
    assert request.action_key == "open_inventory_reservation"


@pytest.mark.django_db
def test_overdue_staff_notice_includes_staff_suffix(seeded, settings):
    settings.INVENTORY_NOTIFICATION_POLICY_VERSION = 1
    reservation_id = str(uuid4())
    envelope = _envelope(
        "inventory.reservation.return_overdue_staff",
        {
            "reservation_public_id": reservation_id,
            "office_id": "1",
            "owner_id": "42",
            "overdue_day": "3",
            "policy_version": "1",
            "staff_ids": ["7", "9"],
        },
    )
    requests = inventory_return_overdue_staff(envelope)
    assert len(requests) == 2
    assert {row.recipient_id for row in requests} == {7, 9}
    assert all(":staff:" in row.dedupe_key for row in requests)
    assert all(row.action_key == "open_admin_reservation" for row in requests)


@pytest.mark.django_db
def test_publish_due_soon_skips_non_checked_out(seeded, settings):
    settings.INVENTORY_RETURN_DUE_SOON_DAYS = (1,)
    reservation, owner, _admin = checked_out_reservation(seeded)
    today = timezone.localdate()
    return_day = today + timedelta(days=1)
    _set_return_day(reservation, return_day)
    InventoryReservation.objects.filter(pk=reservation.pk).update(
        status=ReservationStatus.CONFIRMED,
    )
    assert publish_due_soon_reminders(as_of=today) == 0


@pytest.mark.django_db
def test_publish_due_soon_when_lead_matches(seeded, settings):
    settings.INVENTORY_RETURN_DUE_SOON_DAYS = (1,)
    reservation, owner, _admin = checked_out_reservation(seeded)
    today = timezone.localdate()
    return_day = today + timedelta(days=1)
    _set_return_day(reservation, return_day)
    reservation.refresh_from_db()
    assert days_until_return(reservation, today=today) == 1
    with patch("apps.inventory.notification_schedule.publish_event") as publish:
        assert publish_due_soon_reminders(as_of=today) == 1
        assert publish.call_args.args[0] == "inventory.reservation.return_due_soon"


@pytest.mark.django_db
def test_publish_overdue_agent_when_past_deadline(seeded, settings):
    settings.INVENTORY_RETURN_OVERDUE_AGENT_DAYS = (1,)
    reservation, owner, _admin = checked_out_reservation(seeded)
    today = timezone.localdate()
    return_day = today - timedelta(days=1)
    _set_return_day(reservation, return_day)
    reservation.refresh_from_db()
    assert is_overdue(reservation)
    assert days_overdue(reservation, today=today) == 1
    with patch("apps.inventory.notification_schedule.publish_event") as publish:
        assert publish_overdue_agent_reminders(as_of=today) == 1
        assert publish.call_args.args[0] == "inventory.reservation.return_overdue"


@pytest.mark.django_db
def test_returned_reservation_skips_overdue_publish(seeded, settings):
    settings.INVENTORY_RETURN_OVERDUE_AGENT_DAYS = (1,)
    reservation, owner, admin = checked_out_reservation(seeded)
    today = timezone.localdate()
    return_day = today - timedelta(days=1)
    _set_return_day(reservation, return_day)
    transition(
        actor=actor(admin, ReservationPermission.APPROVE, ReservationPermission.VIEW),
        reservation=reservation,
        action=ReservationAction.ACCEPT_RETURN.value,
        expected_version=reservation_version(reservation),
        expected_status=ReservationStatus.CHECKED_OUT,
    )
    assert publish_overdue_agent_reminders(as_of=today) == 0


@pytest.mark.django_db
def test_suppress_stale_reminders_after_return(
    seeded, django_capture_on_commit_callbacks
):
    reservation, owner, admin = checked_out_reservation(seeded)
    _set_return_day(reservation, timezone.localdate() - timedelta(days=1))
    envelope = _envelope(
        "inventory.reservation.return_overdue",
        {
            "reservation_public_id": str(reservation.public_id),
            "office_id": str(reservation.office_id),
            "owner_id": str(owner.pk),
            "overdue_day": "1",
            "policy_version": "1",
        },
    )
    deliver_many(notifications_for_event(envelope))
    assert Notification.objects.filter(
        recipient=owner, event_key="inventory.reservation.return_overdue"
    ).exists()
    admin_actor = actor(
        admin, ReservationPermission.APPROVE, ReservationPermission.VIEW
    )
    with django_capture_on_commit_callbacks(execute=True):
        transition(
            actor=admin_actor,
            reservation=reservation,
            action=ReservationAction.ACCEPT_RETURN.value,
            expected_version=reservation_version(reservation),
            expected_status=ReservationStatus.CHECKED_OUT,
        )
    notice = Notification.objects.get(
        recipient=owner, event_key="inventory.reservation.return_overdue"
    )
    assert notice.expires_at is not None


@pytest.mark.django_db
def test_duplicate_delivery_is_idempotent(seeded):
    reservation, owner, _admin = checked_out_reservation(seeded)
    _set_return_day(reservation, timezone.localdate() - timedelta(days=1))
    envelope = _envelope(
        "inventory.reservation.return_overdue",
        {
            "reservation_public_id": str(reservation.public_id),
            "office_id": str(reservation.office_id),
            "owner_id": str(owner.pk),
            "overdue_day": "1",
            "policy_version": "1",
        },
    )
    requests = notifications_for_event(envelope)
    assert deliver_many(requests) == 1
    assert deliver_many(requests) == 0
