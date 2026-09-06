from __future__ import annotations

from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MAX_SPACE_PHOTO_BYTES = 8 * 1024 * 1024
SPACE_PHOTO_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
SPACE_PHOTO_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


def validate_space_photo(upload) -> None:
    """Verify size, extension, and image bytes without trusting client metadata."""
    if not upload or getattr(upload, "_committed", False):
        return

    if upload.size > MAX_SPACE_PHOTO_BYTES:
        raise ValidationError(_("Space photos must be no larger than 8 MB."))

    suffix = Path(upload.name).suffix.lower()
    if suffix not in SPACE_PHOTO_EXTENSIONS:
        raise ValidationError(_("Only JPEG, PNG, and WebP photos are accepted."))

    from PIL import Image, UnidentifiedImageError

    upload.seek(0)
    try:
        with Image.open(upload) as image:
            image.verify()
        upload.seek(0)
        with Image.open(upload) as image:
            image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError(_("Upload a valid JPEG, PNG, or WebP image.")) from exc
    finally:
        upload.seek(0)

    if image_format not in SPACE_PHOTO_FORMATS:
        raise ValidationError(_("Only JPEG, PNG, and WebP photos are accepted."))
