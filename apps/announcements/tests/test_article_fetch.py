"""SSRF validation and article fetch/extract for announcement linking."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from django.core.cache import cache

from apps.announcements.article_fetch import (
    MIN_EXTRACT_CHARS,
    ArticleFetchError,
    fetch_article_suggestions,
    load_extract,
    store_extract,
)
from apps.announcements.article_ssrf import UnsafeArticleUrl, validate_fetch_url


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_rejects_http_and_credentials_and_private_hosts():
    with pytest.raises(UnsafeArticleUrl):
        validate_fetch_url("http://example.com/story")
    with pytest.raises(UnsafeArticleUrl):
        validate_fetch_url("https://user:pass@example.com/story")
    with pytest.raises(UnsafeArticleUrl):
        validate_fetch_url("https://localhost/story")
    with pytest.raises(UnsafeArticleUrl):
        validate_fetch_url("https://127.0.0.1/story")
    with pytest.raises(UnsafeArticleUrl):
        validate_fetch_url("https://169.254.169.254/latest/meta-data")
    with pytest.raises(UnsafeArticleUrl):
        validate_fetch_url("https://example.com:8443/story")


def test_metadata_decodes_html_entities_for_authors():
    from apps.announcements.article_fetch import _truncate

    assert (
        _truncate("No, The Fed Didn&#39;t Hike Mortgage Rates Today", 180)
        == "No, The Fed Didn't Hike Mortgage Rates Today"
    )
    assert (
        _truncate("Rates &amp; fees &#8220;held&#8221;", 180) == "Rates & fees “held”"
    )


def test_rejects_when_dns_returns_private_address():
    with (
        patch(
            "apps.announcements.article_ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("10.0.0.5", 0))],
        ),
        pytest.raises(UnsafeArticleUrl),
    ):
        validate_fetch_url("https://evil.example/story")


def test_accepts_public_https_url():
    with patch(
        "apps.announcements.article_ssrf.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    ):
        safe = validate_fetch_url("https://Example.com/path?q=1#frag")
    assert safe.url == "https://example.com/path?q=1"
    assert safe.hostname == "example.com"
    assert "93.184.216.34" in safe.addresses


def _html_response(
    body: bytes,
    *,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
    location: str = "",
):
    request = httpx.Request("GET", "https://news.example/story")
    headers = {"Content-Type": content_type}
    if location:
        headers["Location"] = location
    return httpx.Response(status, headers=headers, content=body, request=request)


SAMPLE_HTML = (
    b"""<!doctype html>
<html>
<head>
  <meta property="og:title" content="Rates hold steady this week" />
  <meta property="og:description" content="Mortgage averages were unchanged Friday." />
  <meta property="og:site_name" content="Market Desk" />
  <meta property="og:image" content="https://cdn.example/hero.jpg" />
  <title>Rates hold steady this week</title>
</head>
<body>
<article>
<p>"""
    + (b"Lenders reported flat pricing across conforming loans. " * 20)
    + b"""</p>
</article>
</body>
</html>"""
)


@pytest.mark.django_db
def test_fetch_returns_suggestions_and_extract_token(django_user_model):
    user = django_user_model.objects.create_user(
        email="author@example.com", password="x"
    )
    public = [(None, None, None, None, ("93.184.216.34", 0))]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            response = _html_response(SAMPLE_HTML)

            class StreamCtx:
                def __enter__(self_inner):
                    return response

                def __exit__(self_inner, *args):
                    return False

            return StreamCtx()

    with (
        patch(
            "apps.announcements.article_ssrf.socket.getaddrinfo", return_value=public
        ),
        patch("apps.announcements.article_fetch.httpx.Client", FakeClient),
        patch(
            "apps.announcements.article_fetch.trafilatura.extract",
            return_value=("Lenders reported flat pricing. " * 30),
        ),
    ):
        suggestions = fetch_article_suggestions(user, "https://news.example/story")

    assert suggestions.title == "Rates hold steady this week"
    assert suggestions.publisher == "Market Desk"
    assert suggestions.has_extractable_text is True
    assert suggestions.image_url.endswith("hero.jpg")
    cached = load_extract(user, suggestions.extract_token)
    assert len(cached["extract_text"]) >= MIN_EXTRACT_CHARS


@pytest.mark.django_db
def test_fetch_missing_metadata_is_honest(django_user_model):
    user = django_user_model.objects.create_user(
        email="author2@example.com", password="x"
    )
    public = [(None, None, None, None, ("93.184.216.34", 0))]
    thin = b"<html><head><title>Bare</title></head><body><p>Hi</p></body></html>"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            response = _html_response(thin)

            class StreamCtx:
                def __enter__(self_inner):
                    return response

                def __exit__(self_inner, *args):
                    return False

            return StreamCtx()

    with (
        patch(
            "apps.announcements.article_ssrf.socket.getaddrinfo", return_value=public
        ),
        patch("apps.announcements.article_fetch.httpx.Client", FakeClient),
        patch(
            "apps.announcements.article_fetch.trafilatura.extract", return_value=None
        ),
    ):
        suggestions = fetch_article_suggestions(user, "https://news.example/thin")

    assert suggestions.has_extractable_text is False
    assert any("Not enough readable" in item for item in suggestions.limitations)


@pytest.mark.django_db
def test_fetch_blocks_paywalled_response(django_user_model):
    user = django_user_model.objects.create_user(
        email="author3@example.com", password="x"
    )
    public = [(None, None, None, None, ("93.184.216.34", 0))]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            response = _html_response(b"", status=403)

            class StreamCtx:
                def __enter__(self_inner):
                    return response

                def __exit__(self_inner, *args):
                    return False

            return StreamCtx()

    with (
        patch(
            "apps.announcements.article_ssrf.socket.getaddrinfo", return_value=public
        ),
        patch("apps.announcements.article_fetch.httpx.Client", FakeClient),
        pytest.raises(ArticleFetchError) as raised,
    ):
        fetch_article_suggestions(user, "https://news.example/paywall")
    assert (
        "login" in str(raised.value).lower() or "blocked" in str(raised.value).lower()
    )


@pytest.mark.django_db
def test_extract_token_is_user_scoped(django_user_model):
    a = django_user_model.objects.create_user(email="a@example.com", password="x")
    b = django_user_model.objects.create_user(email="b@example.com", password="x")
    token = store_extract(
        a,
        source_url="https://news.example/x",
        publisher="Desk",
        title="T",
        description="D",
        image_url="",
        extract_text="word " * 80,
        text_basis="extract",
    )
    with pytest.raises(ArticleFetchError):
        load_extract(b, token)


@pytest.mark.django_db
def test_redirect_to_private_host_is_refused(django_user_model):
    user = django_user_model.objects.create_user(
        email="author4@example.com", password="x"
    )
    public = [(None, None, None, None, ("93.184.216.34", 0))]
    private = [(None, None, None, None, ("10.0.0.8", 0))]
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            calls["n"] += 1
            response = _html_response(
                b"", status=302, location="https://internal.local/secret"
            )

            class StreamCtx:
                def __enter__(self_inner):
                    return response

                def __exit__(self_inner, *args):
                    return False

            return StreamCtx()

    def fake_gai(host, *args, **kwargs):
        if "internal" in host or host.endswith(".local"):
            return private
        return public

    with (
        patch(
            "apps.announcements.article_ssrf.socket.getaddrinfo", side_effect=fake_gai
        ),
        patch("apps.announcements.article_fetch.httpx.Client", FakeClient),
        pytest.raises(ArticleFetchError),
    ):
        fetch_article_suggestions(user, "https://news.example/redirect")
