"""Hub-native PDF fill, signature appearance stamping, and PKCS#12 PAdES seal."""

from __future__ import annotations

import base64
import hashlib
import io
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from apps.contract.field_layout import (
    PREFILL_ROLE,
    SIGNER_ROLE,
    FieldType,
    normalize_field_layout,
)

logger = logging.getLogger(__name__)

RENDERER_VERSION = "hub-pdf-1.0.0"


@dataclass(frozen=True)
class SealResult:
    pdf_bytes: bytes
    cert_subject: str
    cert_fingerprint: str


def _page_size(reader: PdfReader, page_index: int) -> tuple[float, float]:
    page = reader.pages[page_index]
    box = page.mediabox
    return float(box.width), float(box.height)


def _top_left_to_pdf_y(*, y: float, h: float, page_height: float) -> float:
    """Convert Hub placer top-left Y into PDF bottom-left Y for the box bottom."""
    return page_height - y - h


def _draw_text_in_box(
    c: canvas.Canvas,
    *,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    page_height: float,
    font_size: float = 10,
) -> None:
    if not text:
        return
    pdf_y = _top_left_to_pdf_y(y=y, h=h, page_height=page_height)
    c.setFont("Helvetica", min(font_size, max(6.0, h * 0.55)))
    # Baseline near vertical center of the box.
    baseline = pdf_y + max(2.0, h * 0.28)
    c.drawString(x + 2, baseline, text[:200])


def _draw_image_in_box(
    c: canvas.Canvas,
    *,
    image_bytes: bytes,
    x: float,
    y: float,
    w: float,
    h: float,
    page_height: float,
) -> None:
    if not image_bytes:
        return
    pdf_y = _top_left_to_pdf_y(y=y, h=h, page_height=page_height)
    image = ImageReader(io.BytesIO(image_bytes))
    c.drawImage(
        image,
        x,
        pdf_y,
        width=w,
        height=h,
        preserveAspectRatio=True,
        mask="auto",
        anchor="c",
    )


