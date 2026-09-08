"""The unified capacity ledger and the reservation record that rides on it."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.db import (
    IntegrityError,
    OperationalError,
    connection,
    connections,
    transaction,
)

from apps.reservations.booking import (
    ReservationConflict,
    _is_deadlock,
    _save_occupancy,
    create_reservation,
    reschedule_reservation,
)
from apps.reservations.models import Occupancy, Reservation, SpaceAvailabilityException
from apps.reservations.operations import OCCUPANCY_NO_OVERLAP
from apps.reservations.taxonomy import (
    ExceptionKind,
    OccupancySource,
    ReservationPermission,
    ReservationStatus,
)
from apps.reservations.tests.factories import (
    assign_role,
    make_occupancy,
    make_reservation,
    make_space,
    make_weekly_hours,
    office,
    person,
)
from apps.user.roles import ScopeType

NINE = datetime(2026, 3, 2, 14, tzinfo=UTC)
TEN = NINE + timedelta(hours=1)
ELEVEN = NINE + timedelta(hours=2)
TWELVE = NINE + timedelta(hours=3)


def test_occupancy_requires_an_aware_forward_interval(seeded):
    space = make_space()

    naive = Occupancy(
        space=space,
        starts_at=NINE.replace(tzinfo=None),
        ends_at=TEN,
        source=OccupancySource.RESERVATION,
    )
    with pytest.raises(ValidationError) as naive_error:
        naive.full_clean()
    assert "starts_at" in naive_error.value.message_dict

    backwards = Occupancy(
        space=space,
        starts_at=TEN,
        ends_at=NINE,
        source=OccupancySource.RESERVATION,
    )
    with pytest.raises(ValidationError) as order_error:
        backwards.full_clean()
    assert "ends_at" in order_error.value.message_dict


def test_overlap_lookup_is_half_open(seeded):
    space = make_space()
    make_occupancy(space, starts_at=NINE, ends_at=TEN)

    assert not Occupancy.objects.overlapping(
        space_id=space.pk, starts_at=TEN, ends_at=ELEVEN
    ).exists()
    assert Occupancy.objects.overlapping(
        space_id=space.pk,
        starts_at=TEN - timedelta(minutes=1),
        ends_at=ELEVEN,
    ).exists()


def test_released_occupancy_stops_consuming_capacity(seeded):
    space = make_space()
    make_occupancy(space, starts_at=NINE, ends_at=TEN, consumes_capacity=False)

    assert not Occupancy.objects.overlapping(
        space_id=space.pk, starts_at=NINE, ends_at=TEN
    ).exists()


def test_an_availability_exception_joins_the_ledger(seeded):
    space = make_space()

    block = SpaceAvailabilityException.objects.create(
        space=space,
        kind=ExceptionKind.MAINTENANCE,
        starts_at=NINE,
        ends_at=TEN,
        reason="HVAC service",
    )

    assert block.occupancy.source == OccupancySource.EXCEPTION
    assert block.occupancy.consumes_capacity is True
    assert (block.occupancy.starts_at, block.occupancy.ends_at) == (NINE, TEN)
    assert (
        Occupancy.objects.overlapping(
            space_id=space.pk, starts_at=NINE, ends_at=ELEVEN
        ).count()
        == 1
    )


def test_moving_an_exception_moves_its_ledger_row(seeded):
    space = make_space()
    block = SpaceAvailabilityException.objects.create(
        space=space,
        kind=ExceptionKind.MAINTENANCE,
        starts_at=NINE,
        ends_at=TEN,
        reason="HVAC service",
    )
    ledger_id = block.occupancy_id

    block.starts_at = TEN
    block.ends_at = ELEVEN
    block.save()
    block.occupancy.refresh_from_db()

    assert block.occupancy_id == ledger_id
    assert (block.occupancy.starts_at, block.occupancy.ends_at) == (TEN, ELEVEN)


def test_reservation_office_must_match_the_space_office(seeded):
    space = make_space()
    owner = person("agent@example.com", "fairfax-va")

    with pytest.raises(ValidationError) as error:
        make_reservation(
            space=space,
            owner=owner,
            starts_at=NINE,
            ends_at=TEN,
            office=space.owner_office.parent or space.owner_office,
            office_name="Wrong office",
        )
    assert "office" in error.value.message_dict


def test_cancellation_timestamp_tracks_the_cancelled_status(seeded):
    space = make_space()
    owner = person("agent@example.com", "fairfax-va")
    reservation = make_reservation(
        space=space, owner=owner, starts_at=NINE, ends_at=TEN
    )

    reservation.status = ReservationStatus.CANCELLED
    with pytest.raises(ValidationError) as missing:
        reservation.full_clean()
    assert "cancelled_at" in missing.value.message_dict

    reservation.cancelled_at = TEN
    reservation.full_clean()

    reservation.status = ReservationStatus.CONFIRMED
    with pytest.raises(ValidationError) as stale:
        reservation.full_clean()
    assert "cancelled_at" in stale.value.message_dict


def test_stable_reservation_identity_cannot_be_rewritten(seeded):
    space = make_space()
    owner = person("agent@example.com", "fairfax-va")
    other = person("colleague@example.com", "fairfax-va")
    reservation = make_reservation(
        space=space, owner=owner, starts_at=NINE, ends_at=TEN
    )

    reservation.reference = "REWRITTEN"
    reservation.owner = other
    with pytest.raises(ValidationError) as error:
        reservation.full_clean()

    assert set(error.value.message_dict) == {"reference", "owner"}


def test_reservations_are_retained_for_audit_history(seeded):
    space = make_space()
    owner = person("agent@example.com", "fairfax-va")
    reservation = make_reservation(
        space=space, owner=owner, starts_at=NINE, ends_at=TEN
    )

    with pytest.raises(ValidationError, match="audit"):
        reservation.delete()

    assert Reservation.objects.filter(pk=reservation.pk).exists()


def test_owner_scope_query_excludes_other_agents(seeded):
    space = make_space()
    owner = person("agent@example.com", "fairfax-va")
    other = person("colleague@example.com", "fairfax-va")
    mine = make_reservation(space=space, owner=owner, starts_at=NINE, ends_at=TEN)
    make_reservation(space=space, owner=other, starts_at=TEN, ends_at=ELEVEN)

    assert list(Reservation.objects.for_owner(owner)) == [mine]


def test_the_overlap_constraint_compiles_to_valid_postgresql():
    """SQLite cannot enforce it, so verify the DDL PostgreSQL will run."""
    from apps.reservations.operations import occupancy_no_overlap_constraint
    from apps.user.tests.pg_compile import compile_constraint_for_postgresql

    sql = compile_constraint_for_postgresql(
        occupancy_no_overlap_constraint(), Occupancy
    )

    assert "EXCLUDE USING GIST" in sql
    assert '"space_id" WITH =' in sql
    # ``'[)'`` is the half-open interval the whole domain is built on: a block
    # ending at 10:00 and one starting at 10:00 do not collide.
    assert '(TSTZRANGE("starts_at", "ends_at", \'[)\')) WITH &&' in sql
    assert 'WHERE ("consumes_capacity")' in sql


def test_the_overlap_constraint_is_a_no_op_away_from_postgres(seeded):
    """It must not fail on SQLite, and must not enter migration state."""
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader

    from apps.reservations.operations import AddConstraintIfPostgres

    loader = MigrationLoader(connection)
    migration = loader.disk_migrations[
        ("reservations", "0003_reservation_occupancy_ledger")
    ]
    constraint_ops = [
        operation
        for operation in migration.operations
        if isinstance(operation, AddConstraintIfPostgres)
    ]

    assert constraint_ops
    state = {}
    for operation in constraint_ops:
        operation.state_forwards("reservations", state)
    assert state == {}
    assert not any(
        constraint.name == "rsv_occupancy_no_overlap"
        for constraint in Occupancy._meta.constraints
    )


@pytest.mark.parametrize(
    ("permission", "expected_roles"),
    [
        (
            ReservationPermission.MANAGE,
            {
                "system_admin",
                "principal_broker",
                "broker_admin",
                "regional_manager",
                "regional_admin",
                "branch_manager",
                "branch_admin",
            },
        ),
        (
            ReservationPermission.OVERRIDE,
            {
                "system_admin",
                "principal_broker",
                "broker_admin",
                "regional_manager",
                "branch_manager",
            },
        ),
    ],
)
def test_booking_permissions_reach_the_same_roles_from_both_sources(
    permission, expected_roles
):
    """The role bundles and the reviewed catalog must not drift apart."""
    from apps.user.roles import ROLE_DEFINITIONS
    from apps.web.permission_catalog import permissions_for_role

    from_bundles = {
        definition.code
        for definition in ROLE_DEFINITIONS
        if permission.value in definition.default_permissions
    }
    from_catalog = {
        definition.code
        for definition in ROLE_DEFINITIONS
        if permission.value in permissions_for_role(definition.code)
    }

    assert from_bundles == from_catalog == expected_roles


def test_every_role_may_book_but_not_every_role_may_override():
    from apps.user.roles import ROLE_DEFINITIONS
    from apps.web.permission_catalog import permissions_for_role

    for definition in ROLE_DEFINITIONS:
        granted = permissions_for_role(definition.code)
        assert ReservationPermission.BOOK.value in granted, definition.code
        assert ReservationPermission.BOOK.value in definition.default_permissions

    realtor = permissions_for_role("realtor")
    assert ReservationPermission.MANAGE.value not in realtor
    assert ReservationPermission.OVERRIDE.value not in realtor


postgres_only = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="The overlap invariant is a PostgreSQL exclusion constraint.",
)


@postgres_only
def test_postgres_refuses_a_second_overlapping_occupancy(seeded):
    space = make_space()
    make_occupancy(space, starts_at=NINE, ends_at=ELEVEN)

    with pytest.raises(IntegrityError), transaction.atomic():
        Occupancy.objects.create(
            space=space,
            starts_at=TEN,
            ends_at=ELEVEN,
            source=OccupancySource.EXCEPTION,
        )


@postgres_only
def test_postgres_allows_back_to_back_and_released_intervals(seeded):
    space = make_space()
    make_occupancy(space, starts_at=NINE, ends_at=TEN)

    # Half-open: the 10:00 boundary is shared, not overlapping.
    make_occupancy(space, starts_at=TEN, ends_at=ELEVEN)
    # A released row no longer holds the slot it used to.
    make_occupancy(space, starts_at=NINE, ends_at=TEN, consumes_capacity=False)

    assert Occupancy.objects.filter(space=space).count() == 3


@postgres_only
def test_postgres_scopes_the_invariant_to_one_space(seeded):
    first = make_space()
    second = make_space(name="Green meeting room")
    make_occupancy(first, starts_at=NINE, ends_at=ELEVEN)

    make_occupancy(second, starts_at=NINE, ends_at=ELEVEN)

    assert Occupancy.objects.count() == 2


@postgres_only
def test_postgres_frees_the_slot_when_a_reservation_is_released(seeded):
    space = make_space()
    owner = person("agent@example.com", "fairfax-va")
    reservation = make_reservation(
        space=space, owner=owner, starts_at=NINE, ends_at=ELEVEN
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        make_occupancy(space, starts_at=TEN, ends_at=ELEVEN)

    reservation.occupancy.consumes_capacity = False
    reservation.occupancy.save(update_fields=["consumes_capacity"])

    make_occupancy(space, starts_at=TEN, ends_at=ELEVEN)
    assert (
        Occupancy.objects.overlapping(
            space_id=space.pk, starts_at=NINE, ends_at=ELEVEN
        ).count()
        == 1
    )


# --- Concurrency: the invariant under two genuinely simultaneous writers -----


def _seed_reference_data() -> None:
    """Seed inside a transactional test, where the ``seeded`` fixture cannot run."""
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def _booker(email: str) -> object:
    user = person(email, "fairfax-va")
    assign_role(user, "realtor", ScopeType.OFFICE, office("fairfax-va"))
    return user


def _bookable_room(**fields):
    room = make_space(minimum_notice_minutes=0, **fields)
    make_weekly_hours(room, weekday=0, starts_at=time(9), ends_at=time(17))
    return room


def _run_concurrently(work, arguments: list[tuple]) -> list[str]:
    """Run ``work`` on separate connections, released together by a barrier.

    Each thread owns its connection, so both transactions are really in flight
    and the loser is decided by PostgreSQL rather than by Python ordering.
    """
    barrier = threading.Barrier(len(arguments), timeout=15)
    outcomes: list[str] = []
    guard = threading.Lock()

    def attempt(args: tuple) -> None:
        try:
            with transaction.atomic():
                barrier.wait()
                work(*args)
            result = "committed"
        except (ReservationConflict, IntegrityError):
            result = "conflict"
        except OperationalError as exc:
            # A writer that skipped the space lock can lose to a deadlock
            # instead; the service layer maps this to a conflict.
            result = "deadlock" if _is_deadlock(exc) else "error"
        finally:
            connections.close_all()
        with guard:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt, args=(args,)) for args in arguments]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads), "a worker deadlocked"
    return sorted(outcomes)


@postgres_only
@pytest.mark.django_db(transaction=True)
def test_concurrent_bookings_of_one_slot_commit_exactly_once():
    _seed_reference_data()
    room = _bookable_room()
    first = _booker("first@example.com")
    second = _booker("second@example.com")

    def book(actor, key):
        create_reservation(
            actor=actor,
            space=room,
            starts_at=NINE,
            ends_at=TEN,
            purpose="Buyer consultation",
            submission_key=key,
            now=NINE - timedelta(hours=1),
        )

    outcomes = _run_concurrently(book, [(first, "race-a"), (second, "race-b")])

    assert outcomes == ["committed", "conflict"]
    assert Reservation.objects.filter(space=room).count() == 1
    assert Occupancy.objects.consuming().filter(space=room).count() == 1


@postgres_only
@pytest.mark.django_db(transaction=True)
def test_concurrent_back_to_back_bookings_both_commit():
    _seed_reference_data()
    room = _bookable_room()
    first = _booker("first@example.com")
    second = _booker("second@example.com")

    def book(actor, starts_at, ends_at, key):
        create_reservation(
            actor=actor,
            space=room,
            starts_at=starts_at,
            ends_at=ends_at,
            purpose="Buyer consultation",
            submission_key=key,
            now=NINE - timedelta(hours=1),
        )

    # Half-open [start, end): the shared 10:00 boundary is not an overlap.
    outcomes = _run_concurrently(
        book,
        [(first, NINE, TEN, "btb-a"), (second, TEN, ELEVEN, "btb-b")],
    )

    assert outcomes == ["committed", "committed"]
    assert Occupancy.objects.consuming().filter(space=room).count() == 2


@postgres_only
@pytest.mark.django_db(transaction=True)
def test_a_buffered_booking_blocks_a_neighbour_that_looks_adjacent():
    _seed_reference_data()
    room = _bookable_room(buffer_after_minutes=15)
    first = _booker("first@example.com")
    second = _booker("second@example.com")

    def book(actor, starts_at, ends_at, key):
        create_reservation(
            actor=actor,
            space=room,
            starts_at=starts_at,
            ends_at=ends_at,
            purpose="Buyer consultation",
            submission_key=key,
            now=NINE - timedelta(hours=1),
        )

    # 09:00-10:00 protects through 10:15, so a 10:00 start is not free.
    outcomes = _run_concurrently(
        book,
        [(first, NINE, TEN, "buf-a"), (second, TEN, ELEVEN, "buf-b")],
    )

    assert outcomes == ["committed", "conflict"]
    assert Occupancy.objects.consuming().filter(space=room).count() == 1


@postgres_only
@pytest.mark.django_db(transaction=True)
def test_the_constraint_still_decides_a_race_that_skips_the_space_lock():
    """The database is the authority even when a writer takes no space lock.

    Both service write paths lock the space row first, so they serialize. This
    inserts straight into the ledger to prove the exclusion constraint — not the
    lock discipline — is what makes the invariant race-proof.
    """
    _seed_reference_data()
    room = make_space()

    def insert(starts_at, ends_at, source):
        Occupancy.objects.create(
            space=room, starts_at=starts_at, ends_at=ends_at, source=source
        )

    outcomes = _run_concurrently(
        insert,
        [
            (NINE, ELEVEN, OccupancySource.RESERVATION),
            (TEN, ELEVEN, OccupancySource.EXCEPTION),
        ],
    )

    # One writer commits; the other loses to the constraint or to the deadlock
    # PostgreSQL raises when both are mid-check. Never two rows.
    assert outcomes.count("committed") <= 1
    assert "error" not in outcomes
    assert Occupancy.objects.consuming().filter(space=room).count() <= 1


@postgres_only
@pytest.mark.django_db(transaction=True)
def test_concurrent_reschedules_onto_one_slot_commit_exactly_once():
    """Reschedules lock their own rows, so this is the path that can deadlock."""
    _seed_reference_data()
    room = _bookable_room()
    first_owner = _booker("first@example.com")
    second_owner = _booker("second@example.com")
    first = make_reservation(
        space=room, owner=first_owner, starts_at=NINE, ends_at=TEN, reference="RSV-A"
    )
    second = make_reservation(
        space=room,
        owner=second_owner,
        starts_at=ELEVEN,
        ends_at=ELEVEN + timedelta(hours=1),
        reference="RSV-B",
    )
    target_start = TEN
    target_end = ELEVEN

    def move(actor, reservation):
        reschedule_reservation(
            actor=actor,
            reservation=reservation,
            starts_at=target_start,
            ends_at=target_end,
            now=NINE - timedelta(hours=1),
        )

    outcomes = _run_concurrently(move, [(first_owner, first), (second_owner, second)])

    assert outcomes == ["committed", "conflict"]
    assert (
        Occupancy.objects.overlapping(
            space_id=room.pk, starts_at=target_start, ends_at=target_end
        ).count()
        == 1
    )


def test_a_deadlock_maps_to_the_same_conflict_as_an_exclusion_violation(
    seeded, monkeypatch
):
    """Both database refusals must reach the caller as one domain conflict."""

    class Deadlock(Exception):
        sqlstate = "40P01"

    def explode(*args, **kwargs):
        raise OperationalError("deadlock detected") from Deadlock()

    monkeypatch.setattr(Occupancy, "save", explode)
    occupancy = Occupancy(
        space=make_space(),
        starts_at=NINE,
        ends_at=TEN,
        source=OccupancySource.RESERVATION,
    )

    with pytest.raises(ReservationConflict) as caught:
        _save_occupancy(occupancy)

    assert "no longer available" in str(caught.value) or "just taken" in str(
        caught.value
    )


def test_an_unrelated_database_error_is_not_disguised_as_a_conflict(
    seeded, monkeypatch
):
    class Timeout(Exception):
        sqlstate = "57014"

    def explode(*args, **kwargs):
        raise OperationalError("statement timeout") from Timeout()

    monkeypatch.setattr(Occupancy, "save", explode)
    occupancy = Occupancy(
        space=make_space(),
        starts_at=NINE,
        ends_at=TEN,
        source=OccupancySource.RESERVATION,
    )

    with pytest.raises(OperationalError):
        _save_occupancy(occupancy)


# --- Overlap shapes, DST, room identity, and the supporting indexes ---------


@postgres_only
def test_postgres_refuses_a_contained_and_a_containing_interval(seeded):
    space = make_space()
    make_occupancy(space, starts_at=NINE, ends_at=TWELVE)

    # Fully inside the committed interval.
    with pytest.raises(IntegrityError), transaction.atomic():
        make_occupancy(space, starts_at=TEN, ends_at=ELEVEN)

    assert Occupancy.objects.consuming().filter(space=space).count() == 1


@postgres_only
def test_postgres_refuses_an_interval_that_swallows_a_committed_one(seeded):
    space = make_space()
    make_occupancy(space, starts_at=TEN, ends_at=ELEVEN)

    # Strictly contains the committed interval on both sides.
    with pytest.raises(IntegrityError), transaction.atomic():
        make_occupancy(space, starts_at=NINE, ends_at=TWELVE)

    assert Occupancy.objects.consuming().filter(space=space).count() == 1


@postgres_only
def test_postgres_separates_repeated_wall_times_across_a_fall_back_fold(seeded):
    """01:00 happens twice on 2026-11-01 in New York; they are distinct instants."""
    space = make_space()
    zone = ZoneInfo("America/New_York")
    # Resolve to instants before doing any arithmetic: adding a timedelta to an
    # aware local datetime is wall-clock arithmetic and silently drops ``fold``.
    first_one = datetime(2026, 11, 1, 1, fold=0, tzinfo=zone).astimezone(UTC)
    second_one = datetime(2026, 11, 1, 1, fold=1, tzinfo=zone).astimezone(UTC)
    assert second_one - first_one == timedelta(hours=1)

    make_occupancy(
        space, starts_at=first_one, ends_at=first_one + timedelta(minutes=30)
    )
    # Same wall clock, one hour later in real time: not an overlap.
    make_occupancy(
        space, starts_at=second_one, ends_at=second_one + timedelta(minutes=30)
    )

    assert Occupancy.objects.consuming().filter(space=space).count() == 2

    # The hour between them is still protected against a genuine overlap.
    with pytest.raises(IntegrityError), transaction.atomic():
        make_occupancy(
            space,
            starts_at=first_one + timedelta(minutes=15),
            ends_at=second_one + timedelta(minutes=15),
        )


@postgres_only
def test_postgres_scopes_a_room_move_to_the_destination_room(seeded):
    """Moving a ledger row between rooms is judged against the destination.

    No service moves a booking between rooms today; the invariant is enforced at
    the ledger, so it governs such a move whenever one is added.
    """
    origin = make_space()
    destination = make_space(name="Green meeting room")
    moving = make_occupancy(origin, starts_at=NINE, ends_at=ELEVEN)
    make_occupancy(destination, starts_at=NINE, ends_at=ELEVEN)

    moving.space = destination
    with pytest.raises(IntegrityError), transaction.atomic():
        moving.save(update_fields=["space"])

    assert Occupancy.objects.consuming().filter(space=destination).count() == 1


def test_widening_a_buffer_policy_does_not_rewrite_committed_intervals(seeded):
    """Buffer edits apply to new writes; committed rows keep their own interval.

    Stated as a test because the alternative — retroactively widening live
    occupancies — could put the table into a state the constraint rejects.
    """
    space = make_space(buffer_after_minutes=0)
    owner = person("agent@example.com", "fairfax-va")
    reservation = make_reservation(
        space=space, owner=owner, starts_at=NINE, ends_at=TEN
    )

    space.buffer_after_minutes = 30
    space.save(update_fields=["buffer_after_minutes"])

    reservation.refresh_from_db()
    assert reservation.occupancy.ends_at == TEN
    assert reservation.buffer_after_minutes == 0


@postgres_only
def test_the_ledger_carries_the_indexes_the_overlap_checks_rely_on(seeded):
    """Both the calendar lookup index and the constraint's GiST index exist."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = %s
            """,
            [Occupancy._meta.db_table],
        )
        indexes = dict(cursor.fetchall())

    assert "rsv_occupancy_calendar_idx" in indexes
    constraint_index = indexes.get(OCCUPANCY_NO_OVERLAP)
    assert constraint_index is not None, "the exclusion constraint has no index"
    assert "gist" in constraint_index.lower()
    assert "tstzrange" in constraint_index.lower()
    assert "consumes_capacity" in constraint_index.lower()


@postgres_only
def test_the_overlap_lookup_can_be_served_by_the_calendar_index(seeded):
    """The planner can use the index for the overlap shape the service runs.

    Test tables are small enough that a sequential scan is genuinely cheaper, so
    ``enable_seqscan`` is disabled to ask the narrower question: is the index
    usable for this predicate at all, or is its column order wrong?
    """
    space = make_space()
    make_occupancy(space, starts_at=NINE, ends_at=TEN)
    query, params = Occupancy.objects.overlapping(
        space_id=space.pk, starts_at=NINE, ends_at=ELEVEN
    ).query.sql_with_params()

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(f"EXPLAIN {query}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert "rsv_occupancy_calendar_idx" in plan, plan
