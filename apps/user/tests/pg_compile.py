"""Compile a queryset with the PostgreSQL backend without touching a socket.

Local pytest and CI both run on SQLite, which drops row locking entirely, so a
``FOR UPDATE`` that PostgreSQL would reject sails through the test suite and
only fails on a deployed request. Compiling the real production queryset with
the PostgreSQL compiler closes that gap. Building the wrapper directly never
opens a connection — ``as_sql()`` only reads the backend's operations and
feature flags.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Model, QuerySet


def postgresql_backend() -> Any:
    """A PostgreSQL ``DatabaseWrapper`` that never opens a socket."""
    from django.db.backends.postgresql.base import DatabaseWrapper

    # django-stubs types settings_dict too narrowly for a literal like this.
    settings_dict: Any = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "compile-only",
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "OPTIONS": {},
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "AUTOCOMMIT": True,
        "ATOMIC_REQUESTS": False,
        "TIME_ZONE": None,
        "TEST": {},
    }
    return DatabaseWrapper(settings_dict, alias="pg_compile_only")


def compile_for_postgresql(queryset: QuerySet[Any], monkeypatch: Any) -> str:
    """Return the SQL PostgreSQL would run for ``queryset``."""
    postgres = postgresql_backend()
    # The compiler refuses to emit FOR UPDATE outside a transaction, and
    # answering that question is the one thing here that would need a socket.
    monkeypatch.setattr(postgres, "get_autocommit", lambda: False)

    sql, _params = queryset.query.get_compiler(connection=postgres).as_sql()
    return sql


def compile_constraint_for_postgresql(constraint: Any, model: type[Model]) -> str:
    """Return the DDL PostgreSQL would run to add ``constraint`` to ``model``."""
    postgres = postgresql_backend()
    with postgres.schema_editor(collect_sql=True, atomic=False) as editor:
        return str(constraint.create_sql(model, editor))
