"""Mistral Document AI OCR for Hub field-suggestion packages."""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import pymupdf
from django.conf import settings
from django.core.exceptions import ValidationError
from mistralai.client import Mistral
from mistralai.client.errors import HTTPValidationError, NoResponseError, SDKError
from mistralai.client.models.ocrresponse import OCRResponse
from mistralai.extra import response_format_from_pydantic_model
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter

from apps.contract.field_layout import (
    PREFILL_ROLE,
    SIGNER_ROLE,
    FieldType,
    new_field_id,
    normalize_field_layout,
)

logger = logging.getLogger(__name__)

DEFAULT_OCR_MODEL = "mistral-ocr-latest"
DEFAULT_MAX_PAGES = 8

# Underscore / checkbox marks that usually mean a fillable blank on ICA PDFs.
_BLANK_RE = re.compile(r"_{3,}|\.{4,}|…{2,}")
_CHECKBOX_RE = re.compile(r"(?:\[\s*\]|☐|□|◻)")
_TOKEN_RE = re.compile(r"[a-z0-9]+")

_MIN_BOX = {
    FieldType.TEXT: (80.0, 14.0),
    FieldType.DATE: (70.0, 14.0),
    FieldType.CHECKBOX: (12.0, 12.0),
    FieldType.SIGNATURE: (140.0, 28.0),
    FieldType.INITIALS: (40.0, 28.0),
}

DOCUMENT_ANNOTATION_PROMPT = (
    "You help place DocuSign-style form fields on an agent ICA PDF. "
    "Return only the fields that still need placement — skip values already "
    "printed in the PDF. Fill the schema with name, type, role, page, and "
    "anchor. type is one of text, signature, date, initials, checkbox. "
    "role is Prefill (brokerage-filled commercial text/date/checkbox) or "
    "Agent (signer). Signature and initials MUST use role Agent. "
    "page is the 1-based page number. "
    "anchor is nearby label text from the PDF that identifies the blank or "
    "signature line (for example 'Contractor', 'Beginning on', 'Signature'). "
    "Do not invent coordinates; geometry comes from OCR blocks."
)


class SuggestedField(BaseModel):
    """Semantic field label only — geometry is taken from OCR blocks."""

    name: str
    type: FieldType
    role: str = Field(description=f"{PREFILL_ROLE} or {SIGNER_ROLE}")
    page: int = Field(ge=1, description="1-based PDF page number")
    anchor: str = Field(
        default="",
        description="Nearby label text that identifies the blank or signature line",
    )


class SuggestedFieldLayout(BaseModel):
    fields: list[SuggestedField]


RegionKind = Literal["signature", "blank", "checkbox"]


@dataclass(frozen=True, slots=True)
class OcrRegion:
    page: int
    kind: RegionKind
    x: float
    y: float
    w: float
    h: float
    content: str
    hint: str


def ocr_configured() -> bool:
    return bool((getattr(settings, "MISTRAL_API_KEY", "") or "").strip())


def _ocr_http_message(status: int) -> str:
    if status in {401, 403}:
        return "Document OCR rejected the API key."
    if status == 404:
        return (
            "Document OCR model was not found. Set MISTRAL_OCR_MODEL to a "
            "current Mistral OCR model."
        )
    if status == 429:
        return "Document OCR is rate-limited. Try again in a moment."
    return "Document OCR request failed. Try again later."


def _status_from_exc(exc: BaseException) -> int | None:
    raw = getattr(exc, "raw_response", None)
    if raw is not None:
        code = getattr(raw, "status_code", None)
        if isinstance(code, int):
            return code
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _slice_pdf(pdf_bytes: bytes, *, max_pages: int) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValidationError({"form": ["Document OCR requires a PDF with pages."]})
    keep = min(len(reader.pages), max(1, max_pages))
    if keep == len(reader.pages):
        return pdf_bytes
    writer = PdfWriter()
    for page in reader.pages[:keep]:
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def ocr_document(
    pdf_bytes: bytes, *, max_pages: int = DEFAULT_MAX_PAGES
) -> OCRResponse:
    """Run Mistral OCR + document annotation on a private PDF (base64, not a URL)."""
    if not ocr_configured():
        raise ValidationError(
            {"form": ["Document OCR is not configured. Set MISTRAL_API_KEY."]}
        )
    if not pdf_bytes:
        raise ValidationError({"form": ["Document OCR requires a PDF."]})

    payload = _slice_pdf(pdf_bytes, max_pages=max_pages)
    b64 = base64.b64encode(payload).decode("ascii")
    model = (
        getattr(settings, "MISTRAL_OCR_MODEL", "") or ""
    ).strip() or DEFAULT_OCR_MODEL
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    try:
        return client.ocr.process(
            model=model,
            document={
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{b64}",
            },
            include_blocks=True,
            document_annotation_format=response_format_from_pydantic_model(
                SuggestedFieldLayout
            ),
            document_annotation_prompt=DOCUMENT_ANNOTATION_PROMPT,
            timeout_ms=60_000,
        )
    except (SDKError, HTTPValidationError) as exc:
        status = _status_from_exc(exc)
        logger.warning("document OCR failed status=%s", status)
        raise ValidationError({"form": [_ocr_http_message(status or 0)]}) from exc
    except (httpx.TimeoutException, httpx.RequestError, NoResponseError) as exc:
        logger.warning("document OCR request failed type=%s", type(exc).__name__)
        raise ValidationError(
            {"form": ["Document OCR request failed. Try again later."]}
        ) from exc


