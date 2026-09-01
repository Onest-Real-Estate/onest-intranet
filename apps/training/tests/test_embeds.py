"""Embed and rich-text validation."""

import pytest
from django.core.exceptions import ValidationError

from apps.training.embeds import parse_embed_url, validate_embed_url


def test_rejects_non_https_embed():
    with pytest.raises(ValidationError):
        validate_embed_url("http://www.youtube.com/watch?v=abc")


def test_accepts_youtube_embed():
    parsed = validate_embed_url("https://www.youtube.com/watch?v=abc12345678")
    assert parsed.provider == "youtube"


def test_rejects_unknown_host():
    assert parse_embed_url("https://evil.example/video") is None
