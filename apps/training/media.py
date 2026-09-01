"""Allowed training file matrix and upload inspection."""

from __future__ import annotations

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

TRAINING_ALLOWED_MEDIA: dict[str, MediaRule] = {
    **ALLOWED_MEDIA,
    ".mp4": MediaRule(
        ".mp4",
        "video/mp4",
        frozenset({"video/mp4", "application/octet-stream"}),
        200 * _MB,
    ),
    ".webm": MediaRule(
        ".webm",
        "video/webm",
        frozenset({"video/webm", "application/octet-stream"}),
        200 * _MB,
    ),
}

MAX_ATTACHMENTS = 10


def storage_key(display_name: str, *, prefix: str = "training") -> str:
    extension = safe_display_name(display_name).rsplit(".", 1)[-1].lower()
    ext = (
        f".{extension}"
        if extension and f".{extension}" in TRAINING_ALLOWED_MEDIA
        else ""
    )
    if ext:
        import uuid

        return f"{prefix}/{uuid.uuid4().hex}{ext}"
    return _announcement_storage_key(display_name, prefix=prefix)


def inspect_training_upload(uploaded, *, field: str = "file", primary: bool = False):
    display_name = safe_display_name(getattr(uploaded, "name", ""))
    extension = (
        f".{display_name.rsplit('.', 1)[-1].lower()}" if "." in display_name else ""
    )
    rule = TRAINING_ALLOWED_MEDIA.get(extension)
    if rule is None:
        from django.core.exceptions import ValidationError
        from django.utils.translation import gettext_lazy as _

        raise ValidationError(
            {field: _(f"Files of type “{extension or 'unknown'}” are not allowed.")}
        )
    uploaded.seek(0)
    data = uploaded.read()
    size = len(data)
    if size == 0:
        from django.core.exceptions import ValidationError
        from django.utils.translation import gettext_lazy as _

        raise ValidationError({field: _("That file is empty.")})
    if size > rule.max_bytes:
        from django.core.exceptions import ValidationError
        from django.utils.translation import gettext_lazy as _

        limit = rule.max_bytes // _MB
        raise ValidationError(
            {field: _(f"{extension} files must be {limit} MB or smaller.")}
        )
    detected = detect_media_type(data[:4096])
    if detected not in rule.accepted_types:
        from django.core.exceptions import ValidationError
        from django.utils.translation import gettext_lazy as _

        raise ValidationError(
            {
                field: _(
                    f"That file claims to be {extension} but its contents are "
                    f"{detected}. Upload the real file."
                )
            }
        )
    return (
        InspectedUpload(
            display_name=display_name,
            extension=extension,
            media_type=rule.media_type,
            byte_size=size,
            checksum=checksum_of(data),
            width=None,
            height=None,
            is_image=rule.is_image,
        ),
        data,
    )
