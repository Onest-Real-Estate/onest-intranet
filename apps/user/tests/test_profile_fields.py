"""Normalization rules for the self-service professional profile fields."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from apps.user.models import User
from apps.user.profile_fields import (
    BIO_MAX_LENGTH,
    MAX_LANGUAGES,
    normalize_bio,
    normalize_languages,
    normalize_license_number,
    normalize_name,
    normalize_preferred_contact_method,
    normalize_url,
)

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("   ", ""),
        ("example.com", "https://example.com"),
        ("  https://Example.COM/Path  ", "https://example.com/Path"),
        ("http://example.com/a?b=c", "http://example.com/a?b=c"),
        ("https://example.com:8443/x", "https://example.com:8443/x"),
    ],
)
def test_normalize_url_canonicalizes(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "javascript:alert(1)",
        "ftp://example.com",
        "https://user:secret@example.com",
        "localhost",
        "https://",
    ],
)
def test_normalize_url_rejects_unsafe_or_incomplete(raw):
    with pytest.raises(ValidationError):
        normalize_url(raw)


def test_normalize_url_enforces_platform_host():
    assert (
        normalize_url(
            "linkedin.com/in/bob", allowed_hosts=("linkedin.com",), label="LinkedIn"
        )
        == "https://linkedin.com/in/bob"
    )
    assert (
        normalize_url(
            "https://www.linkedin.com/in/bob",
            allowed_hosts=("linkedin.com",),
            label="LinkedIn",
        )
        == "https://www.linkedin.com/in/bob"
    )
    with pytest.raises(ValidationError, match="LinkedIn"):
        normalize_url(
            "https://evil.example/in/bob",
            allowed_hosts=("linkedin.com",),
            label="LinkedIn",
        )


def test_normalize_url_rejects_host_suffix_lookalike():
    """``notlinkedin.com`` must not pass a ``linkedin.com`` allowlist."""
    with pytest.raises(ValidationError):
        normalize_url(
            "https://notlinkedin.com/in/bob",
            allowed_hosts=("linkedin.com",),
            label="LinkedIn",
        )


def test_normalize_url_rejects_overlong_value():
    with pytest.raises(ValidationError):
        normalize_url(f"https://example.com/{'a' * 300}")


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------


def test_normalize_languages_dedupes_and_orders():
    assert normalize_languages(["es", "en", "es", " EN "]) == ["en", "es"]


def test_normalize_languages_accepts_empty_shapes():
    assert normalize_languages(None) == []
    assert normalize_languages("") == []
    assert normalize_languages([]) == []
    assert normalize_languages("es") == ["es"]


def test_normalize_languages_rejects_unknown_code():
    with pytest.raises(ValidationError, match="not one of the languages"):
        normalize_languages(["en", "klingon"])


def test_normalize_languages_rejects_too_many():
    codes = ["en", "es", "zh", "tl", "vi", "ar", "fr", "ko", "ru", "de", "hi"]
    assert len(codes) > MAX_LANGUAGES
    with pytest.raises(ValidationError):
        normalize_languages(codes)


def test_normalize_languages_rejects_non_sequence():
    with pytest.raises(ValidationError):
        normalize_languages({"en": True})


# ---------------------------------------------------------------------------
# Text fields
# ---------------------------------------------------------------------------


def test_normalize_bio_trims_and_collapses_blank_lines():
    assert normalize_bio("  one\r\n\r\n\r\n\r\ntwo  ") == "one\n\ntwo"


def test_normalize_bio_rejects_overlong_text():
    with pytest.raises(ValidationError):
        normalize_bio("a" * (BIO_MAX_LENGTH + 1))


def test_normalize_license_number_uppercases():
    assert normalize_license_number("  va-  1234 ") == "VA- 1234"
    assert normalize_license_number("") == ""


def test_normalize_name_collapses_whitespace():
    assert normalize_name("  Bo   b ") == "Bo b"


def test_normalize_preferred_contact_method():
    assert normalize_preferred_contact_method(" Email ") == "email"
    assert normalize_preferred_contact_method("") == ""
    with pytest.raises(ValidationError):
        normalize_preferred_contact_method("carrier-pigeon")


# ---------------------------------------------------------------------------
# Model-level normalization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_clean_normalizes_professional_fields():
    user = User(
        email="bob@example.com",
        first_name="Bob",
        last_name="Lee",
        preferred_name="  Bobby  ",
        license_number=" va-1234 ",
        license_state="VA",
        website_url="example.com",
        linkedin_url="linkedin.com/in/bob",
        bio="  hello  ",
        languages=["es", "en", "en"],
        preferred_contact_method="Email",
    )
    user.full_clean(exclude=["password"])
    assert user.preferred_name == "Bobby"
    assert user.license_number == "VA-1234"
    assert user.website_url == "https://example.com"
    assert user.linkedin_url == "https://linkedin.com/in/bob"
    assert user.bio == "hello"
    assert user.languages == ["en", "es"]
    assert user.preferred_contact_method == "email"


@pytest.mark.django_db
def test_model_clean_requires_license_number_with_state():
    user = User(email="bob@example.com", license_state="VA")
    with pytest.raises(ValidationError) as excinfo:
        user.full_clean(exclude=["password"])
    assert "license_number" in excinfo.value.message_dict


@pytest.mark.django_db
def test_model_clean_rejects_absurd_license_expiry():
    user = User(
        email="bob@example.com",
        license_number="VA-1",
        license_expires_on=dt.date.today().replace(year=dt.date.today().year + 40),
    )
    with pytest.raises(ValidationError) as excinfo:
        user.full_clean(exclude=["password"])
    assert "license_expires_on" in excinfo.value.message_dict


@pytest.mark.django_db
def test_model_clean_accepts_expired_license():
    """An expired license is a fact to surface, not a value to refuse."""
    user = User(
        email="bob@example.com",
        license_number="VA-1",
        license_expires_on=dt.date(2020, 1, 1),
    )
    user.full_clean(exclude=["password"])
    assert user.license_expires_on == dt.date(2020, 1, 1)
