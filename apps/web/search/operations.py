"""Migration operations that only exist on PostgreSQL.

A GIN index over a ``tsvector`` and the ``pg_trgm`` extension are both
PostgreSQL features, and the test suite runs on SQLite. A migration that
created them unconditionally would fail on every CI run, so these wrappers
no-op on any other backend.

Deliberately a *no-op*, not a skip-and-warn: on SQLite the search code takes
its substring path, which needs no index to be correct — only slower, on a
database nobody serves traffic from. The state operations still run, so
``makemigrations --check`` sees the same model state on both backends and does
not report drift.
"""

from __future__ import annotations

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations
from django.db.migrations.operations.base import Operation


class PostgresOnlyMixin(Operation):
    """Run the database half only when the backend can take it.

    ``state_forwards`` is deliberately a no-op. These indexes are an
    infrastructure detail of one backend, not a fact about the model: keeping
    them out of migration state means the models do not have to declare
    PostgreSQL index classes in their ``Meta``, and
    ``makemigrations --check`` does not report drift on SQLite for an index
    that only exists on PostgreSQL.
    """

    def state_forwards(self, app_label, state):
        return

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)


class AddIndexIfPostgres(PostgresOnlyMixin, migrations.AddIndex):
    """``AddIndex`` that is a no-op away from PostgreSQL."""


class RemoveIndexIfPostgres(PostgresOnlyMixin, migrations.RemoveIndex):
    """``RemoveIndex`` that is a no-op away from PostgreSQL."""


class TrigramExtensionIfPostgres(TrigramExtension):
    """``CREATE EXTENSION pg_trgm``, skipped on backends without extensions.

    Requires the database role to be able to create extensions. On a managed
    Postgres where it cannot, install ``pg_trgm`` out of band and this becomes
    a harmless no-op — ``CREATE EXTENSION IF NOT EXISTS`` is idempotent.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)
