"""Inventory reservation lifecycle transition tests."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.inventory.models import (
    InventoryItem,
    InventoryReservation,
    ReservationTransitionEvent,
)
from apps.inventory.reservation_common import ActorContext
from apps.inventory.reservation_lifecycle import (
    StaleReservationVersion,
    TransitionRefused,
    reservation_version,
    serialize_timeline,
    sync_overdue_reservations,
    transition,
)
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


def make_item(
    name: str = "Kit", *, requires_approval=False, tracking=TrackingMode.POOLED
):
    kwargs = {
        "owner_office": office(),
        "name": name,
        "category": ItemCategory.OTHER,
        "tracking_mode": tracking,
        "condition": ItemCondition.GOOD,
        "availability_state": ItemAvailabilityState.AVAILABLE,
        "requires_approval": requires_approval,
        "total_quantity": 3 if tracking == TrackingMode.POOLED else 1,
    }
    if tracking == TrackingMode.SERIALIZED:
        kwargs["asset_id"] = f"AST-{name[:8]}"
    return InventoryItem.objects.create(**kwargs)


def future_dates(start_offset: int = 3, length_days: int = 2):
    today = timezone.localdate()
    pickup = today + timedelta(days=start_offset)
    while pickup.weekday() >= 5:
        pickup += timedelta(days=1)
    return_day = pickup + timedelta(days=length_days - 1)
    while return_day.weekday() >= 5:
        return_day += timedelta(days=1)
    return pickup.isoformat(), return_day.isoformat()


def reserve(
    user,
    item,
    *,
    requires_approval=False,
    key: str | None = None,
) -> InventoryReservation:
    if requires_approval:
        item.requires_approval = True
        item.save(update_fields=["requires_approval"])
    pickup, return_day = future_dates()
    reservation, _ = create_reservation(
        actor=actor(user),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=key or str(uuid4()),
    )
    return reservation


def advance(reservation: InventoryReservation, action: str, user, **kwargs):
    return transition(
        actor=actor(user, ReservationPermission.APPROVE, ReservationPermission.VIEW),
        reservation=reservation,
        action=action,
        expected_version=reservation_version(reservation),
        expected_status=reservation.status,
        **kwargs,
    )


@pytest.mark.django_db
def test_full_happy_path(seeded, django_capture_on_commit_callbacks):
    item = make_item()
    owner = agent()
    reservation = reserve(owner, item)
    admin = manager()
    with django_capture_on_commit_callbacks(execute=True):
        reservation = advance(reservation, ReservationAction.MARK_READY.value, admin)
        reservation = advance(reservation, ReservationAction.CHECK_OUT.value, admin)
        reservation = advance(
            reservation, ReservationAction.ACCEPT_RETURN.value, admin, notes="Good"
        )
        reservation = advance(reservation, ReservationAction.COMPLETE.value, admin)
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.COMPLETED
    assert reservation.return_condition_notes == "Good"
    assert (
        ReservationTransitionEvent.objects.filter(reservation=reservation).count() >= 5
    )
    assert AuditEvent.objects.filter(action="inventory.reservation.completed").exists()


@pytest.mark.django_db
def test_approve_requested_reservation(seeded, django_capture_on_commit_callbacks):
    item = make_item(requires_approval=True)
    owner = agent()
    reservation = reserve(owner, item, requires_approval=True)
    assert reservation.status == ReservationStatus.REQUESTED
    admin = manager()
    with django_capture_on_commit_callbacks(execute=True):
        reservation = advance(reservation, ReservationAction.APPROVE.value, admin)
    assert reservation.status == ReservationStatus.CONFIRMED
    assert reservation.approved_by_id == admin.pk


@pytest.mark.django_db
def test_deny_requires_reason(seeded):
    item = make_item(requires_approval=True)
    reservation = reserve(agent(), item, requires_approval=True)
    admin = manager()
    with pytest.raises(ValidationError):
        advance(reservation, ReservationAction.DENY.value, admin)


@pytest.mark.django_db
def test_illegal_transition_refused(seeded):
    item = make_item()
    reservation = reserve(agent(), item)
    admin = manager()
    with pytest.raises(TransitionRefused):
        advance(reservation, ReservationAction.CHECK_OUT.value, admin)


@pytest.mark.django_db
def test_stale_expected_status_rejected(seeded):
    item = make_item()
    reservation = reserve(agent(), item)
    admin = manager()
    reservation = advance(reservation, ReservationAction.MARK_READY.value, admin)
    with pytest.raises(StaleReservationVersion):
        transition(
            actor=actor(admin, ReservationPermission.APPROVE),
            reservation=reservation,
            action=ReservationAction.MARK_READY.value,
            expected_status=ReservationStatus.CONFIRMED,
        )


@pytest.mark.django_db
def test_stale_expected_version_rejected(seeded):
    item = make_item()
    reservation = reserve(agent(), item)
    admin = manager()
    stale = reservation_version(reservation)
    reservation = advance(reservation, ReservationAction.MARK_READY.value, admin)
    with pytest.raises(StaleReservationVersion):
        transition(
            actor=actor(admin, ReservationPermission.APPROVE),
            reservation=reservation,
            action=ReservationAction.CHECK_OUT.value,
            expected_version=stale,
            expected_status=ReservationStatus.READY_FOR_PICKUP,
        )


@pytest.mark.django_db
def test_cancel_releases_capacity(seeded):
    item = make_item(tracking=TrackingMode.SERIALIZED)
    owner = agent()
    other = agent(email="other@example.com")
    reservation = reserve(owner, item)
    from apps.inventory.reservations import cancel_reservation

    cancel_reservation(
        actor=actor(owner),
        reservation=reservation,
        expected_status=reservation.status,
    )
    pickup, return_day = future_dates()
    again, created = create_reservation(
        actor=actor(other),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    assert created


@pytest.mark.django_db
def test_overdue_sync(seeded, django_capture_on_commit_callbacks):
    item = make_item()
    owner = agent()
    reservation = reserve(owner, item)
    admin = manager()
    reservation = advance(reservation, ReservationAction.MARK_READY.value, admin)
    reservation = advance(reservation, ReservationAction.CHECK_OUT.value, admin)
    now = timezone.now()
    reservation.starts_at = now - timedelta(days=2)
    reservation.ends_at = now - timedelta(hours=1)
    reservation.save(update_fields=["starts_at", "ends_at"])
    with django_capture_on_commit_callbacks(execute=True):
        count = sync_overdue_reservations()
    reservation.refresh_from_db()
    assert count == 1
    assert reservation.status == ReservationStatus.OVERDUE


@pytest.mark.django_db
def test_mark_lost_updates_serialized_item(seeded, django_capture_on_commit_callbacks):
    item = make_item(tracking=TrackingMode.SERIALIZED)
    reservation = reserve(agent(), item)
    admin = manager()
    reservation = advance(reservation, ReservationAction.MARK_READY.value, admin)
    reservation = advance(reservation, ReservationAction.CHECK_OUT.value, admin)
    with django_capture_on_commit_callbacks(execute=True):
        reservation = advance(
            reservation,
            ReservationAction.MARK_LOST.value,
            admin,
            reason="Never returned",
        )
    item.refresh_from_db()
    assert reservation.status == ReservationStatus.LOST
    assert item.availability_state == ItemAvailabilityState.LOST


@pytest.mark.django_db
def test_idempotent_transition_no_duplicate_events(seeded):
    item = make_item(requires_approval=True)
    reservation = reserve(agent(), item, requires_approval=True)
    admin = manager()
    reservation = advance(reservation, ReservationAction.APPROVE.value, admin)
    reservation = advance(reservation, ReservationAction.MARK_READY.value, admin)
    events_before = ReservationTransitionEvent.objects.filter(
        reservation=reservation, action=ReservationAction.MARK_READY.value
    ).count()
    advance(reservation, ReservationAction.MARK_READY.value, admin)
    assert (
        ReservationTransitionEvent.objects.filter(
            reservation=reservation, action=ReservationAction.MARK_READY.value
        ).count()
        == events_before
    )


@pytest.mark.django_db
def test_direct_status_save_blocked(seeded):
    reservation = reserve(agent(), make_item())
    reservation.status = ReservationStatus.COMPLETED
    with pytest.raises(ValidationError):
        reservation.save()


@pytest.mark.django_db
def test_timeline_serialization(seeded):
    reservation = reserve(agent(), make_item())
    rows = serialize_timeline(reservation)
    assert rows
    assert rows[0]["action"] == "create"


@pytest.mark.django_db
def test_override_revert_requires_reason(seeded):
    item = make_item()
    reservation = reserve(agent(), item)
    admin = manager()
    override_perm = Permission.objects.get(
        content_type__app_label="inventory", codename="override_reservations"
    )
    admin.user_permissions.add(override_perm)
    reservation = advance(reservation, ReservationAction.MARK_READY.value, admin)
    reservation = advance(reservation, ReservationAction.CHECK_OUT.value, admin)
    reservation = advance(reservation, ReservationAction.ACCEPT_RETURN.value, admin)
    reservation = advance(reservation, ReservationAction.COMPLETE.value, admin)
    with pytest.raises(ValidationError):
        transition(
            actor=actor(
                admin,
                ReservationPermission.OVERRIDE,
                ReservationPermission.APPROVE,
            ),
            reservation=reservation,
            action=ReservationAction.REVERT_RETURN.value,
            expected_version=reservation_version(reservation),
            expected_status=ReservationStatus.COMPLETED,
            override=True,
        )


@pytest.mark.django_db
def test_office_actor_without_permission_denied(seeded):
    reservation = reserve(agent(), make_item(), requires_approval=True)
    reader = agent(email="reader@example.com")
    with pytest.raises(PermissionDenied):
        transition(
            actor=actor(reader),
            reservation=reservation,
            action=ReservationAction.APPROVE.value,
            expected_status=ReservationStatus.REQUESTED,
        )
