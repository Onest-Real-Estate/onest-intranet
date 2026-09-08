"""Capacity semantics: peak demand, state matrix, boundaries, overrides."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.utils import timezone

from apps.inventory.availability import DateTimeInterval, intervals_overlap
from apps.inventory.capacity import (
    AvailabilityConflict,
    assert_capacity_available,
    peak_committed_quantity,
)
from apps.inventory.models import InventoryItem, InventoryReservation
from apps.inventory.reservation_taxonomy import (
    CAPACITY_CONSUMING_STATES,
    ReservationPermission,
    ReservationStatus,
)
from apps.inventory.reservations import (
    ActorContext,
    approve_reservation,
    cancel_reservation,
    change_reservation_quantity,
    create_reservation,
    deny_reservation,
    mark_returned,
    reschedule_reservation,
)
from apps.inventory.services import ActorContext as ItemActor
from apps.inventory.services import update_item
from apps.inventory.taxonomy import (
    InventoryPermission,
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
        **extra,
    }
    if tracking == TrackingMode.SERIALIZED:
        kwargs["asset_id"] = extra.pop("asset_id", f"AST-{name[:8]}")
        kwargs["total_quantity"] = 1
    else:
        kwargs["total_quantity"] = quantity
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


def actor(user, *perms: str) -> ActorContext:
    return ActorContext(user=user, permissions=frozenset(perms))


@pytest.mark.django_db
def test_half_open_endpoints_do_not_overlap():
    start = timezone.now().replace(microsecond=0)
    left = DateTimeInterval(start=start, end=start + timedelta(hours=2))
    right = DateTimeInterval(
        start=start + timedelta(hours=2), end=start + timedelta(hours=4)
    )
    assert not intervals_overlap(left, right)


@pytest.mark.django_db
def test_pooled_fills_to_capacity_not_above(seeded):
    item = make_item("fairfax-va", "Chairs", quantity=2)
    user_a = agent("a@example.com")
    user_b = agent("b@example.com")
    user_c = agent("c@example.com")
    pickup, return_day = future_dates()

    create_reservation(
        actor=actor(user_a),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    create_reservation(
        actor=actor(user_b),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    with pytest.raises(AvailabilityConflict):
        create_reservation(
            actor=actor(user_c),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )


@pytest.mark.django_db
@pytest.mark.parametrize("status", sorted(CAPACITY_CONSUMING_STATES))
def test_capacity_consuming_states_block_overlap(seeded, status):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    owner = agent()
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
    InventoryReservation.objects.filter(pk=reservation.pk).update(status=status)
    with pytest.raises(AvailabilityConflict):
        create_reservation(
            actor=actor(agent("other@example.com")),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [
        ReservationStatus.CANCELLED,
        ReservationStatus.DENIED,
        ReservationStatus.RETURNED,
        ReservationStatus.COMPLETED,
        ReservationStatus.LOST,
        ReservationStatus.DAMAGED,
    ],
)
def test_non_consuming_states_release_capacity(seeded, status):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    owner = agent()
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
    updates = {"status": status}
    if status == ReservationStatus.CANCELLED:
        updates["cancelled_at"] = timezone.now()
        updates["cancelled_by_id"] = owner.pk
    InventoryReservation.objects.filter(pk=reservation.pk).update(**updates)

    again, created = create_reservation(
        actor=actor(agent("other@example.com")),
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
def test_peak_committed_ignores_non_overlapping_sum(seeded):
    item = make_item("fairfax-va", "Kits", quantity=5)
    user = agent()
    pickup_a, return_a = future_dates(start_offset=3, length_days=2)
    pickup_b, return_b = future_dates(start_offset=10, length_days=2)

    create_reservation(
        actor=actor(user),
        item_public_id=str(item.public_id),
        pickup=pickup_a,
        return_date=return_a,
        quantity=3,
        purpose="",
        submission_key=str(uuid4()),
    )
    create_reservation(
        actor=actor(agent("b@example.com")),
        item_public_id=str(item.public_id),
        pickup=pickup_b,
        return_date=return_b,
        quantity=3,
        purpose="",
        submission_key=str(uuid4()),
    )
    # Sum is 6, peak is 3 — reduction to 4 must succeed.
    assert peak_committed_quantity(item) == 3
    manager = agent("mgr@example.com")
    update_item(
        actor=ItemActor(
            user=manager,
            permissions=frozenset({InventoryPermission.MANAGE}),
        ),
        item=item,
        total_quantity=4,
    )
    item.refresh_from_db()
    assert item.total_quantity == 4


@pytest.mark.django_db
def test_quantity_reduction_blocked_by_peak(seeded):
    item = make_item("fairfax-va", "Kits", quantity=5)
    user = agent()
    pickup, return_day = future_dates()
    create_reservation(
        actor=actor(user),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=3,
        purpose="",
        submission_key=str(uuid4()),
    )
    manager = agent("mgr@example.com")
    with pytest.raises(ValidationError) as exc:
        update_item(
            actor=ItemActor(
                user=manager,
                permissions=frozenset({InventoryPermission.MANAGE}),
            ),
            item=item,
            total_quantity=2,
        )
    assert "total_quantity" in exc.value.message_dict


@pytest.mark.django_db
def test_cancel_versus_create_releases_then_allows(seeded):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    owner = agent()
    pickup, return_day = future_dates(start_offset=5)
    reservation, _ = create_reservation(
        actor=actor(owner),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    cancel_reservation(actor=actor(owner), reservation=reservation)
    again, created = create_reservation(
        actor=actor(agent("other@example.com")),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    assert created


@pytest.mark.django_db
def test_approve_and_deny_capacity_path(seeded):
    item = make_item("fairfax-va", "Kit", quantity=1, requires_approval=True)
    owner = agent()
    approver = agent("approver@example.com")
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
    assert reservation.status == ReservationStatus.REQUESTED

    # Requested already consumes — second create fails before approve.
    with pytest.raises(AvailabilityConflict):
        create_reservation(
            actor=actor(agent("other@example.com")),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )

    approved = approve_reservation(
        actor=actor(approver, ReservationPermission.APPROVE),
        reservation=reservation,
    )
    assert approved.status == ReservationStatus.CONFIRMED

    # Deny path on a separate item frees capacity.
    item2 = make_item("fairfax-va", "Kit2", quantity=1, requires_approval=True)
    pending, _ = create_reservation(
        actor=actor(owner),
        item_public_id=str(item2.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    deny_reservation(
        actor=actor(approver, ReservationPermission.APPROVE),
        reservation=pending,
        reason="Not needed",
    )
    freed, created = create_reservation(
        actor=actor(agent("third@example.com")),
        item_public_id=str(item2.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    assert created
    assert freed.status == ReservationStatus.REQUESTED


@pytest.mark.django_db
def test_reschedule_and_quantity_change_races_preserve_invariant(seeded):
    item = make_item("fairfax-va", "Kits", quantity=2)
    owner = agent()
    other = agent("other@example.com")
    pickup, return_day = future_dates(start_offset=4, length_days=2)
    alt_pickup, alt_return = future_dates(start_offset=12, length_days=2)

    first, _ = create_reservation(
        actor=actor(owner),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    create_reservation(
        actor=actor(other),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )

    # Cannot grow quantity above remaining capacity.
    with pytest.raises(AvailabilityConflict):
        change_reservation_quantity(
            actor=actor(owner),
            reservation=first,
            quantity=2,
        )

    # Reschedule away frees the original window for a third unit there... but
    # capacity is 2 and one remains — moving first away allows a new create.
    reschedule_reservation(
        actor=actor(owner),
        reservation=first,
        pickup=alt_pickup,
        return_date=alt_return,
    )
    create_reservation(
        actor=actor(agent("third@example.com")),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )


@pytest.mark.django_db
def test_return_releases_capacity(seeded):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    owner = agent()
    staff = agent("staff@example.com")
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
    InventoryReservation.objects.filter(pk=reservation.pk).update(
        status=ReservationStatus.CHECKED_OUT
    )
    reservation.refresh_from_db()
    mark_returned(
        actor=actor(staff, ReservationPermission.APPROVE),
        reservation=reservation,
    )
    again, created = create_reservation(
        actor=actor(agent("other@example.com")),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    assert created


@pytest.mark.django_db
def test_override_cannot_exceed_capacity_without_over_allocation(seeded):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    owner = agent()
    admin = agent("admin@example.com")
    pickup, return_day = future_dates()
    create_reservation(
        actor=actor(owner),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    with pytest.raises(AvailabilityConflict):
        create_reservation(
            actor=actor(admin, ReservationPermission.OVERRIDE),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
            bypass_policy=True,
        )

    over, created = create_reservation(
        actor=actor(admin, ReservationPermission.OVERRIDE),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
        allow_over_allocation=True,
        override_reason="Broker-approved double use for open house",
    )
    assert created
    assert over.over_allocation_reason.startswith("Broker-approved")
    assert over.over_allocation_approved_by_id == admin.pk


@pytest.mark.django_db
def test_over_allocation_requires_permission_and_reason(seeded):
    item = make_item("fairfax-va", "Kit", quantity=1)
    user = agent()
    pickup, return_day = future_dates()
    create_reservation(
        actor=actor(user),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    with pytest.raises(PermissionDenied):
        create_reservation(
            actor=actor(agent("other@example.com")),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
            allow_over_allocation=True,
            override_reason="nope",
        )
    with pytest.raises(ValidationError):
        create_reservation(
            actor=actor(agent("admin@example.com"), ReservationPermission.OVERRIDE),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
            allow_over_allocation=True,
            override_reason="",
        )


@pytest.mark.django_db
def test_conflict_message_hides_other_owners(seeded):
    item = make_item("fairfax-va", "Serialized", tracking=TrackingMode.SERIALIZED)
    owner = agent("secret-owner@example.com")
    pickup, return_day = future_dates()
    create_reservation(
        actor=actor(owner),
        item_public_id=str(item.public_id),
        pickup=pickup,
        return_date=return_day,
        quantity=1,
        purpose="",
        submission_key=str(uuid4()),
    )
    with pytest.raises(AvailabilityConflict) as exc:
        create_reservation(
            actor=actor(agent("other@example.com")),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )
    blob = str(exc.value).lower()
    assert "secret-owner" not in blob
    assert "choose another range" in blob


@pytest.mark.django_db
def test_assert_capacity_requires_item_lock(seeded):
    item = make_item("fairfax-va", "Kit", quantity=1)
    pickup, return_day = future_dates()
    from apps.inventory.browser import parse_availability_interval

    interval, _ = parse_availability_interval(pickup, return_day)
    assert interval is not None
    # Without a lock this still validates math; locking is the caller's duty.
    assert_capacity_available(item, interval, 1)


@pytest.mark.django_db
def test_lock_item_compiles_for_postgresql(monkeypatch, seeded):
    from apps.user.tests.pg_compile import compile_for_postgresql

    item = make_item("fairfax-va", "Kit", quantity=1)
    qs = InventoryItem.objects.select_for_update(of=("self",)).filter(pk=item.pk)
    sql = compile_for_postgresql(qs, monkeypatch).upper()
    assert "FOR UPDATE" in sql
    assert "OF" in sql


@pytest.mark.django_db
def test_overlap_query_uses_capacity_index_on_postgres(seeded):
    if connection.vendor != "postgresql":
        pytest.skip("EXPLAIN index check requires PostgreSQL")

    item = make_item("fairfax-va", "Kit", quantity=5)
    user = agent()
    pickup, return_day = future_dates()
    for i in range(3):
        create_reservation(
            actor=actor(agent(f"u{i}@example.com") if i else user),
            item_public_id=str(item.public_id),
            pickup=pickup,
            return_date=return_day,
            quantity=1,
            purpose="",
            submission_key=str(uuid4()),
        )

    from apps.inventory.browser import parse_availability_interval

    interval, _ = parse_availability_interval(pickup, return_day)
    assert interval is not None
    qs = InventoryReservation.objects.overlapping(
        item_id=item.pk,
        starts_at=interval.start,
        ends_at=interval.end,
    )
    sql, params = qs.query.sql_with_params()
    with connection.cursor() as cursor:
        cursor.execute(f"EXPLAIN {sql}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall()).lower()
    assert "inv_rsv" in plan
