"""AI summarization for linked announcement articles."""

from __future__ import annotations

import urllib.error
from email.message import EmailMessage
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.announcements.article_ai import (
    ArticleAiError,
    _article_ai_http_message,
    summarize_article,
)
from apps.announcements.article_fetch import store_extract


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_summarize_refuses_when_ai_unconfigured(django_user_model, settings):
    settings.CONTRACT_FIELD_AI_ENDPOINT = ""
    settings.CONTRACT_FIELD_AI_API_KEY = ""
    user = django_user_model.objects.create_user(email="a@example.com", password="x")
    token = store_extract(
        user,
        source_url="https://news.example/x",
        publisher="Desk",
        title="Rates hold",
        description="",
        image_url="",
        extract_text="Lenders reported flat pricing across conforming loans. " * 20,
        text_basis="extract",
    )
    with pytest.raises(ArticleAiError):
        summarize_article(user, token)


@pytest.mark.django_db
def test_summarize_refuses_thin_metadata_only(django_user_model, settings):
    settings.CONTRACT_FIELD_AI_ENDPOINT = "https://api.openai.com/v1"
    settings.CONTRACT_FIELD_AI_API_KEY = "test-key"
    user = django_user_model.objects.create_user(email="b@example.com", password="x")
    token = store_extract(
        user,
        source_url="https://news.example/x",
        publisher="Desk",
        title="Rates hold",
        description="A short blurb",
        image_url="",
        extract_text="",
        text_basis="metadata",
    )
    with pytest.raises(ArticleAiError) as raised:
        summarize_article(user, token)
    assert "Not enough readable" in str(raised.value)


@pytest.mark.django_db
def test_summarize_returns_reviewable_copy(django_user_model, settings):
    settings.CONTRACT_FIELD_AI_ENDPOINT = "https://api.openai.com/v1"
    settings.CONTRACT_FIELD_AI_API_KEY = "test-key"
    user = django_user_model.objects.create_user(email="c@example.com", password="x")
    extract = (
        "Average 30-year mortgage rates held steady at 6.4 percent this week, "
        "according to the Market Desk survey of lenders. Purchase applications "
        "rose slightly while refinances remained soft. Borrowers shopping this "
        "weekend should compare quotes before locking. " * 2
    )
    token = store_extract(
        user,
        source_url="https://news.example/rates",
        publisher="Market Desk",
        title="Rates hold steady",
        description="",
        image_url="",
        extract_text=extract,
        text_basis="extract",
    )

    teaser = (
        "Thirty-year mortgage averages held at 6.4 percent this week as purchase "
        "applications edged higher."
    )
    digest = (
        "Market Desk reports 30-year averages held at 6.4 percent this week. "
        "Purchase applications rose slightly while refinances stayed soft. "
        "Shoppers comparing quotes before a weekend lock should treat the survey "
        "as a guide, not a quote."
    )

    with patch(
        "apps.announcements.article_ai._call_chat",
        return_value={"teaser": teaser, "digest": digest},
    ):
        payload = summarize_article(user, token)

    assert payload["teaser"] == teaser
    assert payload["digest"] == digest
    assert payload["textBasis"] == "extract"
    assert "AI-generated" in payload["label"]
    assert payload["teaser"].lower().startswith("thirty")


@pytest.mark.django_db
def test_summarize_maps_provider_busy_to_clear_message(django_user_model, settings):
    settings.CONTRACT_FIELD_AI_ENDPOINT = "https://api.openai.com/v1"
    settings.CONTRACT_FIELD_AI_API_KEY = "test-key"
    user = django_user_model.objects.create_user(email="d@example.com", password="x")
    token = store_extract(
        user,
        source_url="https://news.example/rates",
        publisher="Market Desk",
        title="Rates hold steady",
        description="",
        image_url="",
        extract_text=("Lenders reported flat pricing across conforming loans. " * 20),
        text_basis="extract",
    )
    headers = EmailMessage()
    error = urllib.error.HTTPError(
        url="https://api.openai.com/v1/chat/completions",
        code=503,
        msg="Unavailable",
        hdrs=headers,
        fp=None,
    )
    with (
        patch(
            "apps.announcements.article_ai.urllib.request.urlopen",
            side_effect=error,
        ),
        pytest.raises(ArticleAiError) as raised,
    ):
        summarize_article(user, token)
    message = str(raised.value)
    assert "busy" in message.lower() or "rate-limited" in message.lower()
    assert "Field AI" not in message


def test_article_ai_http_message_covers_busy_statuses():
    assert "busy" in _article_ai_http_message(503).lower()
    assert "rate-limited" in _article_ai_http_message(429).lower()
    assert "Field AI" not in _article_ai_http_message(500)


def test_parse_json_payload_accepts_markdown_fences_and_aliases():
    from apps.announcements.article_ai import _parse_json_payload

    fenced = _parse_json_payload(
        '```json\n{"teaser": "Rates held steady.", "digest": "Lenders paused."}\n```'
    )
    assert fenced["teaser"] == "Rates held steady."
    assert fenced["digest"] == "Lenders paused."

    aliased = _parse_json_payload(
        '{"summary": "Rates held steady.", "body": "Lenders paused for now."}'
    )
    assert aliased["teaser"] == "Rates held steady."
    assert aliased["digest"] == "Lenders paused for now."


def test_message_content_joins_list_parts():
    from apps.announcements.article_ai import _message_content

    text = _message_content(
        {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": '{"teaser":"A","digest":"B"}'}
                        ]
                    }
                }
            ]
        }
    )
    assert '"teaser"' in text
