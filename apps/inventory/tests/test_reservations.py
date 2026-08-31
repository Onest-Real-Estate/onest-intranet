"""Inventory reservation create/cancel workflow tests."""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.inventory.models import InventoryItem, InventoryReservation
from apps.inventory.reservation_taxonomy import ReservationStatus
from apps.inventory.reservations import ActorContext, create_reservation
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


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def agent(email: str = "agent@example.com", slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def make_item(
    owner_slug: str,
    name: str,
    *,
    tracking=TrackingMode.POOLED,
    quantity=3,
    requires_approval=False,
    **extra,
):
    kwargs = {
        "owner_office": office(owner_slug),
        "name": name,
        "category": ItemCategory.OTHER,
        "tracking_mode": tracking,
        "condition": ItemCondition.GOOD,
        "availability_state": ItemAvailabilityState.AVAILABLE,
        "requires_approval": requires_approval,
        "notes": "Return to front desk",
        "storage_location": "Closet A",
        **extra,
    }
    if tracking == TrackingMode.SERIALIZED:
        kwargs["asset_id"] = extra.pop("asset_id", f"AST-{name[:8]}")
        kwargs["total_quantity"] = 1
    else:
        kwargs["total_quantity"] = quantity
    return InventoryItem.objects.create(**kwargs)


def future_dates(start_offset: int = 3, length_days: int = 2):
    """Return weekday pickup/return ISO dates within policy horizon."""
    today = timezone.localdate()
    pickup = today + timedelta(days=start_offset)
    while pickup.weekday() >= 5:  # Saturday/Sunday
        pickup += timedelta(days=1)
    return_day = pickup + timedelta(days=length_days - 1)
    while return_day.weekday() >= 5:
        return_day += timedelta(days=1)
    return pickup.isoformat(), return_day.isoformat()


def inertia_props(response) -> dict:
    return json.loads(response.content)["props"]


def inertia_component(response) -> str:
    return json.loads(response.content)["component"]


@pytest.mark.django_db
def test_create_auto_confirms_and_snapshots_instructions(
    client, seeded, django_capture_on_commit_callbacks
):
    item = make_item("fairfax-va", "Kit")
    user = agent()
    client.force_login(user)
    pickup, return_day = future_dates()
    key = str(uuid4())

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("inventory_reservation_create"),
            data={
                "item": str(item.public_id),
                "pickup": pickup,
                "return": return_day,
                "quantity": 1,
                "purpose": "Open house",
                "submissionKey": key,
            },
            content_type="application/json",
            HTTP_X_INERTIA="true",
        )
    assert response.status_code == 302
    reservation = InventoryReservation.objects.get(submission_key=key)
    assert reservation.status == ReservationStatus.CONFIRMED
    assert reservation.owner_id == user.pk
    assert reservation.instructions_snapshot == "Return to front desk"
    assert reservation.storage_location_snapshot == "Closet A"
    assert reservation.reference.startswith("INV-R-")
    assert AuditEvent.objects.filter(action="inventory.reservation.created").exists()


