"""HTTP surface for article fetch / summarize / hero import."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.announcements.article_fetch import ArticleSuggestions
from apps.announcements.tests.test_administration import (
    draft_for,
    regional_publisher,
)


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


@pytest.mark.django_db
def test_article_fetch_requires_manage(client, seeded):
    response = client.post(
        reverse("announcement_article_fetch"),
        data={"url": "https://news.example/x"},
        content_type="application/json",
    )
    assert response.status_code in {302, 401, 403}


@pytest.mark.django_db
def test_article_fetch_json_success(client, seeded):
    actor = regional_publisher()
    client.force_login(actor)
    suggestions = ArticleSuggestions(
        source_url="https://news.example/story",
        publisher="Desk",
        title="Headline",
        description="Blurb",
        image_url="",
        has_extractable_text=False,
        extract_token="abc",
        text_basis="metadata",
        retrieved_at="2026-09-17T12:00:00+00:00",
        limitations=("No preview image was found.",),
    )
    with patch(
        "apps.announcements.administration_views.fetch_article_suggestions",
        return_value=suggestions,
    ):
        response = client.post(
            reverse("announcement_article_fetch"),
            data={"url": "https://news.example/story"},
            content_type="application/json",
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["suggestions"]["title"] == "Headline"
    assert payload["suggestions"]["extractToken"] == "abc"


@pytest.mark.django_db
def test_article_import_hero_unknown_id_is_404(client, seeded):
    actor = regional_publisher()
    client.force_login(actor)
    response = client.post(
        reverse("announcement_article_import_hero", args=[999_999]),
        data={"image_url": "https://cdn.example/a.jpg"},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_source_fields_survive_draft_update(client, seeded):
    actor = regional_publisher()
    announcement = draft_for(actor, owner_slug="harrisburg")
    office_ids = list(
        announcement.audiences.filter(kind="office").values_list("office_id", flat=True)
    )
    client.force_login(actor)
    response = client.post(
        reverse("announcement_update", args=[announcement.pk]),
        data={
            "owner_office": announcement.owner_office_id,
            "title": announcement.title,
            "summary": announcement.summary,
            "body": announcement.body,
            "category": announcement.category.code if announcement.category else "",
            "priority": announcement.priority,
            "cta_label": "",
            "cta_url": "",
            "source_url": "https://news.example/story",
            "source_publisher": "Market Desk",
            "source_retrieved_at": "2026-09-17T12:00:00+00:00",
            "ai_assisted_summary": "1",
            "ai_assisted_body": "false",
            "audience_offices": office_ids,
            "expected_version": announcement.updated_at.isoformat(),
        },
        content_type="application/json",
    )
    assert response.status_code in {302, 303}
    announcement.refresh_from_db()
    assert announcement.source_url == "https://news.example/story"
    assert announcement.source_publisher == "Market Desk"
    assert announcement.ai_assisted_summary is True
    assert announcement.ai_assisted_body is False
