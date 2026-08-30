"""Redaction, same-origin, and disclosure.

The acceptance criterion this file exists for: *authenticated users submit
feedback without leaking secrets in diagnostics*. Every test below is a
concrete secret somebody could plausibly have in their address bar when
something breaks and they reach for the support form.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.feedback.diagnostics import (
    ALLOWED_METADATA_KEYS,
    REDACTED,
    build_diagnostics,
    clean_metadata,
    disclosure_lines,
    redact_url,
)

HOSTS = {"hub.onest.test", "localhost"}


def scrub(url: str) -> str:
    return redact_url(url, allowed_hosts=HOSTS)


# --------------------------------------------------------------------------- #
# The URL
# --------------------------------------------------------------------------- #


def test_a_plain_path_survives_untouched():
    assert scrub("/operations/tasks") == "/operations/tasks"


def test_an_allowlisted_filter_is_kept_because_it_helps_triage():
    assert scrub("/users?page=3&status=active") == "/users?page=3&status=active"


@pytest.mark.parametrize(
    "url",
    [
        "/reset?token=abc123def456",
        "/invite?code=SEKRIT",
        "/download?signature=xyz&expires=99",
        "/sso?state=opaque&nonce=another",
        "/thing?access_token=abc&refresh_token=def",
        "/p?session=1&sessionid=2&csrftoken=3",
    ],
)
def test_every_parameter_outside_the_allowlist_is_dropped(url):
    """An allowlist, not a denylist.

    The next secret-bearing parameter name is one nobody has thought of, so
    anything unrecognised goes — including ones this test does not enumerate.
    """
    cleaned = scrub(url)
    assert "?" not in cleaned or cleaned.endswith("?") is False
    for leak in ("abc123def456", "SEKRIT", "xyz", "opaque", "abc", "1", "3"):
        assert leak not in cleaned.split("?", 1)[-1] or "?" not in cleaned


def test_an_allowlisted_key_still_loses_a_value_that_looks_like_a_credential():
    """`q` is a search box, and people paste tokens into search boxes."""
    cleaned = scrub("/search?q=eyJhbGciOiJIUzI1NiJ9payload")
    assert cleaned == f"/search?q={REDACTED}"


@pytest.mark.parametrize(
    "value",
    [
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "sk-livekeymaterialgoeshere",
        "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "A" * 40,
    ],
)
def test_credential_shapes_are_recognised_wherever_they_appear(value):
    assert scrub(f"/search?q={value}") == f"/search?q={REDACTED}"


def test_the_fragment_never_survives():
    """Invisible to the server in normal operation, and a favourite place to
    park a token."""
    assert scrub("/page?page=2#access_token=secret") == "/page?page=2"


def test_a_url_on_another_host_is_refused_rather_than_stored():
    with pytest.raises(ValidationError):
        scrub("https://evil.example/steal?page=1")


def test_our_own_absolute_url_is_accepted():
    assert scrub("https://hub.onest.test/dashboard?page=1") == (
        "https://hub.onest.test/dashboard?page=1"
    )


def test_a_non_web_scheme_is_refused():
    with pytest.raises(ValidationError):
        scrub("javascript:alert(1)")


def test_credentials_embedded_in_the_authority_do_not_smuggle_a_host_past():
    with pytest.raises(ValidationError):
        scrub("https://hub.onest.test@evil.example/x")


def test_an_absurdly_long_url_is_refused_before_anything_parses_it():
    with pytest.raises(ValidationError):
        scrub("/x?" + "a" * 3000)


def test_an_empty_url_is_simply_empty():
    assert scrub("") == ""


# --------------------------------------------------------------------------- #
# Browser metadata
# --------------------------------------------------------------------------- #


def test_only_allowlisted_keys_survive():
    cleaned = clean_metadata(
        {
            "viewport": "1280x720",
            "locale": "en-US",
            "cookies": "session=abc",
            "localStorage": "{...}",
            "userAgent": "everything about me",
        }
    )
    assert cleaned == {"viewport": "1280x720", "locale": "en-US"}


def test_a_value_that_does_not_match_its_declared_shape_is_dropped():
    """The shape check is the point: a viewport is "1280x720" and anything
    else is something the client should not be sending."""
    assert clean_metadata({"viewport": "; DROP TABLE feedback"}) == {}
    assert clean_metadata({"timezone": "../../etc/passwd"}) == {}


def test_metadata_that_is_not_a_mapping_is_ignored():
    assert clean_metadata("everything") == {}
    assert clean_metadata(None) == {}
    assert clean_metadata([1, 2, 3]) == {}


def test_a_credential_shaped_metadata_value_is_dropped():
    assert clean_metadata({"platform": "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaa"}) == {}


def test_values_are_capped_so_metadata_cannot_become_a_payload():
    cleaned = clean_metadata({"browser": "Chrome " + "x" * 500})
    assert len(cleaned.get("browser", "")) <= 80


# --------------------------------------------------------------------------- #
# Disclosure
# --------------------------------------------------------------------------- #


def test_the_disclosure_names_every_field_actually_captured():
    """The promise is generated from the constants that do the capturing, so
    widening the capture rewrites the disclosure automatically."""
    text = " ".join(disclosure_lines())
    for key in ALLOWED_METADATA_KEYS:
        assert key in text


def test_build_diagnostics_applies_both_halves():
    diagnostics = build_diagnostics(
        page_url="/x?token=leak&page=2#frag",
        metadata={"viewport": "800x600", "cookies": "no"},
        allowed_hosts=HOSTS,
    )
    assert diagnostics.page_url == "/x?page=2"
    assert diagnostics.metadata == {"viewport": "800x600"}
