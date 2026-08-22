"""Background processing for announcement media.

An upload is not readable the moment it lands. It is stored in ``PENDING`` and
this pass decides what happens next, which is the whole reason a disguised or
corrupt file can never reach a recipient: the publish gate refuses while
anything is unprocessed, and the read path refuses anything that is not
``READY``.

The pass is idempotent. Re-running it on a row that already succeeded
regenerates the same variants from the same bytes and lands on the same state,
so a retried task is never a second outcome.
"""

from __future__ import annotations

import io
import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger("apps.announcements")

#: Variants are only worth generating above their own width — upscaling a small
#: image produces a bigger file that looks worse.
_MIN_UPSCALE_MARGIN = 1.0


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_announcement_media(self, media_id: int) -> str:
    """Verify, sanitize, and derive one uploaded file.

    Returns the resulting processing state so a caller running it eagerly (or a
    test) can assert on the outcome without a second query.
    """
    from apps.announcements.media import VARIANT_WIDTHS, checksum_of, variant_key
    from apps.announcements.models import AnnouncementMedia

    State = AnnouncementMedia.ProcessingState

    media = AnnouncementMedia.objects.filter(pk=media_id).first()
    if media is None:
        # The creating transaction rolled back. Nothing to do, and nothing
        # wrong: the sweep will collect any bytes it left behind.
        return "missing"

    try:
        with media.file.storage.open(media.file.name, "rb") as handle:
            data = handle.read()
    except (FileNotFoundError, OSError):
        return _fail(media, State.FAILED, "The stored file could not be read.")

    # The checksum was taken from the bytes that were validated. If storage
    # holds something else, the thing that was checked is not the thing that
    # would be served.
    if checksum_of(data) != media.checksum:
        return _fail(
            media, State.QUARANTINED, "Stored bytes do not match the upload checksum."
        )

    if not media.is_image:
        return _succeed(media, variants={})

    try:
        sanitized, size = _sanitize_image(data, media.media_type)
    except Exception as exc:  # noqa: BLE001 - any decode failure quarantines
        logger.warning("announcements: media %s failed image pass: %s", media.pk, exc)
        return _fail(
            media, State.QUARANTINED, "The image could not be processed safely."
        )

    # Re-save the original without its metadata. EXIF can carry GPS coordinates
    # and camera serials; an announcement hero has no use for either, and the
    # file is about to be served to the whole brokerage.
    media.file.storage.delete(media.file.name)
    media.file.storage.save(media.file.name, io.BytesIO(sanitized))

    variants: dict[str, str] = {}
    for label, width in VARIANT_WIDTHS.items():
        if size[0] < width * _MIN_UPSCALE_MARGIN:
            continue
        try:
            derived = _resize(sanitized, media.media_type, width)
        except Exception as exc:  # noqa: BLE001 - one bad variant is not fatal
            logger.warning(
                "announcements: media %s variant %s failed: %s", media.pk, label, exc
            )
            continue
        key = variant_key(media.file.name, label)
        media.file.storage.delete(key)
        variants[label] = media.file.storage.save(key, io.BytesIO(derived))

    media.width, media.height = size
    media.byte_size = len(sanitized)
    media.checksum = checksum_of(sanitized)
    return _succeed(media, variants=variants)


def _pil_format(media_type: str) -> str:
    return {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(media_type, "PNG")


def _sanitize_image(data: bytes, media_type: str) -> tuple[bytes, tuple[int, int]]:
    """Decode, drop metadata, re-encode. Returns the clean bytes and the size.

    Re-encoding from a decoded bitmap is what removes the metadata: copying the
    pixel data into a fresh image leaves every EXIF, XMP, and ICC block behind
    rather than trying to enumerate and strip them.
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image) or image
        if media_type == "image/jpeg" and image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        # Copying raw pixel bytes into a fresh image is what drops the
        # metadata: nothing but the bitmap crosses over, so there is no EXIF,
        # XMP, or ICC block left to enumerate and strip.
        clean = Image.frombytes(image.mode, image.size, image.tobytes())
        buffer = io.BytesIO()
        clean.save(buffer, format=_pil_format(media_type))
        return buffer.getvalue(), clean.size


def _resize(data: bytes, media_type: str, width: int) -> bytes:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        ratio = width / image.width
        target = (width, max(1, round(image.height * ratio)))
        resized = image.resize(target, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        resized.save(buffer, format=_pil_format(media_type))
        return buffer.getvalue()


def _succeed(media, *, variants: dict[str, str]) -> str:
    from apps.announcements.models import AnnouncementMedia

    media.variants = variants
    media.processing_state = AnnouncementMedia.ProcessingState.READY
    media.processing_note = ""
    media.save(
        update_fields=[
            "variants",
            "processing_state",
            "processing_note",
            "width",
            "height",
            "byte_size",
            "checksum",
            "updated_at",
        ]
    )
    return media.processing_state


def _fail(media, state: str, note: str) -> str:
    media.processing_state = state
    media.processing_note = note[:255]
    media.save(update_fields=["processing_state", "processing_note", "updated_at"])
    logger.warning("announcements: media %s -> %s (%s)", media.pk, state, note)
    return state


@shared_task
def sweep_announcement_media_orphans() -> dict:
    """Periodic cleanup. Safe to run at any time; see ``media_service``."""
    from apps.announcements.media_service import sweep_orphan_media

    with transaction.atomic():
        report = sweep_orphan_media()
    return {
        "deleted_objects": len(report.deleted_objects),
        "deleted_rows": len(report.deleted_rows),
    }