def _overlay_for_page(
    *,
    page_width: float,
    page_height: float,
    draw,
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    draw(c)
    c.save()
    return buf.getvalue()


def _merge_overlays(source: bytes, overlays: dict[int, bytes]) -> bytes:
    reader = PdfReader(io.BytesIO(source))
    writer = PdfWriter()
    for index, page in enumerate(reader.pages):
        overlay_bytes = overlays.get(index)
        if overlay_bytes:
            overlay_page = PdfReader(io.BytesIO(overlay_bytes)).pages[0]
            page.merge_page(overlay_page)
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def fill_prefill_fields(
    source_pdf: bytes,
    *,
    layout: list[dict[str, Any]],
    values: dict[str, str],
) -> bytes:
    """Stamp Prefill field values onto a blank template PDF (Agent regions blank)."""
    fields = normalize_field_layout(layout)
    reader = PdfReader(io.BytesIO(source_pdf))
    by_page: dict[int, list[dict[str, Any]]] = {}
    for field in fields:
        if field["role"] != PREFILL_ROLE:
            continue
        by_page.setdefault(int(field["page"]) - 1, []).append(field)

    overlays: dict[int, bytes] = {}
    for page_index, page_fields in by_page.items():
        if page_index < 0 or page_index >= len(reader.pages):
            continue
        width, height = _page_size(reader, page_index)

        def draw(c: canvas.Canvas, items=page_fields, ph=height) -> None:
            for item in items:
                name = str(item["name"])
                value = str(values.get(name) or "")
                ftype = str(item["type"])
                if ftype == FieldType.CHECKBOX:
                    if value.lower() in {"1", "true", "yes", "on", "x"}:
                        _draw_text_in_box(
                            c,
                            text="X",
                            x=float(item["x"]),
                            y=float(item["y"]),
                            w=float(item["w"]),
                            h=float(item["h"]),
                            page_height=ph,
                            font_size=12,
                        )
                    continue
                if ftype in {
                    FieldType.TEXT,
                    FieldType.DATE,
                    FieldType.INITIALS,
                }:
                    _draw_text_in_box(
                        c,
                        text=value,
                        x=float(item["x"]),
                        y=float(item["y"]),
                        w=float(item["w"]),
                        h=float(item["h"]),
                        page_height=ph,
                    )

        overlays[page_index] = _overlay_for_page(
            page_width=width, page_height=height, draw=draw
        )

    if not overlays:
        return source_pdf
    return _merge_overlays(source_pdf, overlays)


def decode_data_url_image(raw: str) -> bytes:
    value = (raw or "").strip()
    if not value:
        return b""
    if "," in value and value.lower().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode(value, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError({"signature": ["Invalid signature image."]}) from exc


def stamp_signer_fields(
    review_pdf: bytes,
    *,
    layout: list[dict[str, Any]],
    role: str,
    signature_png: bytes,
    signed_date: str,
    initials_png: bytes = b"",
    text_values: dict[str, str] | None = None,
) -> bytes:
    """Apply one human signer role's appearance onto the review PDF."""
    fields = normalize_field_layout(layout)
    text_values = text_values or {}
    reader = PdfReader(io.BytesIO(review_pdf))
    by_page: dict[int, list[dict[str, Any]]] = {}
    for field in fields:
        if field["role"] != role:
            continue
        by_page.setdefault(int(field["page"]) - 1, []).append(field)

    overlays: dict[int, bytes] = {}
    for page_index, page_fields in by_page.items():
        if page_index < 0 or page_index >= len(reader.pages):
            continue
        width, height = _page_size(reader, page_index)

        def draw(c: canvas.Canvas, items=page_fields, ph=height) -> None:
            for item in items:
                ftype = str(item["type"])
                x, y, w, h = (
                    float(item["x"]),
                    float(item["y"]),
                    float(item["w"]),
                    float(item["h"]),
                )
                if ftype == FieldType.SIGNATURE:
                    _draw_image_in_box(
                        c,
                        image_bytes=signature_png,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        page_height=ph,
                    )
                elif ftype == FieldType.INITIALS:
                    if initials_png:
                        _draw_image_in_box(
                            c,
                            image_bytes=initials_png,
                            x=x,
                            y=y,
                            w=w,
                            h=h,
                            page_height=ph,
                        )
                    else:
                        _draw_text_in_box(
                            c,
                            text=str(text_values.get(str(item["name"])) or ""),
                            x=x,
                            y=y,
                            w=w,
                            h=h,
                            page_height=ph,
                        )
                elif ftype == FieldType.DATE:
                    _draw_text_in_box(
                        c,
                        text=signed_date,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        page_height=ph,
                    )
                elif ftype == FieldType.TEXT:
                    _draw_text_in_box(
                        c,
                        text=str(text_values.get(str(item["name"])) or ""),
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        page_height=ph,
                    )
                elif ftype == FieldType.CHECKBOX:
                    raw = str(text_values.get(str(item["name"])) or "")
                    if raw.lower() in {"1", "true", "yes", "on", "x"}:
                        _draw_text_in_box(
                            c,
                            text="X",
                            x=x,
                            y=y,
                            w=w,
                            h=h,
                            page_height=ph,
                            font_size=12,
                        )

        overlays[page_index] = _overlay_for_page(
            page_width=width, page_height=height, draw=draw
        )

    if not overlays:
        return review_pdf
    return _merge_overlays(review_pdf, overlays)


def stamp_agent_signatures(
    review_pdf: bytes,
    *,
    layout: list[dict[str, Any]],
    signature_png: bytes,
    signed_date: str,
    initials_png: bytes = b"",
    text_values: dict[str, str] | None = None,
) -> bytes:
    """Apply Agent signature / date / initials / text onto the review PDF."""
    return stamp_signer_fields(
        review_pdf,
        layout=layout,
        role=SIGNER_ROLE,
        signature_png=signature_png,
        signed_date=signed_date,
        initials_png=initials_png,
        text_values=text_values,
    )


def signing_cert_configured() -> bool:
    path = (getattr(settings, "CONTRACT_SIGNING_CERT_PATH", "") or "").strip()
    return bool(path)


def require_signing_cert_or_raise() -> None:
    """Production fails closed without a sealing cert; DEBUG may proceed unsigned."""
    if signing_cert_configured():
        return
    if getattr(settings, "DEBUG", False) and getattr(
        settings, "CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV", True
    ):
        return
    raise ValidationError(
        {
            "form": [
                "Electronic signing is unavailable: organization signing "
                "certificate is not configured."
            ]
        }
    )


def seal_pdf_with_org_cert(pdf_bytes: bytes) -> SealResult:
    """Apply a PAdES signature with the brokerage PKCS#12 when configured."""
    path = (getattr(settings, "CONTRACT_SIGNING_CERT_PATH", "") or "").strip()
    if not path:
        return SealResult(pdf_bytes=pdf_bytes, cert_subject="", cert_fingerprint="")

    passphrase = getattr(settings, "CONTRACT_SIGNING_CERT_PASSPHRASE", "") or ""
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
        from pyhanko.sign.fields import SigFieldSpec, append_signature_field
        from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
    except ImportError as exc:  # pragma: no cover
        raise ValidationError(
            {"form": ["PDF sealing library is unavailable."]}
        ) from exc

    try:
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=path,
            passphrase=passphrase.encode("utf-8") if passphrase else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("contract signing cert load failed")
        raise ValidationError(
            {"form": ["Could not load the organization signing certificate."]}
        ) from exc

    subject = ""
    fingerprint = ""
    if signer.signing_cert is not None:
        subject = str(signer.signing_cert.subject)
        fingerprint = hashlib.sha256(signer.signing_cert.dump()).hexdigest()

    input_buf = io.BytesIO(pdf_bytes)
    writer = IncrementalPdfFileWriter(input_buf)
    append_signature_field(writer, SigFieldSpec(sig_field_name="OnestOrgSeal"))
    meta = PdfSignatureMetadata(field_name="OnestOrgSeal")
    out = io.BytesIO()
    signers.sign_pdf(writer, meta, signer=signer, output=out)
    return SealResult(
        pdf_bytes=out.getvalue(),
        cert_subject=subject,
        cert_fingerprint=fingerprint,
    )


def signing_is_ready() -> bool:
    """Hub signing is available when org seal requirements are satisfied."""
    try:
        require_signing_cert_or_raise()
    except ValidationError:
        return False
    return True


def appearance_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
