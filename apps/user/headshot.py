"""Headshot upload validation and storage utilities.

Security rules
--------------
- Accepted MIME types: image/jpeg, image/png (verified by Pillow, not header).
- Maximum file size: 5 MB.
- Minimum dimensions: 200×200 px.
- Storage filename is generated from UUID4 so client filename is never trusted.
- Pillow opens the image and verifies it is a valid image before accepting.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_DIM = 200  # px
ALLOWED_MIME = {"image/jpeg", "image/png"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PILLOW_FORMATS = {"JPEG", "PNG"}


def validate_headshot(upload) -> None:
    """Raise ValidationError if the uploaded file is unsafe or out of spec."""
    from PIL import Image, UnidentifiedImageError

    if upload.size > MAX_BYTES:
        raise ValidationError(
            _("Headshot must be smaller than 5 MB. Yours is %(mb).1f MB.")
            % {"mb": upload.size / 1024 / 1024}
        )

    suffix = Path(upload.name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationError(_("Only JPEG and PNG files are accepted for headshots."))

    # Verify the actual image content with Pillow — do not trust the extension.
    upload.seek(0)
    try:
        with Image.open(upload) as img:
            img.verify()
    except (UnidentifiedImageError, Exception) as exc:
        raise ValidationError(
            _("The file could not be read as an image. Upload a valid JPEG or PNG.")
        ) from exc

    # Re-open after verify() (verify() leaves the file in an unusable state).
    upload.seek(0)
    try:
        with Image.open(upload) as img:
            fmt = img.format
            width, height = img.size
    except Exception as exc:
        raise ValidationError(_("Could not read image dimensions.")) from exc

    if fmt not in PILLOW_FORMATS:
        raise ValidationError(_("Only JPEG and PNG images are accepted."))

    if width < MIN_DIM or height < MIN_DIM:
        raise ValidationError(
            _("Headshot must be at least %(n)d×%(n)d pixels.") % {"n": MIN_DIM}
        )

    upload.seek(0)


def headshot_upload_path(instance, filename: str) -> str:
    """Generate a UUID-based storage path; never trusts the client filename."""
    suffix = Path(filename).suffix.lower() or ".jpg"
    return f"headshots/{uuid.uuid4().hex}{suffix}"


def headshot_public_url(request, user) -> str | None:
    """Absolute browser URL for the stored headshot, when one exists."""
    if not user.headshot:
        return None
    if request.user.is_authenticated and request.user.pk == user.pk:
        # A fingerprint of the generated storage name, never the name itself:
        # the URL changes whenever the photo does, so a replaced photo is not
        # served from the browser cache and no storage path reaches the client.
        version = hashlib.sha256(user.headshot.name.encode()).hexdigest()[:12]
        return request.build_absolute_uri(f"{reverse('headshot_display')}?v={version}")
    stored = user.headshot.url
    if stored.startswith(("http://", "https://")):
        return stored
    return request.build_absolute_uri(stored)
