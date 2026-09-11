"""Allowed policy file matrix and upload inspection."""

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

#: Consumer-facing policy documents (primarily sealed PDFs).
DOCUMENT_ALLOWED_MEDIA: dict[str, MediaRule] = {
    ".pdf": ALLOWED_MEDIA[".pdf"],
    ".docx": ALLOWED_MEDIA[".docx"],
    ".txt": ALLOWED_MEDIA[".txt"],
}

#: Editable sources retained for administrators.
SOURCE_ALLOWED_MEDIA: dict[str, MediaRule] = {
    **DOCUMENT_ALLOWED_MEDIA,
    ".zip": MediaRule(
        ".zip",
        "application/zip",
        frozenset({"application/zip"}),
        50 * _MB,
    ),
    ".doc": MediaRule(
        ".doc",
        "application/msword",
        frozenset({"application/msword", "application/octet-stream"}),
        20 * _MB,
    ),
}

MAX_DOCUMENT_FILES = 10
MAX_SOURCE_FILES = 5


def storage_key(display_name: str, *, prefix: str = "compliance") -> str:
    extension = safe_display_name(display_name).rsplit(".", 1)[-1].lower()
    matrix = {**DOCUMENT_ALLOWED_MEDIA, **SOURCE_ALLOWED_MEDIA}
    ext = f".{extension}" if extension and f".{extension}" in matrix else ""
    if ext:
        import uuid

        return f"{prefix}/{uuid.uuid4().hex}{ext}"
    return _announcement_storage_key(display_name, prefix=prefix)


def inspect_policy_upload(
    uploaded,
    *,
    field: str = "file",
    role: str = "document",
):
    from django.core.exceptions import ValidationError
    from django.utils.translation import gettext_lazy as _

    from apps.compliance.models import PolicyFile

    matrix = (
        SOURCE_ALLOWED_MEDIA
        if role == PolicyFile.Role.SOURCE
        else DOCUMENT_ALLOWED_MEDIA
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
