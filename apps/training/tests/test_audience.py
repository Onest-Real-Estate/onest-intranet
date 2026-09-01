"""Audience resolution for training content."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.training.audience import (
    AudienceSelector,
    visible_to,
    visible_training_content,
)
from apps.training.models import TrainingAudience, TrainingContent
from apps.training.tests.factories import office, publish_content
from apps.user.models import User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

Kind = TrainingAudience.Kind


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def assign(user, role: str, scope_type: str, scope_office=None, **window) -> None:
    assignment = UserRoleAssignment(
        user=user,
        user_id=user.pk,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
        **window,
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def person(email: str, office_slug: str = "fairfax-va") -> User:
    return completed_user(email=email, office=office(office_slug))


def slugs(rows) -> set[str]:
    return {row.slug for row in rows}


@pytest.mark.parametrize(
    ("kind", "office_slug", "reader_office", "expected"),
    [
        (Kind.COMPANY, None, "fairfax-va", True),
        (Kind.REGION, "region-mid-atlantic", "fairfax-va", True),
        (Kind.REGION, "region-mid-atlantic", "connecticut", False),
        (Kind.OFFICE, "fairfax-va", "fairfax-va", True),
        (Kind.OFFICE, "fairfax-va", "charlottesville-va", False),
    ],
)
def test_selectors_match_documented_office_scope(
    seeded, kind, office_slug, reader_office, expected
):
    row = publish_content(
        slug="notice",
        title="Notice",
        owner_office=office("onest-head-office"),
        audience=(),
    )
    TrainingAudience.objects.filter(content=row).delete()
    if kind == Kind.COMPANY:
        TrainingAudience.objects.create(content=row, kind=Kind.COMPANY)
    else:
        TrainingAudience.objects.create(
            content=row, kind=kind, office=office(office_slug)
        )
    reader = person("reader@example.com", reader_office)
    assert visible_to(reader, row) is expected


def test_role_selector_reaches_live_holders_only(seeded):
    row = publish_content(
        slug="for-coordinators",
        title="For coordinators",
        owner_office=office("onest-head-office"),
        audience=(AudienceSelector(kind=Kind.ROLE, role="transaction_coordinator"),),
    )
    holder = person("tc@example.com", "charlottesville-va")
    assign(holder, "transaction_coordinator", "office", office("charlottesville-va"))
    outsider = person("plain@example.com", "charlottesville-va")

    assert visible_to(holder, row) is True
    assert visible_to(outsider, row) is False


def test_role_selector_honours_validity_window(seeded):
    row = publish_content(
        slug="for-coordinators",
        title="For coordinators",
        owner_office=office("onest-head-office"),
        audience=(AudienceSelector(kind=Kind.ROLE, role="transaction_coordinator"),),
    )
    now = timezone.now()
    future = person("future@example.com", "fairfax-va")
    assign(
        future,
        "transaction_coordinator",
        "office",
        office("fairfax-va"),
        starts_at=now + timedelta(days=3),
    )
    assert visible_to(future, row) is False
    assert visible_to(future, row, at=now + timedelta(days=4)) is True


def test_revoked_role_assignment_closes_access(seeded):
    row = publish_content(
        slug="for-coordinators",
        title="For coordinators",
        owner_office=office("onest-head-office"),
        audience=(AudienceSelector(kind=Kind.ROLE, role="transaction_coordinator"),),
    )
    reader = person("tc@example.com", "fairfax-va")
    assign(reader, "transaction_coordinator", "office", office("fairfax-va"))
    assert visible_to(reader, row) is True

    UserRoleAssignment.objects.filter(user=reader).update(
        status=UserRoleAssignment.Status.REVOKED,
        revoked_at=timezone.now(),
    )
    assert visible_to(User.objects.get(pk=reader.pk), row) is False


def test_content_with_no_selectors_reaches_nobody(seeded):
    row = publish_content(
        slug="orphan",
        title="Orphan",
        owner_office=office("onest-head-office"),
        audience=(),
    )
    TrainingAudience.objects.filter(content=row).delete()
    reader = person("reader@example.com")
    assert visible_to(reader, row) is False
    assert slugs(visible_training_content(reader)) == set()


def test_future_publish_at_is_invisible_until_live(seeded):
    reader = person("reader@example.com")
    row = publish_content(
        slug="scheduled",
        title="Scheduled",
        owner_office=office("onest-head-office"),
    )
    row.publish_at = timezone.now() + timedelta(days=2)
    row.save(update_fields=["publish_at"])
    assert row.pk not in visible_training_content(reader).values_list("pk", flat=True)
    assert visible_to(reader, row, at=timezone.now() + timedelta(days=3)) is True


def test_archived_content_is_invisible(seeded):
    reader = person("reader@example.com")
    row = publish_content(
        slug="archived",
        title="Archived",
        owner_office=office("onest-head-office"),
    )
    row.status = TrainingContent.Status.ARCHIVED
    row.save(update_fields=["status"])
    assert row.pk not in visible_training_content(reader).values_list("pk", flat=True)
