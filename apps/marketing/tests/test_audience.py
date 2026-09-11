"""Audience resolution for marketing assets."""

from __future__ import annotations

import pytest

from apps.marketing.audience import (
    AudienceSelector,
    visible_assets,
    visible_to,
)
from apps.marketing.models import MarketingAsset, MarketingAudience
from apps.marketing.tests.factories import category, office, publish_asset
from apps.user.models import User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

Kind = MarketingAudience.Kind


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
    row = publish_asset(
        slug="notice",
        title="Notice",
        owner_office=office("onest-head-office"),
        audience=(),
        with_export=False,
    )
    MarketingAudience.objects.filter(asset=row).delete()
    if kind == Kind.COMPANY:
        MarketingAudience.objects.create(asset=row, kind=Kind.COMPANY)
    else:
        MarketingAudience.objects.create(
            asset=row, kind=kind, office=office(office_slug)
        )
    reader = person("reader@example.com", reader_office)
    assert visible_to(reader, row) is expected


def test_role_selector_reaches_live_holders_only(seeded):
    row = publish_asset(
        slug="for-coordinators",
        title="For coordinators",
        owner_office=office("onest-head-office"),
        audience=(AudienceSelector(kind=Kind.ROLE, role="transaction_coordinator"),),
        with_export=False,
    )
    holder = person("tc@example.com", "charlottesville-va")
    assign(holder, "transaction_coordinator", "office", office("charlottesville-va"))
    outsider = person("plain@example.com", "charlottesville-va")

    assert visible_to(holder, row) is True
    assert visible_to(outsider, row) is False


def test_draft_and_archived_not_visible(seeded):
    reader = person("reader@example.com")
    draft = MarketingAsset.objects.create(
        owner_office=office("onest-head-office"),
        slug="draft-logo",
        title="Draft logo",
        asset_type="logo",
        category=category(),
        status=MarketingAsset.Status.DRAFT,
    )
    MarketingAudience.objects.create(asset=draft, kind=Kind.COMPANY)

    archived = publish_asset(
        slug="archived-logo",
        title="Archived logo",
        owner_office=office("onest-head-office"),
        with_export=False,
    )
    archived.status = MarketingAsset.Status.ARCHIVED
    archived.save(update_fields=["status"])

    ids = set(visible_assets(reader).values_list("pk", flat=True))
    assert draft.pk not in ids
    assert archived.pk not in ids
