"""The allowed-file matrix, and everything that decides whether bytes are safe.

Nothing here trusts the client. Not the filename, not the ``Content-Type``
header, not the extension. Each upload is checked three ways and all three must
agree:

1. **Extension** must appear in :data:`ALLOWED_MEDIA`.
2. **Detected type** — sniffed from the leading bytes — must be one the
   extension is allowed to carry. A ``.png`` whose bytes are a PDF, a script,
   or an executable is a disguised upload and is refused here.
3. **Shape** — byte size for everything, plus pixel dimensions and total pixel
   count for images.

The pixel-count check happens *before* the image is decoded. ``Image.open``
reads only the header, so a decompression bomb — a few kilobytes of PNG that
expands to gigabytes of bitmap — is caught while it is still a few kilobytes.
Decoding first and asking questions afterwards is how that attack works.

Detection is done with a local signature table rather than ``libmagic`` so the
check has no system dependency to be missing in one environment and present in
another. The table only has to cover the types this matrix allows.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#: Bytes read from the front of a file for type detection.
SNIFF_BYTES = 4096


@dataclass(frozen=True)
class MediaRule:
    """One row of the allowed-file matrix."""

    extension: str
    #: Canonical type stored on the row and echoed to clients.
    media_type: str
    #: Types the sniffer may legitimately report for this extension.
    accepted_types: frozenset[str]
    max_bytes: int
    is_image: bool = False


_MB = 1024 * 1024

#: The allowed file matrix. Anything not listed here cannot be uploaded.
ALLOWED_MEDIA: dict[str, MediaRule] = {
    rule.extension: rule
    for rule in (
        # --- Images (hero and inline attachments) --- #
        MediaRule(".png", "image/png", frozenset({"image/png"}), 8 * _MB, True),
        MediaRule(".jpg", "image/jpeg", frozenset({"image/jpeg"}), 8 * _MB, True),
        MediaRule(".jpeg", "image/jpeg", frozenset({"image/jpeg"}), 8 * _MB, True),
        MediaRule(".webp", "image/webp", frozenset({"image/webp"}), 8 * _MB, True),
        # --- Documents --- #
        MediaRule(".pdf", "application/pdf", frozenset({"application/pdf"}), 20 * _MB),
        MediaRule(
            ".docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            # Office Open XML is a zip container; the sniffer sees the zip.
            frozenset({"application/zip"}),
            20 * _MB,
        ),
        MediaRule(
            ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            frozenset({"application/zip"}),
            20 * _MB,
        ),
        MediaRule(".txt", "text/plain", frozenset({"text/plain"}), 2 * _MB),
        MediaRule(".csv", "text/csv", frozenset({"text/plain"}), 5 * _MB),
    )
}

#: Extensions a hero image may use. Documents can never be the hero.
HERO_EXTENSIONS: frozenset[str] = frozenset(
    extension for extension, rule in ALLOWED_MEDIA.items() if rule.is_image
)

#: Most attachments one announcement may carry, hero excluded.
MAX_ATTACHMENTS = 10

#: Image guards. ``MAX_IMAGE_PIXELS`` is the decompression-bomb ceiling and is
#: checked against the header before any decode.
MAX_IMAGE_WIDTH = 8000
MAX_IMAGE_HEIGHT = 8000
MAX_IMAGE_PIXELS = 40_000_000
MIN_HERO_WIDTH = 600

#: Responsive variants generated asynchronously for images. Width in pixels;
#: height follows the source aspect ratio.
VARIANT_WIDTHS: dict[str, int] = {"thumb": 320, "card": 768, "hero": 1600}


# --------------------------------------------------------------------------- #
# Type detection
# --------------------------------------------------------------------------- #

#: ``(offset, signature, media type)``. Ordered: the first match wins, so more
#: specific signatures come before the containers they sit inside.
_SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"%PDF-", "application/pdf"),
    (0, b"PK\x03\x04", "application/zip"),
    (0, b"PK\x05\x06", "application/zip"),
    (0, b"PK\x07\x08", "application/zip"),
    # Executables and scripts are listed so the error can say what was found
    # rather than "unknown", which reads like a bug to whoever hit it.
    (0, b"MZ", "application/x-dosexec"),
    (0, b"\x7fELF", "application/x-executable"),
    (0, b"#!", "text/x-script"),
)


def detect_media_type(head: bytes) -> str:
    """Best-effort type from the leading bytes. Never raises."""
    for offset, signature, media_type in _SIGNATURES:
        if head[offset : offset + len(signature)] == signature:
            return media_type
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # Everything left is plain text only if it decodes as UTF-8 and holds no
    # NUL byte — the cheap discriminator between text and unrecognized binary.
    if b"\x00" in head:
        return "application/octet-stream"
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/plain"


# --------------------------------------------------------------------------- #
# Storage keys
# --------------------------------------------------------------------------- #


def safe_display_name(raw: str) -> str:
    """The name a reader sees. Never a path, never used to build one."""
    name = Path(str(raw or "")).name.replace("\x00", "").strip()
    # Leading dots would make the display name look like a hidden file; a bare
    # extension is not a name anyone chose.
    name = name.lstrip(".") or "file"
    return name[:180]


def storage_key(display_name: str, *, prefix: str = "announcements") -> str:
    """A collision-resistant key that borrows nothing from the upload.

    The submitted filename never reaches the path. Two people uploading
    ``Q3.pdf`` in the same second get different keys, and neither can steer the
    write with ``../`` or an absolute path, because only the extension — and
    only after it has been matched against the allowed matrix — survives.
    """
    extension = Path(safe_display_name(display_name)).suffix.lower()
    if extension not in ALLOWED_MEDIA:
        extension = ""
    return f"{prefix}/{uuid.uuid4().hex}{extension}"


def variant_key(original_key: str, variant: str) -> str:
    """Derivative key beside the original, so one prefix holds one upload."""
    path = Path(original_key)
    return str(path.parent / f"{path.stem}__{variant}{path.suffix}")


def checksum_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class InspectedUpload:
    """What the server decided about an upload, after reading it itself."""

    display_name: str
    extension: str
    media_type: str
    byte_size: int
    checksum: str
    width: int | None
    height: int | None
    is_image: bool


def _image_shape(data: bytes, *, field: str) -> tuple[int, int]:
    """Dimensions from the header, with the bomb ceiling applied first."""
    import io

    from PIL import Image, UnidentifiedImageError

    try:
        # ``open`` parses the header only; ``size`` is available without a
        # decode, which is the whole point of checking here.
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ValidationError(
                    {
                        field: _(
                            "That image decodes to too many pixels to process safely."
                        )
                    }
                )
            if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
                raise ValidationError(
                    {
                        field: _(
                            f"Images must be at most {MAX_IMAGE_WIDTH}×"
                            f"{MAX_IMAGE_HEIGHT} pixels."
                        )
                    }
                )
            # Only now is decoding safe.
            image.verify()
            return width, height
    except ValidationError:
        raise
    except UnidentifiedImageError as exc:
        raise ValidationError({field: _("That file is not a readable image.")}) from exc
    except Exception as exc:  # pragma: no cover - Pillow raises many types
        raise ValidationError({field: _("That image could not be read.")}) from exc


def inspect_upload(uploaded, *, field: str = "file", hero: bool = False):
    """Read the upload and decide whether it may be stored. Raises or returns.

    Returns the inspection **and** the bytes, because every caller needs both
    and reading a stream twice is how a file gets stored without having been
    the one that was checked.
    """
    display_name = safe_display_name(getattr(uploaded, "name", ""))
    extension = Path(display_name).suffix.lower()

    rule = ALLOWED_MEDIA.get(extension)
    if rule is None:
        raise ValidationError(
            {field: _(f"Files of type “{extension or 'unknown'}” are not allowed.")}
        )
    if hero and not rule.is_image:
        raise ValidationError({field: _("The hero must be an image.")})

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

    detected = detect_media_type(data[:SNIFF_BYTES])
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
        if hero and width < MIN_HERO_WIDTH:
            raise ValidationError(
                {
                    field: _(
                        f"A hero image must be at least {MIN_HERO_WIDTH} pixels wide."
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
            width=width,
            height=height,
            is_image=rule.is_image,
        ),
        data,
    )


def allowed_matrix_payload() -> dict:
    """The matrix, for the upload control and the documentation page."""
    return {
        "hero": {
            "extensions": sorted(HERO_EXTENSIONS),
            "maxBytes": max(ALLOWED_MEDIA[ext].max_bytes for ext in HERO_EXTENSIONS),
            "minWidth": MIN_HERO_WIDTH,
        },
        "attachment": {
            "extensions": sorted(ALLOWED_MEDIA),
            "maxBytes": max(rule.max_bytes for rule in ALLOWED_MEDIA.values()),
            "maxCount": MAX_ATTACHMENTS,
        },
    }
