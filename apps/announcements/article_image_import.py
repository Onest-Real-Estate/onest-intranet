"""Import a remote article image through the announcement hero media pipeline.

The candidate URL is re-validated for SSRF, downloaded with the same bounds as
other outbound article work, then handed to ``inspect_upload`` / ``attach_media``.
Readers never see a hotlinked remote URL.
"""

from __future__ import annotations

import logging
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.translation import gettext_lazy as _

from apps.announcements.article_ssrf import (
    UnsafeArticleUrl,
    validate_fetch_url,
)
from apps.announcements.media import HERO_EXTENSIONS
from apps.announcements.media_service import attach_media, media_payload
from apps.announcements.models import Announcement, AnnouncementMedia
from apps.user.models import User

logger = logging.getLogger(__name__)

IMAGE_TIMEOUT_SECONDS = 8.0
MAX_IMAGE_BYTES = 8 * 1024 * 1024
RATE_LIMIT_IMPORTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60

_USER_AGENT = (
    "oNEST-Hub-AnnouncementPreview/1.0 (+https://onest; hero candidate import)"
)
_IMAGE_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }
)
_EXT_FOR_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class ArticleImageImportError(ValidationError):
    """User-safe failure importing a remote hero candidate."""


class RateLimited(ValidationError):
    """The actor has asked too often inside the window."""


def _rate_key(user) -> str:
    return f"announcement:article-image:{getattr(user, 'pk', 'anon')}"


def check_import_rate_limit(user, *, now: float | None = None) -> None:
    moment = now if now is not None else time.monotonic()
    key = _rate_key(user)
    window = cache.get(key) or []
    recent = [stamp for stamp in window if moment - stamp < RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= RATE_LIMIT_IMPORTS:
        raise RateLimited(
            {
                "form": [
                    _(
                        f"You have imported {RATE_LIMIT_IMPORTS} images recently. "
                        "Wait a minute and try again."
                    )
                ]
            }
        )
    recent.append(moment)
    cache.set(key, recent, RATE_LIMIT_WINDOW_SECONDS)


def _extension_for(url: str, content_type: str) -> str:
    media = (content_type or "").split(";", 1)[0].strip().lower()
    if media in _EXT_FOR_TYPE:
        return _EXT_FOR_TYPE[media]
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix in HERO_EXTENSIONS:
        return suffix
    return ".jpg"


def _download_image(raw_url: str) -> tuple[bytes, str, str]:
    try:
        safe = validate_fetch_url(raw_url)
    except UnsafeArticleUrl as exc:
        raise ArticleImageImportError(exc.message_dict) from exc

    # Re-resolve immediately before connect.
    try:
        safe = validate_fetch_url(safe.url)
    except UnsafeArticleUrl as exc:
        raise ArticleImageImportError(exc.message_dict) from exc

    with httpx.Client(
        timeout=IMAGE_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": _USER_AGENT, "Accept": "image/*,*/*;q=0.1"},
    ) as client:
        try:
            with client.stream("GET", safe.url) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    raise ArticleImageImportError(
                        {
                            "imageUrl": _(
                                "Image redirects are not followed. "
                                "Upload a hero image manually instead."
                            )
                        }
                    )
                if response.status_code >= 400:
                    raise ArticleImageImportError(
                        {"imageUrl": _("The source image could not be downloaded.")}
                    )
                content_type = response.headers.get("Content-Type", "")
                media = content_type.split(";", 1)[0].strip().lower()
                if (
                    media
                    and media not in _IMAGE_TYPES
                    and not media.startswith("image/")
                ):
                    raise ArticleImageImportError(
                        {"imageUrl": _("That URL did not return an image.")}
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise ArticleImageImportError(
                            {
                                "imageUrl": _(
                                    "That image is too large to import as a hero."
                                )
                            }
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
        except ArticleImageImportError:
            raise
        except httpx.TimeoutException as exc:
            raise ArticleImageImportError(
                {"imageUrl": _("The source image took too long to download.")}
            ) from exc
        except httpx.HTTPError as exc:
            logger.info("article image import failed host=%s", safe.hostname)
            raise ArticleImageImportError(
                {"imageUrl": _("The source image could not be downloaded.")}
            ) from exc

    if not data:
        raise ArticleImageImportError({"imageUrl": _("That image file is empty.")})
    if len(data) > MAX_IMAGE_BYTES:
        raise ArticleImageImportError(
            {"imageUrl": _("That image is too large to import as a hero.")}
        )
    extension = _extension_for(safe.url, content_type)
    display_name = f"source-article{extension}"
    return data, display_name, content_type


def import_article_hero(
    actor: User, announcement: Announcement, image_url: str
) -> dict:
    """Download a candidate image and attach it as the announcement hero."""
    check_import_rate_limit(actor)
    data, display_name, _content_type = _download_image(image_url)
    uploaded = InMemoryUploadedFile(
        file=BytesIO(data),
        field_name="file",
        name=display_name,
        content_type=_content_type or "application/octet-stream",
        size=len(data),
        charset=None,
    )
    try:
        media = attach_media(
            actor,
            announcement,
            uploaded,
            role=AnnouncementMedia.Role.HERO,
        )
    except ValidationError as exc:
        # Preserve field messages; map file → imageUrl for the composer.
        if hasattr(exc, "message_dict") and "file" in exc.message_dict:
            raise ArticleImageImportError(
                {"imageUrl": exc.message_dict["file"]}
            ) from exc
        raise
    return media_payload(media, for_admin=True)
