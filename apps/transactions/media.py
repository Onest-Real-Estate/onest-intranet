"""Allowed transaction-document file matrix and upload inspection."""

from __future__ import annotations

from typing import Any

from apps.announcements.media import (
    ALLOWED_MEDIA,
    InspectedUpload,
    MediaRule,
    checksum_of,
    detect_media_type,
    safe_display_name,
)
from apps.announcements.media import (
    storage_key as _announcement_storage_key,
)

_MB = 1024 * 1024

TRANSACTION_ALLOWED_MEDIA: dict[str, MediaRule] = {
    ".pdf": ALLOWED_MEDIA[".pdf"],
    ".png": ALLOWED_MEDIA[".png"],
    ".jpg": ALLOWED_MEDIA[".jpg"],
    ".jpeg": ALLOWED_MEDIA[".jpeg"],
    ".webp": ALLOWED_MEDIA[".webp"],
}

MAX_TRANSACTION_DOCUMENTS = 40
MAX_UPLOAD_BATCH = 10
ORPHAN_GRACE_HOURS = 6
ABANDONED_PENDING_DAYS = 14


def storage_key(display_name: str, *, prefix: str = "transactions") -> str:
    extension = safe_display_name(display_name).rsplit(".", 1)[-1].lower()
    allowed = f".{extension}" in TRANSACTION_ALLOWED_MEDIA
    ext = f".{extension}" if extension and allowed else ""
    if ext:
        import uuid

        return f"{prefix}/{uuid.uuid4().hex}{ext}"
    return _announcement_storage_key(display_name, prefix=prefix)


def inspect_transaction_upload(uploaded, *, field: str = "file"):
    from django.core.exceptions import ValidationError
    from django.utils.translation import gettext_lazy as _

    from apps.announcements.media import _image_shape

    display_name = safe_display_name(getattr(uploaded, "name", ""))
    extension = (
        f".{display_name.rsplit('.', 1)[-1].lower()}" if "." in display_name else ""
    )
    rule = TRANSACTION_ALLOWED_MEDIA.get(extension)
    if rule is None:
        raise ValidationError(
            {field: _(f"Files of type “{extension or 'unknown'}” are not allowed.")}
        )
    uploaded.seek(0)
    data = uploaded.read()
    size = len(data)
    if size == 0:
        raise ValidationError({field: _("That file is empty.")})
    if size > rule.max_bytes:
        limit = rule.max_bytes // _MB
        raise ValidationError(
            {field: _(f"{extension} files must be {limit} MB or smaller.")}
        )
    detected = detect_media_type(data[:4096])
    if detected not in rule.accepted_types:
        raise ValidationError(
            {
                field: _(
                    f"That file claims to be {extension} but its contents are "
                    f"{detected}. Upload the real file."
                )
            }
        )
    width = height = None
    if rule.is_image:
        width, height = _image_shape(data, field=field)
    return (
        InspectedUpload(
            display_name=display_name,
            extension=extension,
            media_type=rule.media_type,
            byte_size=size,
            checksum=checksum_of(data),
            width=width,
            height=height,
            is_image=rule.is_image,
        ),
        data,
    )


def allowed_matrix_payload() -> dict[str, Any]:
    return {
        "document": {
            "extensions": sorted(TRANSACTION_ALLOWED_MEDIA.keys()),
            "maxBytes": max(
                rule.max_bytes for rule in TRANSACTION_ALLOWED_MEDIA.values()
            ),
            "maxCount": MAX_TRANSACTION_DOCUMENTS,
            "maxBatch": MAX_UPLOAD_BATCH,
        }
    }


__all__ = [
    "ABANDONED_PENDING_DAYS",
    "MAX_TRANSACTION_DOCUMENTS",
    "MAX_UPLOAD_BATCH",
    "ORPHAN_GRACE_HOURS",
    "TRANSACTION_ALLOWED_MEDIA",
    "allowed_matrix_payload",
    "checksum_of",
    "inspect_transaction_upload",
    "safe_display_name",
    "storage_key",
]
