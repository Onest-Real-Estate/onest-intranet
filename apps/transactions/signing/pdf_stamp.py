"""Appearance stamping for transaction signature packages.

The drawing and page-merge mechanics match ``apps.contract.pdf_signing`` —
same top-left origin, same box-fitting rules — but the field selector is the
signer's public id rather than the contract role vocabulary, so the contract
normalizer cannot be reused. The PAdES seal is shared: this module imports
``seal_pdf_with_org_cert`` rather than growing a second certificate path.
"""

from __future__ import annotations

import io
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from apps.contract.pdf_signing import (
    appearance_checksum,
    decode_data_url_image,
    require_signing_cert_or_raise,
    seal_pdf_with_org_cert,
    signing_is_ready,
)
from apps.transactions.signing.field_layout import fields_for_signer
from apps.transactions.taxonomy import SignatureFieldType

RENDERER_VERSION = "hub-txn-signed-1.0.0"

MAX_STAMPED_TEXT = 200


def page_count_of(pdf_bytes: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def _page_size(reader: PdfReader, page_index: int) -> tuple[float, float]:
    box = reader.pages[page_index].mediabox
    return float(box.width), float(box.height)


def _top_left_to_pdf_y(*, y: float, h: float, page_height: float) -> float:
    """Convert a top-left placer Y into the PDF bottom-left Y of the box."""
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
    del w
    pdf_y = _top_left_to_pdf_y(y=y, h=h, page_height=page_height)
    c.setFont("Helvetica", min(font_size, max(6.0, h * 0.55)))
    baseline = pdf_y + max(2.0, h * 0.28)
    c.drawString(x + 2, baseline, text[:MAX_STAMPED_TEXT])


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
    c.drawImage(
        ImageReader(io.BytesIO(image_bytes)),
        x,
        pdf_y,
        width=w,
        height=h,
        preserveAspectRatio=True,
        mask="auto",
        anchor="c",
    )


def _overlay_for_page(*, page_width: float, page_height: float, draw) -> bytes:
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
            page.merge_page(PdfReader(io.BytesIO(overlay_bytes)).pages[0])
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def stamp_signer_package_fields(
    source_pdf: bytes,
    *,
    fields: list[dict[str, Any]],
    signer_key: str,
    signature_png: bytes,
    signed_date: str,
    initials_png: bytes = b"",
    text_values: dict[str, str] | None = None,
) -> bytes:
    """Apply one signer's appearance to one document's pages.

    ``fields`` may hold the whole package layout; only rows whose ``signerKey``
    matches are drawn. Fields pointing past the last page are skipped so a
    stale layout cannot fail a finalize run.
    """
    mine = fields_for_signer(fields, signer_key=signer_key)
    if not mine:
        return source_pdf

    values = dict(text_values or {})
    reader = PdfReader(io.BytesIO(source_pdf))
    by_page: dict[int, list[dict[str, Any]]] = {}
    for field in mine:
        by_page.setdefault(int(field["page"]) - 1, []).append(field)

    overlays: dict[int, bytes] = {}
    for page_index, page_fields in by_page.items():
        if page_index < 0 or page_index >= len(reader.pages):
            continue
        width, height = _page_size(reader, page_index)

        def draw(c: canvas.Canvas, items=page_fields, ph=height) -> None:
            for item in items:
                ftype = str(item["type"])
                x = float(item["x"])
                y = float(item["y"])
                w = float(item["w"])
                h = float(item["h"])
                if ftype == SignatureFieldType.SIGNATURE:
                    _draw_image_in_box(
                        c,
                        image_bytes=signature_png,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        page_height=ph,
                    )
                elif ftype == SignatureFieldType.INITIALS:
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
                            text=str(values.get(str(item["name"])) or ""),
                            x=x,
                            y=y,
                            w=w,
                            h=h,
                            page_height=ph,
                        )
                elif ftype == SignatureFieldType.DATE:
                    _draw_text_in_box(
                        c,
                        text=str(values.get(str(item["name"])) or signed_date),
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        page_height=ph,
                    )
                elif ftype == SignatureFieldType.TEXT:
                    _draw_text_in_box(
                        c,
                        text=str(values.get(str(item["name"])) or ""),
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        page_height=ph,
                    )

        overlays[page_index] = _overlay_for_page(
            page_width=width, page_height=height, draw=draw
        )

    if not overlays:
        return source_pdf
    return _merge_overlays(source_pdf, overlays)


def append_pages(base_pdf: bytes, *, extra_pdf: bytes) -> bytes:
    """Concatenate certificate page(s) after the stamped documents."""
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(base_pdf)).pages:
        writer.add_page(page)
    for page in PdfReader(io.BytesIO(extra_pdf)).pages:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


__all__ = [
    "RENDERER_VERSION",
    "append_pages",
    "appearance_checksum",
    "decode_data_url_image",
    "page_count_of",
    "require_signing_cert_or_raise",
    "seal_pdf_with_org_cert",
    "signing_is_ready",
    "stamp_signer_package_fields",
]
