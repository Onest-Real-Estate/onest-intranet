"""Background processing for training media."""

from __future__ import annotations

import io
import logging

from celery import shared_task

logger = logging.getLogger("apps.training")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_training_media(self, media_id: int) -> str:
    """Verify one upload. Images are sanitized; other types checksum-only."""
    from apps.announcements.media import checksum_of
    from apps.training.models import TrainingMedia

    State = TrainingMedia.ProcessingState

    media = TrainingMedia.objects.filter(pk=media_id).first()
    if media is None:
        return "missing"

    try:
        with media.file.storage.open(media.file.name, "rb") as handle:
            data = handle.read()
    except (FileNotFoundError, OSError):
        return _fail(media, State.FAILED, "The stored file could not be read.")

    if checksum_of(data) != media.checksum:
        return _fail(
            media, State.QUARANTINED, "Stored bytes do not match the upload checksum."
        )

    if media.media_type.startswith("image/"):
        try:
            sanitized, _size = _sanitize_image(data, media.media_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning("training: media %s failed image pass: %s", media.pk, exc)
            return _fail(
                media, State.QUARANTINED, "The image could not be processed safely."
            )
        media.file.storage.delete(media.file.name)
        media.file.storage.save(media.file.name, io.BytesIO(sanitized))
        media.byte_size = len(sanitized)
        media.checksum = checksum_of(sanitized)

    return _succeed(media)


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


def _succeed(media) -> str:
    from apps.training.models import TrainingMedia

    media.processing_state = TrainingMedia.ProcessingState.READY
    media.processing_note = ""
    media.save(
        update_fields=[
            "processing_state",
            "processing_note",
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
    logger.warning("training: media %s -> %s (%s)", media.pk, state, note)
    return state
