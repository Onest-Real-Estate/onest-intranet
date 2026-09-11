"""Background processing for marketing files.

Uploads land in ``PENDING``. This pass verifies checksums, sanitizes images,
and stores thumb/card variants on EXPORT image rows (same shape as
announcements). Source files are checksum-only.
"""

from __future__ import annotations

import io
import logging

from celery import shared_task

logger = logging.getLogger("apps.marketing")

_MIN_UPSCALE_MARGIN = 1.0


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_marketing_file(self, file_id: int) -> str:
    """Verify, sanitize, and derive one uploaded marketing file."""
    from apps.announcements.media import VARIANT_WIDTHS, checksum_of, variant_key
    from apps.marketing.models import MarketingFile

    State = MarketingFile.ProcessingState
    Role = MarketingFile.Role

    row = MarketingFile.objects.filter(pk=file_id).first()
    if row is None:
        return "missing"

    try:
        with row.file.storage.open(row.file.name, "rb") as handle:
            data = handle.read()
    except (FileNotFoundError, OSError):
        return _fail(row, State.FAILED, "The stored file could not be read.")

    if checksum_of(data) != row.checksum:
        return _fail(
            row, State.QUARANTINED, "Stored bytes do not match the upload checksum."
        )

    if not row.is_image:
        return _succeed(row, variants={})

    try:
        sanitized, size = _sanitize_image(data, row.media_type)
    except Exception as exc:  # noqa: BLE001
        logger.warning("marketing: file %s failed image pass: %s", row.pk, exc)
        return _fail(row, State.QUARANTINED, "The image could not be processed safely.")

    row.file.storage.delete(row.file.name)
    row.file.storage.save(row.file.name, io.BytesIO(sanitized))

    variants: dict[str, str] = {}
    # Only EXPORT images need library/card previews. Source packages keep the
    # original bytes without derivatives.
    if row.role == Role.EXPORT:
        for label, width in VARIANT_WIDTHS.items():
            if label == "hero":
                continue
            if size[0] < width * _MIN_UPSCALE_MARGIN:
                continue
            try:
                derived = _resize(sanitized, row.media_type, width)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "marketing: file %s variant %s failed: %s", row.pk, label, exc
                )
                continue
            key = variant_key(row.file.name, label)
            row.file.storage.delete(key)
            variants[label] = row.file.storage.save(key, io.BytesIO(derived))

    row.width, row.height = size
    row.byte_size = len(sanitized)
    row.checksum = checksum_of(sanitized)
    return _succeed(row, variants=variants)


def _pil_format(media_type: str) -> str:
    return {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(media_type, "PNG")


def _sanitize_image(data: bytes, media_type: str) -> tuple[bytes, tuple[int, int]]:
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image) or image
        if media_type == "image/jpeg" and image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
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


def _succeed(row, *, variants: dict[str, str]) -> str:
    from apps.marketing.models import MarketingFile

    row.variants = variants
    row.processing_state = MarketingFile.ProcessingState.READY
    row.processing_note = ""
    row.save(
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
    return row.processing_state


def _fail(row, state: str, note: str) -> str:
    row.processing_state = state
    row.processing_note = note[:255]
    row.save(update_fields=["processing_state", "processing_note", "updated_at"])
    logger.warning("marketing: file %s -> %s (%s)", row.pk, state, note)
    return state
