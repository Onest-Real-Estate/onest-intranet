"""Migration operations for capacity invariants that only PostgreSQL enforces.

The overlap guarantee for :class:`~apps.reservations.models.Occupancy` is a
PostgreSQL exclusion constraint over ``(space, tstzrange(starts_at, ends_at))``.
SQLite has neither ``btree_gist`` nor exclusion constraints, and the default
test database is SQLite, so an unconditional operation would break every run.

These wrappers reuse ``PostgresOnlyMixin`` from the search app: the database
half runs only on PostgreSQL and ``state_forwards`` stays a no-op, so the
constraint never enters migration state and ``makemigrations --check`` reports
no drift for a model whose ``Meta`` deliberately does not declare it.

Consequence worth stating plainly: away from PostgreSQL the race-proof
invariant does not exist, only the service-level check does. Any test that
claims to prove the invariant has to run against PostgreSQL.
"""

from __future__ import annotations

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import (
    DateTimeRangeField,
    RangeBoundary,
    RangeOperators,
)
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations
from django.db.models import Func, Q

from apps.web.search.operations import PostgresOnlyMixin

OCCUPANCY_NO_OVERLAP = "rsv_occupancy_no_overlap"


class TsTzRange(Func):
    """``tstzrange(starts_at, ends_at, '[)')`` — half-open, matching the domain."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class AddConstraintIfPostgres(PostgresOnlyMixin, migrations.AddConstraint):
    """``AddConstraint`` that is a no-op away from PostgreSQL."""


class RemoveConstraintIfPostgres(PostgresOnlyMixin, migrations.RemoveConstraint):
    """``RemoveConstraint`` that is a no-op away from PostgreSQL."""


class BtreeGistExtensionIfPostgres(BtreeGistExtension):
    """``CREATE EXTENSION btree_gist``, skipped on backends without extensions.

    Needed because the exclusion constraint mixes an equality operator on
    ``space_id`` with a range overlap operator, and only ``btree_gist`` teaches
    GiST the equality half.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)


def occupancy_no_overlap_constraint() -> ExclusionConstraint:
    """Two capacity-consuming intervals may not overlap on one space."""

    return ExclusionConstraint(
        name=OCCUPANCY_NO_OVERLAP,
        expressions=[
            ("space", RangeOperators.EQUAL),
            (
                TsTzRange("starts_at", "ends_at", RangeBoundary()),
                RangeOperators.OVERLAPS,
            ),
        ],
        condition=Q(consumes_capacity=True),
    )