@pytest.mark.django_db
def test_requires_approval_starts_requested(seeded):
    item = make_item("fairfax-va", "Approval kit", requires_approval=True)
    user = agent()
    pickup, return_day = future_dates()
    reservation, created = create_reservation(
        actor=ActorContext(user=user, permissions=frozenset()),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    assert created
    assert reservation.status == ReservationStatus.REQUESTED


@pytest.mark.django_db
def test_idempotent_submit_returns_same_row(seeded, django_capture_on_commit_callbacks):
    item = make_item("fairfax-va", "Kit")
    user = agent()
    pickup, return_day = future_dates()
    key = str(uuid4())
    actor = ActorContext(user=user, permissions=frozenset())
    with django_capture_on_commit_callbacks(execute=True):
        first, created1 = create_reservation(
            actor=actor,
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=key,
        )
        second, created2 = create_reservation(
            actor=actor,
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=key,
        )
    assert created1 and not created2
    assert first.pk == second.pk
    assert InventoryReservation.objects.filter(submission_key=key).count() == 1
    assert (
        AuditEvent.objects.filter(action="inventory.reservation.created").count() == 1
    )


@pytest.mark.django_db
def test_capacity_rechecked_at_write(seeded):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    user = agent()
    other = agent(email="other@example.com")
    pickup, return_day = future_dates()
    create_reservation(
        actor=ActorContext(user=user, permissions=frozenset()),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    from apps.inventory.reservations import AvailabilityConflict

    with pytest.raises(AvailabilityConflict):
        create_reservation(
            actor=ActorContext(user=other, permissions=frozenset()),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )


@pytest.mark.django_db
def test_rejects_foreign_office_item(seeded):
    make_item("harrisburg", "Away kit")
    item = InventoryItem.objects.get(name="Away kit")
    user = agent()  # fairfax
    pickup, return_day = future_dates()
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        create_reservation(
            actor=ActorContext(user=user, permissions=frozenset()),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )


@pytest.mark.django_db
def test_rejects_inactive_item(seeded):
    item = make_item("fairfax-va", "Damaged")
    item.availability_state = ItemAvailabilityState.DAMAGED
    item.save(update_fields=["availability_state"])
    user = agent()
    pickup, return_day = future_dates()
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        create_reservation(
            actor=ActorContext(user=user, permissions=frozenset()),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )


@pytest.mark.django_db
def test_cancel_releases_capacity(client, seeded, django_capture_on_commit_callbacks):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    user = agent()
    pickup, return_day = future_dates(start_offset=5)
    with django_capture_on_commit_callbacks(execute=True):
        reservation, _ = create_reservation(
            actor=ActorContext(user=user, permissions=frozenset()),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )
    client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("inventory_reservation_cancel", args=[reservation.public_id]),
            data={"reason": "Plans changed"},
            content_type="application/json",
            HTTP_X_INERTIA="true",
        )
    assert response.status_code == 302
    reservation.refresh_from_db()
    assert reservation.status == ReservationStatus.CANCELLED
    assert AuditEvent.objects.filter(action="inventory.reservation.cancelled").exists()

    # Capacity freed for another agent.
    other = agent(email="other@example.com")
    again, created = create_reservation(
        actor=ActorContext(user=other, permissions=frozenset()),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    assert created
    assert again.status == ReservationStatus.CONFIRMED


@pytest.mark.django_db
def test_cancel_cutoff_blocks_late_cancel(seeded):
    item = make_item("fairfax-va", "Kit")
    user = agent()
    pickup, return_day = future_dates(start_offset=0, length_days=1)
    # Pickup today — cancel cutoff is 24h before start-of-day, already passed.
    reservation, _ = create_reservation(
        actor=ActorContext(user=user, permissions=frozenset()),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    from apps.inventory.reservations import CancelNotAllowed, cancel_reservation

    with pytest.raises(CancelNotAllowed):
        cancel_reservation(
            actor=ActorContext(user=user, permissions=frozenset()),
            reservation=reservation,
        )


@pytest.mark.django_db
def test_detail_is_owner_scoped(client, seeded):
    item = make_item("fairfax-va", "Kit")
    owner = agent()
    other = agent(email="other@example.com")
    pickup, return_day = future_dates()
    reservation, _ = create_reservation(
        actor=ActorContext(user=owner, permissions=frozenset()),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    client.force_login(other)
    response = client.get(
        reverse("inventory_reservation_detail", args=[reservation.public_id]),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_review_summary_page(client, seeded):
    item = make_item("fairfax-va", "Kit")
    user = agent()
    client.force_login(user)
    pickup, return_day = future_dates()
    response = client.get(
        reverse("inventory_reservation_new"),
        {
            "item": str(item.public_id),
            "pickup": pickup,
            "return": return_day,
            "quantity": "1",
            "review": "1",
        },
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 200
    assert inertia_component(response) == "InventoryReservationNew"
    props = inertia_props(response)
    assert props["review"] is True
    assert props["summary"]["isAvailable"] is True
    assert props["summary"]["terms"]["autoConfirm"] is True


@pytest.mark.django_db
def test_browser_availability_sees_committed_reservations(client, seeded):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    user = agent()
    pickup, return_day = future_dates()
    create_reservation(
        actor=ActorContext(user=user, permissions=frozenset()),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    client.force_login(user)
    response = client.get(
        reverse("office_inventory_item", args=[item.public_id]),
        {"pickup": pickup, "return": return_day, "quantity": "1"},
        HTTP_X_INERTIA="true",
    )
    props = inertia_props(response)
    assert props["item"]["availability"]["isAvailable"] is False
    assert "reserved by" not in json.dumps(props).lower()
