"""True transactional concurrency tests against PostgreSQL.

SQLite serializes writers and hides ``FOR UPDATE`` races, so these tests skip
unless the active connection vendor is PostgreSQL. Run via the docker compose
dev stack (``make test`` / ``docker compose … exec web uv run pytest``).
"""

from __future__ import annotations

import threading
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection, connections
from django.utils import timezone

from apps.inventory.capacity import AvailabilityConflict
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

pytestmark = [
    pytest.mark.django_db(transaction=True),
]


def _require_postgres() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Concurrency races require PostgreSQL row locks")


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def agent(email: str, slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def make_serialized(name: str = "Camera") -> InventoryItem:
    return InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name=name,
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        asset_id=f"AST-{uuid4().hex[:8]}",
        total_quantity=1,
        condition=ItemCondition.GOOD,
        availability_state=ItemAvailabilityState.AVAILABLE,
    )


def make_pooled(quantity: int = 2, name: str = "Chairs") -> InventoryItem:
    return InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name=name,
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=quantity,
        condition=ItemCondition.GOOD,
        availability_state=ItemAvailabilityState.AVAILABLE,
    )


def future_dates(start_offset: int = 5, length_days: int = 2):
    today = timezone.localdate()
    pickup = today + timedelta(days=start_offset)
    while pickup.weekday() >= 5:
        pickup += timedelta(days=1)
    return_day = pickup + timedelta(days=length_days - 1)
    while return_day.weekday() >= 5:
        return_day += timedelta(days=1)
    return pickup.isoformat(), return_day.isoformat()


def _close_thread_connection() -> None:
    connections.close_all()


def test_final_unit_has_exactly_one_winner(seeded):
    _require_postgres()
    item = make_serialized()
    user_a = agent("race-a@example.com")
    user_b = agent("race-b@example.com")
    pickup, return_day = future_dates()
    barrier = threading.Barrier(2, timeout=10)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(user) -> None:
        try:
            barrier.wait()
            create_reservation(
                actor=ActorContext(user=user, permissions=frozenset()),
                item_public_id=str(item.public_id),
                pickup=pickup,
                return_date=return_day,
                quantity=1,
                purpose="",
                submission_key=str(uuid4()),
            )
            with lock:
                outcomes.append("ok")
        except AvailabilityConflict:
            with lock:
                outcomes.append("conflict")
        finally:
            _close_thread_connection()

    threads = [
        threading.Thread(target=attempt, args=(user_a,)),
        threading.Thread(target=attempt, args=(user_b,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == 1
    assert (
        InventoryReservation.objects.filter(
            item=item, status__in=[ReservationStatus.CONFIRMED]
        ).count()
        == 1
    )


def test_pooled_concurrent_fill_never_exceeds_quantity(seeded):
    _require_postgres()
    item = make_pooled(quantity=2)
    users = [agent(f"pool-{i}@example.com") for i in range(4)]
    pickup, return_day = future_dates()
    barrier = threading.Barrier(4, timeout=10)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(user) -> None:
        try:
            barrier.wait()
            create_reservation(
                actor=ActorContext(user=user, permissions=frozenset()),
                item_public_id=str(item.public_id),
                pickup=pickup,
                return_date=return_day,
                quantity=1,
                purpose="",
                submission_key=str(uuid4()),
            )
            with lock:
                outcomes.append("ok")
        except AvailabilityConflict:
            with lock:
                outcomes.append("conflict")
        finally:
            _close_thread_connection()

    threads = [threading.Thread(target=attempt, args=(user,)) for user in users]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert outcomes.count("ok") == 2
    assert outcomes.count("conflict") == 2
    total = InventoryReservation.objects.filter(
        item=item, status=ReservationStatus.CONFIRMED
    ).count()
    assert total == 2


def test_idempotent_retry_under_concurrency(seeded):
    _require_postgres()
    item = make_serialized("Lens")
    user = agent("idem@example.com")
    pickup, return_day = future_dates()
    key = str(uuid4())
    barrier = threading.Barrier(2, timeout=10)
    results: list[tuple[int, bool]] = []
    lock = threading.Lock()

    def attempt() -> None:
        try:
            barrier.wait()
            reservation, created = create_reservation(
                actor=ActorContext(user=user, permissions=frozenset()),
                item_public_id=str(item.public_id),
                pickup=pickup,
                return_date=return_day,
                quantity=1,
                purpose="",
                submission_key=key,
            )
            with lock:
                results.append((reservation.pk, created))
        finally:
            _close_thread_connection()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert len(results) == 2
    assert results[0][0] == results[1][0]
    assert sorted(created for _, created in results) == [False, True]
    assert InventoryReservation.objects.filter(submission_key=key).count() == 1


def test_deadlock_order_two_items_stable(seeded):
    """Two workers each touching two items lock in ascending pk order."""
    _require_postgres()
    from apps.inventory.capacity import lock_items

    first = make_serialized("A")
    second = make_serialized("B")
    # Ensure deterministic pk order.
    low, high = sorted([first, second], key=lambda row: row.pk)
    barrier = threading.Barrier(2, timeout=10)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(order: list[int]) -> None:
        from django.db import transaction

        try:
            barrier.wait()
            with transaction.atomic():
                lock_items(*order)
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            with lock:
                errors.append(exc)
        finally:
            _close_thread_connection()

    # Opposite acquisition orders — helpers sort, so neither deadlocks.
    threads = [
        threading.Thread(target=worker, args=([high.pk, low.pk],)),
        threading.Thread(target=worker, args=([low.pk, high.pk],)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()
    assert errors == []
