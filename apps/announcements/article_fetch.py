"""Fetch and extract public article metadata for announcement authors.

Suggestions stay ephemeral: the response carries reviewable candidates and an
opaque ``extractToken`` that points at short-lived cache. Nothing here writes
announcement rows or calls AI.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import extruct
import httpx
import trafilatura
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.announcements.article_ssrf import (
    MAX_REDIRECTS,
    SafeUrl,
    UnsafeArticleUrl,
    validate_fetch_url,
    validate_redirect_target,
)

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 8.0
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_EXTRACT_CHARS = 12_000
MIN_EXTRACT_CHARS = 200
EXTRACT_CACHE_TTL_SECONDS = 15 * 60
RATE_LIMIT_FETCHES = 10
RATE_LIMIT_WINDOW_SECONDS = 60

_USER_AGENT = (
    "oNEST-Hub-AnnouncementPreview/1.0 (+https://onest; article metadata only)"
)
_HTML_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "application/xhtml",
    }
)


class ArticleFetchError(ValidationError):
    """A user-safe failure while fetching or extracting an article."""


class RateLimited(ValidationError):
    """The actor has asked too often inside the window."""


@dataclass(frozen=True)
class ArticleSuggestions:
    """Ephemeral candidates for the authoring UI — not yet published fields."""

    source_url: str
    publisher: str
    title: str
    description: str
    image_url: str
    has_extractable_text: bool
    extract_token: str
    text_basis: str  # "extract" | "metadata" | "none"
    retrieved_at: str
    limitations: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "sourceUrl": self.source_url,
            "publisher": self.publisher,
            "title": self.title,
            "description": self.description,
            "imageUrl": self.image_url or None,
            "hasExtractableText": self.has_extractable_text,
            "extractToken": self.extract_token,
            "textBasis": self.text_basis,
            "retrievedAt": self.retrieved_at,
            "limitations": list(self.limitations),
            "aiConfigured": _ai_configured(),
        }


def _ai_configured() -> bool:
    from apps.contract.field_ai import field_ai_configured

    return field_ai_configured()


def _rate_limit_key(user) -> str:
    return f"announcement:article-fetch:{getattr(user, 'pk', 'anon')}"


def check_fetch_rate_limit(user, *, now: float | None = None) -> None:
    moment = now if now is not None else time.monotonic()
    key = _rate_limit_key(user)
    window = cache.get(key) or []
    recent = [stamp for stamp in window if moment - stamp < RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= RATE_LIMIT_FETCHES:
        raise RateLimited(
            {
                "form": [
                    _(
                        f"You have fetched {RATE_LIMIT_FETCHES} articles recently. "
                        "Wait a minute and try again."
                    )
                ]
            }
        )
    recent.append(moment)
    cache.set(key, recent, RATE_LIMIT_WINDOW_SECONDS)


def _cache_key(user_id: int | str, token: str) -> str:
    return f"announcement:article-extract:{user_id}:{token}"


def store_extract(
    user,
    *,
    source_url: str,
    publisher: str,
    title: str,
    description: str,
    image_url: str,
    extract_text: str,
    text_basis: str,
) -> str:
    token = uuid.uuid4().hex
    cache.set(
        _cache_key(getattr(user, "pk", "anon"), token),
        {
            "source_url": source_url,
            "publisher": publisher,
            "title": title,
            "description": description,
            "image_url": image_url,
            "extract_text": extract_text,
            "text_basis": text_basis,
            "user_id": getattr(user, "pk", None),
        },
        EXTRACT_CACHE_TTL_SECONDS,
    )
    return token


def load_extract(user, token: str) -> dict[str, Any]:
    raw = (token or "").strip()
    if not raw or len(raw) > 64:
        raise ArticleFetchError(
            {"extractToken": _("Fetch the article again, then generate a summary.")}
        )
    payload = cache.get(_cache_key(getattr(user, "pk", "anon"), raw))
    if not isinstance(payload, dict):
        raise ArticleFetchError(
            {
                "extractToken": _(
                    "That article preview expired. Fetch the details again."
                )
            }
        )
    if payload.get("user_id") != getattr(user, "pk", None):
        raise ArticleFetchError(
            {"extractToken": _("That article preview is not available.")}
        )
    return payload


def _content_type_ok(header: str | None) -> bool:
    if not header:
        return False
    media = header.split(";", 1)[0].strip().lower()
    return media in _HTML_TYPES or media.startswith("text/html")


def _fetch_html(safe: SafeUrl) -> tuple[str, bytes, str]:
    """Return (final_url, body, content_type) after SSRF-checked hops.

    Each hop re-resolves and re-validates before connect. TLS uses the real
    hostname (IP-pinned connects break certificate verification).
    """
    current = safe
    with httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    ) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            # Re-check DNS immediately before connect (rebinding window).
            try:
                current = validate_fetch_url(current.url)
            except UnsafeArticleUrl as exc:
                raise ArticleFetchError(exc.message_dict) from exc
            try:
                with client.stream("GET", current.url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location", "")
                        try:
                            current = validate_redirect_target(
                                location, base_url=current.url
                            )
                        except UnsafeArticleUrl as exc:
                            raise ArticleFetchError(exc.message_dict) from exc
                        continue

                    if response.status_code in {401, 403}:
                        raise ArticleFetchError(
                            {
                                "url": _(
                                    "That page is blocked or requires a login. "
                                    "Paste the details manually."
                                )
                            }
                        )
                    if response.status_code == 404:
                        raise ArticleFetchError({"url": _("That page was not found.")})
                    if response.status_code >= 400:
                        raise ArticleFetchError(
                            {"url": _("The article page could not be fetched.")}
                        )

                    content_type = response.headers.get("Content-Type", "")
                    if not _content_type_ok(content_type):
                        raise ArticleFetchError(
                            {"url": _("That URL did not return an HTML article page.")}
                        )

                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_HTML_BYTES:
                            raise ArticleFetchError(
                                {"url": _("That page is too large to preview safely.")}
                            )
                        chunks.append(chunk)
                    return current.url, b"".join(chunks), content_type
            except ArticleFetchError:
                raise
            except httpx.TimeoutException as exc:
                raise ArticleFetchError(
                    {"url": _("The site took too long to respond.")}
                ) from exc
            except httpx.HTTPError as exc:
                logger.info("article fetch failed host=%s", current.hostname)
                raise ArticleFetchError(
                    {"url": _("The article page could not be fetched.")}
                ) from exc

    raise ArticleFetchError({"url": _("Too many redirects from that URL.")})


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    nested = (
                        item.get("content") or item.get("@value") or item.get("name")
                    )
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
    return ""


def _truncate(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _extract_metadata(html: bytes, base_url: str) -> dict[str, str]:
    try:
        decoded = html.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        decoded = html.decode("latin-1", errors="replace")

    try:
        data = extruct.extract(
            decoded,
            base_url=base_url,
            syntaxes=["opengraph", "microdata", "json-ld", "rdfa"],
            uniform=True,
        )
    except Exception:  # noqa: BLE001
        logger.info("extruct failed for article preview")
        data = {}

    og_list = data.get("opengraph") or []
    og = og_list[0] if isinstance(og_list, list) and og_list else {}
    if not isinstance(og, dict):
        og = {}

    json_ld = data.get("json-ld") or []
    ld: dict[str, Any] = {}
    if isinstance(json_ld, list):
        for item in json_ld:
            if isinstance(item, dict) and (
                str(item.get("@type", "")).lower()
                in {"newsarticle", "article", "webpage"}
                or "headline" in item
                or "name" in item
            ):
                ld = item
                break

    # Fallback: crude meta tags when extruct is sparse.
    title = _first_str(
        og.get("og:title"),
        og.get("title"),
        ld.get("headline"),
        ld.get("name"),
    )
    description = _first_str(
        og.get("og:description"),
        og.get("description"),
        ld.get("description"),
    )
    image = _first_str(
        og.get("og:image"),
        og.get("og:image:url"),
        ld.get("image"),
    )
    if isinstance(ld.get("image"), dict):
        image = _first_str(image, ld["image"].get("url"))
    publisher = _first_str(
        og.get("og:site_name"),
        og.get("og:site"),
        (ld.get("publisher") or {}).get("name")
        if isinstance(ld.get("publisher"), dict)
        else ld.get("publisher"),
    )
    if not publisher:
        host = urlparse(base_url).hostname or ""
        publisher = host.removeprefix("www.")

    if not title:
        match = re.search(
            r"<title[^>]*>(.*?)</title>", decoded, flags=re.IGNORECASE | re.DOTALL
        )
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip()
    if not description:
        match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            decoded,
            flags=re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                decoded,
                flags=re.IGNORECASE,
            )
        if match:
            description = match.group(1).strip()

    # Absolute-ize relative image URLs without fetching them.
    if image and image.startswith("/"):
        parsed = urlparse(base_url)
        image = f"{parsed.scheme}://{parsed.netloc}{image}"

    return {
        "title": _truncate(title, 180),
        "description": _truncate(description, 500),
        "image_url": image[:2000] if image else "",
        "publisher": _truncate(publisher, 120),
    }


def _extract_text(html: bytes, url: str) -> str:
    try:
        decoded = html.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        decoded = html.decode("latin-1", errors="replace")
    try:
        text = trafilatura.extract(
            decoded,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_recall=False,
        )
    except Exception:  # noqa: BLE001
        logger.info("trafilatura failed for article preview")
        text = None
    if not text:
        return ""
    return _truncate(text, MAX_EXTRACT_CHARS)


def fetch_article_suggestions(user, raw_url: str) -> ArticleSuggestions:
    """Authorize, fetch, extract, cache extract text, return reviewable suggestions."""
    check_fetch_rate_limit(user)
    try:
        safe = validate_fetch_url(raw_url)
    except UnsafeArticleUrl as exc:
        raise ArticleFetchError(exc.message_dict) from exc

    final_url, html, _content_type = _fetch_html(safe)
    meta = _extract_metadata(html, final_url)
    extract = _extract_text(html, final_url)

    limitations: list[str] = []
    if not meta["title"]:
        limitations.append("No headline was found in the page metadata.")
    if not meta["description"]:
        limitations.append("No description was found in the page metadata.")
    if not meta["image_url"]:
        limitations.append("No preview image was found.")
    if len(extract) < MIN_EXTRACT_CHARS:
        limitations.append(
            "Not enough readable article text was retrieved for an AI summary."
        )
        text_basis = "metadata" if (meta["title"] or meta["description"]) else "none"
        has_extract = False
        extract_for_cache = ""
    else:
        text_basis = "extract"
        has_extract = True
        extract_for_cache = extract
        limitations.append(
            "Metadata and extracted text are unverified suggestions — "
            "review before publishing."
        )

    if meta["image_url"]:
        limitations.append(
            "The source image is a candidate only. Confirm you have rights "
            "before importing it as the hero."
        )

    token = store_extract(
        user,
        source_url=final_url,
        publisher=meta["publisher"],
        title=meta["title"],
        description=meta["description"],
        image_url=meta["image_url"],
        extract_text=extract_for_cache,
        text_basis=text_basis,
    )
    return ArticleSuggestions(
        source_url=final_url,
        publisher=meta["publisher"],
        title=meta["title"],
        description=meta["description"],
        image_url=meta["image_url"],
        has_extractable_text=has_extract,
        extract_token=token,
        text_basis=text_basis,
        retrieved_at=timezone.now().isoformat(),
        limitations=tuple(limitations),
    )
