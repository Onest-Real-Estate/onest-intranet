"""Marketing administration: lifecycle, versioning, concurrency, audience."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from apps.audit.models import DomainEvent
from apps.marketing.administration import (
    StaleMarketingVersion,
    asset_version,
    create_asset,
    duplicate_version,
    transition,
    update_asset,
)
from apps.marketing.audience import AudienceSelector, assert_can_target
from apps.marketing.models import MarketingAsset
from apps.marketing.tests.factories import (
    assign,
    category,
    mark_exports_ready,
    office,
    publish_asset,
)
from apps.user.models import User
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return User.objects.get(pk=user.pk)


def publisher(*, slug="fairfax-va", email="mkt-admin@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, "system_admin", "company")
    return grant(
        user,
        "manage_marketing_resources",
        "publish_marketing_resources",
        "download_marketing_sources",
    )


def regional_publisher(*, email="mkt-regional@example.com") -> User:
    user = completed_user(email=email, office=office("region-mid-atlantic"))
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    return grant(
        user,
        "manage_marketing_resources",
        "publish_marketing_resources",
    )


def _draft(actor: User, **overrides) -> MarketingAsset:
    cleaned = {
        "title": "Logo pack",
        "description": "Summary",
        "usage_instructions": "Use on listings",
        "category": category(),
        "asset_type": "logo",
        "publish_at": None,
        "expires_at": None,
        "jurisdiction_state_codes": [],
        "brand_codes": [],
        "display_order": 100,
    }
    cleaned.update(overrides)
    return create_asset(
        actor=actor,
        office=office("fairfax-va"),
        cleaned=cleaned,
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
    )


@pytest.mark.django_db
def test_create_draft_publish_emits_domain_event(seeded):
    from apps.marketing.tests.factories import attach_ready_export

    actor = publisher()
    draft = _draft(actor)
    assert draft.status == MarketingAsset.Status.DRAFT
    attach_ready_export(draft, actor=actor)
    transition(
        actor=actor,
        asset=draft,
        action="publish",
        expected_version=asset_version(draft),
    )
    draft.refresh_from_db()
    assert draft.status == MarketingAsset.Status.PUBLISHED
    assert DomainEvent.objects.filter(name="marketing.published").exists()


@pytest.mark.django_db
def test_duplicate_version_and_publish_supersedes_previous(seeded):
    actor = publisher()
    live = publish_asset(
        slug="compliance-pack",
        title="Compliance pack",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    draft = duplicate_version(
        actor=actor, asset=live, expected_version=asset_version(live)
    )
    assert draft.status == MarketingAsset.Status.DRAFT
    assert draft.version_family == live.version_family
    assert draft.version_number == 2

    mark_exports_ready(draft)
    transition(
        actor=actor,
        asset=draft,
        action="publish",
        expected_version=asset_version(draft),
    )
    live.refresh_from_db()
    draft.refresh_from_db()
    assert draft.status == MarketingAsset.Status.PUBLISHED
    assert live.status == MarketingAsset.Status.ARCHIVED
    assert DomainEvent.objects.filter(name="marketing.published").exists()
    assert DomainEvent.objects.filter(name="marketing.archived").exists()


@pytest.mark.django_db
def test_assert_can_target_denies_company_for_non_company_admin(seeded):
    actor = regional_publisher()
    with pytest.raises(PermissionDenied):
        assert_can_target(actor, [AudienceSelector(kind="company")])


@pytest.mark.django_db
def test_stale_version_returns_409_on_update(seeded, client: Client):
    actor = publisher()
    draft = _draft(actor)
    client.force_login(actor)
    response = client.post(
        reverse("marketing_update", args=[draft.pk]),
        data=json.dumps(
            {
                "title": "Changed title",
                "description": draft.description,
                "usage_instructions": draft.usage_instructions,
                "category": "logos",
                "asset_type": "logo",
                "audience_offices": [str(office("fairfax-va").pk)],
                "expected_version": "not-the-token",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_stale_version_refuses_service_update(seeded):
    actor = publisher()
    draft = _draft(actor)
    with pytest.raises(StaleMarketingVersion):
        update_asset(
            actor=actor,
            asset=draft,
            cleaned={"title": "Changed"},
            selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
            expected_version="not-the-token",
        )


@pytest.mark.django_db
def test_json_create_path(seeded, client: Client):
    actor = publisher()
    client.force_login(actor)
    response = client.post(
        reverse("marketing_create"),
        data=json.dumps(
            {
                "owner_office": str(office("fairfax-va").pk),
                "title": "JSON draft",
                "description": "",
                "usage_instructions": "",
                "category": "logos",
                "asset_type": "logo",
                "display_order": 100,
                "audience_offices": [str(office("fairfax-va").pk)],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {302, 303}, response.content[:2000]
    assert MarketingAsset.objects.filter(title="JSON draft").exists()


@pytest.mark.django_db
def test_create_sheet_defaults_display_order_when_omitted(seeded, client: Client):
    """The create modal does not collect display_order; default to 100."""
    actor = publisher()
    client.force_login(actor)
    response = client.post(
        reverse("marketing_create"),
        data=json.dumps(
            {
                "owner_office": str(office("fairfax-va").pk),
                "title": "No order field",
                "description": "Summary",
                "category": "templates",
                "asset_type": "template",
                "audience_company": "on",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {302, 303}, response.content[:2000]
    created = MarketingAsset.objects.get(title="No order field")
    assert created.display_order == 100