def _decode_jsonish(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return json_loads_lenient(text)
    except ValueError:
        return None


def json_loads_lenient(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
        if not match:
            raise ValueError("no JSON object") from None
        return json.loads(match.group(0))


def _field_name(name: str, *, field_type: str, role: str) -> str:
    """Convert an OCR display label into the stable field-name identifier."""
    parts = re.findall(r"[A-Za-z0-9]+", name)
    normalized = "".join(part[:1].upper() + part[1:] for part in parts)
    if not normalized or not normalized[0].isalpha():
        normalized = f"{role}{field_type[:1].upper()}{field_type[1:]}"
    return normalized[:80]


def _annotation_fields(response: Any) -> list[dict[str, Any]]:
    raw = _decode_jsonish(getattr(response, "document_annotation", None))
    if isinstance(raw, dict):
        raw = raw.get("fields") or raw.get("suggestions") or []
    if not isinstance(raw, list):
        return []
    fields: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ftype = str(item.get("type") or "").strip()
        if ftype not in {member.value for member in FieldType}:
            continue
        role = str(item.get("role") or "").strip()
        if role not in {PREFILL_ROLE, SIGNER_ROLE}:
            role = (
                SIGNER_ROLE
                if ftype in {FieldType.SIGNATURE, FieldType.DATE, FieldType.INITIALS}
                else PREFILL_ROLE
            )
        if role == PREFILL_ROLE and ftype in {
            FieldType.SIGNATURE,
            FieldType.INITIALS,
        }:
            role = SIGNER_ROLE
        try:
            page = int(item.get("page") or 1)
        except (TypeError, ValueError):
            page = 1
        name = _field_name(
            str(item.get("name") or ""),
            field_type=ftype,
            role=role,
        )
        fields.append(
            {
                "name": name,
                "type": ftype,
                "role": role,
                "page": max(1, page),
                "anchor": str(item.get("anchor") or "").strip(),
            }
        )
    return fields


def _block_type(block: Any) -> str:
    value = getattr(block, "type", None)
    if value is None and isinstance(block, dict):
        value = block.get("type")
    return str(value or "").strip().lower()


def _block_attr(block: Any, name: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


def _pixels_to_pdf(
    *,
    left: float,
    top: float,
    right: float,
    bottom: float,
    ocr_width: float,
    ocr_height: float,
    pdf_width: float,
    pdf_height: float,
) -> tuple[float, float, float, float]:
    if ocr_width <= 0 or ocr_height <= 0:
        return 0.0, 0.0, 0.0, 0.0
    sx = pdf_width / ocr_width
    sy = pdf_height / ocr_height
    x = left * sx
    y = top * sy
    w = max(0.0, (right - left) * sx)
    h = max(0.0, (bottom - top) * sy)
    return x, y, w, h


def _blank_box_in_block(
    *,
    content: str,
    left: float,
    top: float,
    right: float,
    bottom: float,
    ocr_width: float,
    ocr_height: float,
    pdf_width: float,
    pdf_height: float,
) -> tuple[float, float, float, float] | None:
    match = _BLANK_RE.search(content)
    if not match or not content:
        return None
    # Approximate the blank's horizontal span from character offsets inside the
    # block. OCR only gives block boxes, not glyph positions.
    start = match.start() / len(content)
    end = match.end() / len(content)
    span_left = left + (right - left) * start
    span_right = left + (right - left) * max(start + 0.05, end)
    return _pixels_to_pdf(
        left=span_left,
        top=top,
        right=span_right,
        bottom=bottom,
        ocr_width=ocr_width,
        ocr_height=ocr_height,
        pdf_width=pdf_width,
        pdf_height=pdf_height,
    )


def _checkbox_box_in_block(
    *,
    content: str,
    left: float,
    top: float,
    right: float,
    bottom: float,
    ocr_width: float,
    ocr_height: float,
    pdf_width: float,
    pdf_height: float,
) -> tuple[float, float, float, float] | None:
    match = _CHECKBOX_RE.search(content)
    if not match or not content:
        return None
    start = match.start() / len(content)
    # Square checkbox sized from block height.
    box_left = left + (right - left) * start
    size = max(8.0, (bottom - top) * 0.9)
    return _pixels_to_pdf(
        left=box_left,
        top=top,
        right=box_left + size,
        bottom=top + size,
        ocr_width=ocr_width,
        ocr_height=ocr_height,
        pdf_width=pdf_width,
        pdf_height=pdf_height,
    )


def extract_ocr_regions(
    response: Any,
    *,
    page_sizes: dict[int, tuple[float, float]],
) -> list[OcrRegion]:
    """Collect signature / blank / checkbox regions from measured OCR blocks."""
    pages = getattr(response, "pages", None) or []
    regions: list[OcrRegion] = []
    for page in pages:
        try:
            page_index = int(_block_attr(page, "index", 0))
        except (TypeError, ValueError):
            continue
        page_number = page_index + 1
        if page_number not in page_sizes:
            continue
        pdf_width, pdf_height = page_sizes[page_number]
        dims = _block_attr(page, "dimensions", None)
        ocr_width = float(_block_attr(dims, "width", 0) or 0)
        ocr_height = float(_block_attr(dims, "height", 0) or 0)
        if ocr_width <= 0 or ocr_height <= 0:
            ocr_width, ocr_height = pdf_width, pdf_height

        blocks = _block_attr(page, "blocks", None) or []
        # Hint = text of the previous non-blank block (often the label).
        prior_hint = ""
        for block in blocks:
            btype = _block_type(block)
            try:
                left = float(_block_attr(block, "top_left_x"))
                top = float(_block_attr(block, "top_left_y"))
                right = float(_block_attr(block, "bottom_right_x"))
                bottom = float(_block_attr(block, "bottom_right_y"))
            except (TypeError, ValueError):
                continue
            content = str(_block_attr(block, "content", "") or "")

            if btype == "signature":
                x, y, w, h = _pixels_to_pdf(
                    left=left,
                    top=top,
                    right=right,
                    bottom=bottom,
                    ocr_width=ocr_width,
                    ocr_height=ocr_height,
                    pdf_width=pdf_width,
                    pdf_height=pdf_height,
                )
                regions.append(
                    OcrRegion(
                        page=page_number,
                        kind="signature",
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        content=content,
                        hint=prior_hint or content,
                    )
                )
                continue

            if btype not in {
                "text",
                "title",
                "list",
                "aside_text",
                "caption",
                "header",
                "footer",
            }:
                if content.strip():
                    prior_hint = content.strip()
                continue

            checkbox = _checkbox_box_in_block(
                content=content,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                ocr_width=ocr_width,
                ocr_height=ocr_height,
                pdf_width=pdf_width,
                pdf_height=pdf_height,
            )
            if checkbox is not None:
                x, y, w, h = checkbox
                regions.append(
                    OcrRegion(
                        page=page_number,
                        kind="checkbox",
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        content=content,
                        hint=prior_hint or content,
                    )
                )

            blank = _blank_box_in_block(
                content=content,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                ocr_width=ocr_width,
                ocr_height=ocr_height,
                pdf_width=pdf_width,
                pdf_height=pdf_height,
            )
            if blank is not None:
                x, y, w, h = blank
                regions.append(
                    OcrRegion(
                        page=page_number,
                        kind="blank",
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        content=content,
                        hint=prior_hint or content,
                    )
                )
            if content.strip() and blank is None and checkbox is None:
                prior_hint = content.strip()
            elif content.strip() and (blank is not None or checkbox is not None):
                # Keep the surrounding sentence as the hint for matching.
                prior_hint = content.strip()
    return regions


def extract_native_pdf_regions(pdf_bytes: bytes) -> list[OcrRegion]:
    """Find writable blanks from the source PDF's actual text and line geometry.

    Mistral block boxes are deliberately paragraph-level.  On a born-digital
    PDF, underline glyphs and drawn form rules are a substantially more exact
    source of placement geometry.  PyMuPDF reports these in the same top-left
    page coordinate system used by the Hub field placer.
    """
    if not pdf_bytes:
        return []

    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except (RuntimeError, ValueError):
        return []

    regions: list[OcrRegion] = []
    try:
        for page_number in range(1, document.page_count + 1):
            page = document.load_page(page_number - 1)
            raw = page.get_text("rawdict")
            lines: list[tuple[str, list[dict[str, Any]]]] = []
            for block in raw.get("blocks", []):
                for line in block.get("lines", []):
                    chars = [
                        char
                        for span in line.get("spans", [])
                        for char in span.get("chars", [])
                        if isinstance(char, dict) and isinstance(char.get("c"), str)
                    ]
                    if chars:
                        lines.append(("".join(char["c"] for char in chars), chars))

            for content, chars in lines:
                run_start: int | None = None
                for index, char in enumerate([item["c"] for item in chars] + [""]):
                    if char in {"_", ".", "…"}:
                        if run_start is None:
                            run_start = index
                        continue
                    if run_start is None or index - run_start < 3:
                        run_start = None
                        continue
                    run = chars[run_start:index]
                    boxes: list[tuple[float, float, float, float]] = []
                    for item in run:
                        box = item.get("bbox")
                        if not isinstance(box, tuple | list) or len(box) != 4:
                            boxes = []
                            break
                        x0, y0, x1, y1 = (float(value) for value in box)
                        boxes.append((x0, y0, x1, y1))
                    if not boxes:
                        run_start = None
                        continue
                    x0 = min(float(box[0]) for box in boxes)
                    y0 = min(float(box[1]) for box in boxes)
                    x1 = max(float(box[2]) for box in boxes)
                    y1 = max(float(box[3]) for box in boxes)
                    regions.append(
                        OcrRegion(
                            page=page_number,
                            kind="blank",
                            x=x0,
                            y=y0,
                            w=x1 - x0,
                            h=y1 - y0,
                            content=content,
                            hint=content,
                        )
                    )
                    run_start = None

            # Some forms use a drawn horizontal rule rather than underscores.
            # Associate each rule with the closest text line to retain a useful
            # label for semantic matching.
            for drawing in page.get_drawings():
                for item in drawing.get("items", []):
                    if len(item) != 3 or item[0] != "l":
                        continue
                    start, end = item[1], item[2]
                    if abs(start.y - end.y) > 1 or abs(start.x - end.x) < 24:
                        continue
                    x = min(float(start.x), float(end.x))
                    y = float(start.y)
                    nearby = min(
                        lines,
                        key=lambda line: min(
                            abs(float(char["bbox"][1]) - y) for char in line[1]
                        ),
                        default=("", []),
                    )[0]
                    regions.append(
                        OcrRegion(
                            page=page_number,
                            kind="blank",
                            x=x,
                            y=max(0.0, y - 10),
                            w=abs(float(start.x) - float(end.x)),
                            h=14.0,
                            content=nearby,
                            hint=nearby,
                        )
                    )
    finally:
        document.close()
    return regions


def _tokens(*parts: str) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        tokens.update(_TOKEN_RE.findall(part.lower()))
    # Drop tiny / generic tokens that do not help matching.
    return {
        token
        for token in tokens
        if len(token) > 2 and token not in {"the", "and", "for"}
    }


def _region_kinds_for_type(ftype: str) -> frozenset[RegionKind]:
    if ftype == FieldType.SIGNATURE or ftype == FieldType.INITIALS:
        return frozenset({"signature", "blank"})
    if ftype == FieldType.CHECKBOX:
        return frozenset({"checkbox", "blank"})
    return frozenset({"blank"})


def _score_region(field: dict[str, Any], region: OcrRegion) -> float:
    wanted = _tokens(str(field.get("name") or ""), str(field.get("anchor") or ""))
    have = _tokens(region.content, region.hint)
    if not wanted:
        return 0.1
    overlap = len(wanted & have)
    if overlap == 0:
        return 0.0
    return overlap / len(wanted)


def _fit_box(
    *,
    ftype: str,
    x: float,
    y: float,
    w: float,
    h: float,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float]:
    min_w, min_h = _MIN_BOX.get(FieldType(ftype), (80.0, 14.0))
    w = max(w, min_w)
    h = max(h, min_h)
    # Signature lines are often short height-wise; give a usable pad.
    if ftype in {FieldType.SIGNATURE, FieldType.INITIALS}:
        h = max(h, min_h)
        w = max(w, min_w)
    x = min(max(0.0, x), max(0.0, page_width - w))
    y = min(max(0.0, y), max(0.0, page_height - h))
    w = min(w, page_width - x)
    h = min(h, page_height - y)
    return round(x, 3), round(y, 3), round(w, 3), round(h, 3)


def _fallback_fields_from_regions(
    regions: list[OcrRegion],
    *,
    page_sizes: dict[int, tuple[float, float]],
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    blank_n = 0
    sig_n = 0
    for region in regions:
        pdf_width, pdf_height = page_sizes[region.page]
        if region.kind == "signature":
            sig_n += 1
            ftype = FieldType.SIGNATURE
            role = SIGNER_ROLE
            name = "AgentSignature" if sig_n == 1 else f"AgentSignature{sig_n}"
        elif region.kind == "checkbox":
            blank_n += 1
            ftype = FieldType.CHECKBOX
            role = PREFILL_ROLE
            name = f"PrefillCheckbox{blank_n}"
        else:
            blank_n += 1
            ftype = FieldType.TEXT
            role = PREFILL_ROLE
            name = f"PrefillText{blank_n}"
        x, y, w, h = _fit_box(
            ftype=ftype,
            x=region.x,
            y=region.y,
            w=region.w,
            h=region.h,
            page_width=pdf_width,
            page_height=pdf_height,
        )
        fields.append(
            {
                "id": new_field_id(),
                "name": name,
                "type": ftype,
                "role": role,
                "page": region.page,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "suggested": True,
            }
        )
    return fields


def map_fields_to_ocr_regions(
    annotation_fields: list[dict[str, Any]],
    regions: list[OcrRegion],
    *,
    page_sizes: dict[int, tuple[float, float]],
) -> list[dict[str, Any]]:
    """Attach annotation labels to measured OCR regions; never trust freeform x/y."""
    if not regions:
        return []
    if not annotation_fields:
        return _fallback_fields_from_regions(regions, page_sizes=page_sizes)

    unused = list(regions)
    mapped: list[dict[str, Any]] = []
    for field in annotation_fields:
        page = int(field["page"])
        if page not in page_sizes:
            continue
        kinds = _region_kinds_for_type(str(field["type"]))
        candidates = [
            (idx, region)
            for idx, region in enumerate(unused)
            if region.page == page and region.kind in kinds
        ]
        if not candidates:
            continue
        scored = sorted(
            (
                (_score_region(field, region), -idx, idx, region)
                for idx, region in candidates
            ),
            reverse=True,
        )
        score, _neg, best_idx, region = scored[0]
        # Never consume an arbitrary blank when more than one candidate has no
        # semantic evidence.  Returning no suggestion is safe; a misplaced
        # signing field is not.
        if score <= 0 and len(candidates) > 1:
            continue
        unused.pop(best_idx)
        pdf_width, pdf_height = page_sizes[page]
        x, y, w, h = _fit_box(
            ftype=str(field["type"]),
            x=region.x,
            y=region.y,
            w=region.w,
            h=region.h,
            page_width=pdf_width,
            page_height=pdf_height,
        )
        mapped.append(
            {
                "id": new_field_id(),
                "name": str(field["name"]),
                "type": str(field["type"]),
                "role": str(field["role"]),
                "page": page,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "suggested": True,
            }
        )
    return mapped


def suggest_layout_from_ocr(
    response: Any,
    *,
    page_sizes: dict[int, tuple[float, float]],
    pdf_bytes: bytes | None = None,
) -> list[dict[str, Any]]:
    """Build Hub field suggestions from OCR blocks + annotation labels."""
    native_regions = extract_native_pdf_regions(pdf_bytes or b"")
    ocr_regions = extract_ocr_regions(response, page_sizes=page_sizes)
    # Native blanks are exact for digital PDFs. Keep OCR-only signature and
    # checkbox detections, since those often have no text or drawing primitive.
    regions = native_regions + [
        region for region in ocr_regions if region.kind in {"signature", "checkbox"}
    ]
    if not regions:
        regions = ocr_regions
    labels = _annotation_fields(response)
    suggestions = map_fields_to_ocr_regions(labels, regions, page_sizes=page_sizes)
    # Unique names.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for field in suggestions:
        name = str(field["name"])
        base = name
        n = 2
        while name in seen:
            name = f"{base}{n}"
            n += 1
        field = {**field, "name": name}
        seen.add(name)
        unique.append(field)
    try:
        normalized = normalize_field_layout(
            [{k: v for k, v in row.items() if k != "suggested"} for row in unique]
        )
        for row in normalized:
            row["suggested"] = True
        return normalized
    except ValidationError:
        return unique
