"""Allowed marketing file matrix and upload inspection."""

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

#: Source files may include design packages larger than consumer exports.
SOURCE_ALLOWED_MEDIA: dict[str, MediaRule] = {
    **ALLOWED_MEDIA,
    ".zip": MediaRule(
        ".zip",
        "application/zip",
        frozenset({"application/zip"}),
        50 * _MB,
    ),
    ".ai": MediaRule(
        ".ai",
        "application/postscript",
        frozenset(
            {"application/postscript", "application/pdf", "application/octet-stream"}
        ),
        50 * _MB,
    ),
    ".psd": MediaRule(
        ".psd",
        "image/vnd.adobe.photoshop",
        frozenset({"image/vnd.adobe.photoshop", "application/octet-stream"}),
        50 * _MB,
    ),
    ".svg": MediaRule(
        ".svg",
        "image/svg+xml",
        frozenset({"image/svg+xml", "text/plain", "text/xml", "application/xml"}),
        2 * _MB,
        True,
    ),
}

EXPORT_ALLOWED_MEDIA: dict[str, MediaRule] = dict(ALLOWED_MEDIA)

MAX_EXPORT_FILES = 10
MAX_SOURCE_FILES = 5


def storage_key(display_name: str, *, prefix: str = "marketing") -> str:
    extension = safe_display_name(display_name).rsplit(".", 1)[-1].lower()
    matrix = {**EXPORT_ALLOWED_MEDIA, **SOURCE_ALLOWED_MEDIA}
    ext = f".{extension}" if extension and f".{extension}" in matrix else ""
    if ext:
        import uuid

        return f"{prefix}/{uuid.uuid4().hex}{ext}"
    return _announcement_storage_key(display_name, prefix=prefix)


def inspect_marketing_upload(
    uploaded,
    *,
    field: str = "file",
    role: str = "export",
):
    from django.core.exceptions import ValidationError
    from django.utils.translation import gettext_lazy as _

    from apps.marketing.models import MarketingFile

    matrix = (
        SOURCE_ALLOWED_MEDIA
        if role == MarketingFile.Role.SOURCE
        else EXPORT_ALLOWED_MEDIA
    )
    display_name = safe_display_name(getattr(uploaded, "name", ""))
    extension = (
        f".{display_name.rsplit('.', 1)[-1].lower()}" if "." in display_name else ""
    )
    rule = matrix.get(extension)
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
    # SVG is XML/text; accept text/plain and xml sniff results already in rule.
    if extension == ".svg" and detected in {
        "text/plain",
        "application/octet-stream",
    }:
        detected = "image/svg+xml"
    if detected not in rule.accepted_types:
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
