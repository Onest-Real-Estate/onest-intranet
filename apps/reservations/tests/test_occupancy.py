"""The unified capacity ledger and the reservation record that rides on it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from apps.reservations.models import Occupancy, Reservation, SpaceAvailabilityException
from apps.reservations.taxonomy import (
    ExceptionKind,
    OccupancySource,
    ReservationPermission,
    ReservationStatus,
)
from apps.reservations.tests.factories import (
    make_occupancy,
    make_reservation,
    make_space,
    person,
)

NINE = datetime(2026, 3, 2, 14, tzinfo=UTC)
TEN = NINE + timedelta(hours=1)
ELEVEN = NINE + timedelta(hours=2)


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
