"""HTTPS embed validation for training video and recording content."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

PROVIDER_YOUTUBE = "youtube"
PROVIDER_VIMEO = "vimeo"
PROVIDER_MICROSOFT_STREAM = "microsoft_stream"
PROVIDER_LOOM = "loom"
PROVIDER_OTHER = "other"

ALLOWED_EMBED_HOSTS: dict[str, str] = {
    "www.youtube.com": PROVIDER_YOUTUBE,
    "youtube.com": PROVIDER_YOUTUBE,
    "youtu.be": PROVIDER_YOUTUBE,
    "player.vimeo.com": PROVIDER_VIMEO,
    "vimeo.com": PROVIDER_VIMEO,
    "web.microsoftstream.com": PROVIDER_MICROSOFT_STREAM,
    "microsoftstream.com": PROVIDER_MICROSOFT_STREAM,
    "www.loom.com": PROVIDER_LOOM,
    "loom.com": PROVIDER_LOOM,
}


@dataclass(frozen=True)
class ParsedEmbed:
    url: str
    provider: str
    host: str


def parse_embed_url(raw: str) -> ParsedEmbed | None:
    value = (raw or "").strip()
    if not value:
        return None
    if value.startswith("//"):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https":
        return None
    if not parsed.netloc:
        return None
    host = parsed.netloc.lower().removeprefix("www.")
    provider = ALLOWED_EMBED_HOSTS.get(parsed.netloc.lower())
    if provider is None:
        provider = ALLOWED_EMBED_HOSTS.get(host, PROVIDER_OTHER)
    if provider == PROVIDER_OTHER:
        return None
    return ParsedEmbed(url=value, provider=provider, host=parsed.netloc.lower())


def validate_embed_url(raw: str, *, field: str = "embed_url") -> ParsedEmbed:
    parsed = parse_embed_url(raw)
    if parsed is None:
        raise ValidationError(
            {
                field: _(
                    "Use an https:// embed URL from an approved video provider "
                    "(YouTube, Vimeo, Microsoft Stream, or Loom)."
                )
            }
        )
    return parsed


def embed_payload(parsed: ParsedEmbed) -> dict[str, str]:
    return {
        "url": parsed.url,
        "provider": parsed.provider,
        "host": parsed.host,
    }
