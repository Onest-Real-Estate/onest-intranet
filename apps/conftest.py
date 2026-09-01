"""Shared pytest fixtures for the apps/ test tree."""

from __future__ import annotations

import pytest


def _seed_announcement_categories() -> None:
    from apps.announcements.models import AnnouncementCategory
    from apps.announcements.taxonomy import CATEGORY_SEED

    for item in CATEGORY_SEED:
        AnnouncementCategory.objects.update_or_create(
            code=item.code,
            defaults={"is_system": True},
            create_defaults={
                "code": item.code,
                "label": item.label,
                "description": item.description,
                "display_order": item.display_order,
                "is_active": True,
                "is_system": True,
            },
        )


def _seed_training_categories() -> None:
    from apps.training.models import TrainingCategory
    from apps.training.taxonomy import CATEGORY_SEED

    for item in CATEGORY_SEED:
        TrainingCategory.objects.update_or_create(
            code=item.code,
            defaults={"is_system": True},
            create_defaults={
                "code": item.code,
                "label": item.label,
                "description": item.description,
                "display_order": item.display_order,
                "is_active": True,
                "is_system": True,
            },
        )


@pytest.fixture(autouse=True)
def _ensure_reference_seed_data(db):
    """Reapply canonical offices and taxonomy before each database test.

    Migrations seed the office tree and governed category rows once when the
    test database is created. ``django_db(transaction=True)`` suites and
    threaded concurrency tests commit outside the per-test rollback savepoint,
    so a long ``--reuse-db`` run can leave later tests without ``fairfax-va``
    or ``company_announcement``. The helpers are idempotent.
    """
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()
    _seed_announcement_categories()
    _seed_training_categories()
