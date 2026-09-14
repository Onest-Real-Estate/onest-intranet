"""Vision-assisted field placement suggestions for Hub template authoring."""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.contract.field_layout import (
    PREFILL_ROLE,
    SIGNER_ROLE,
    FieldType,
    new_field_id,
    normalize_field_layout,
)

logger = logging.getLogger(__name__)

_ALLOWED_TYPES = frozenset(member.value for member in FieldType)
_GEMINI_HOST = "generativelanguage.googleapis.com"
_GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
_OPENAI_DEFAULT_MODEL = "gpt-4o"


def _chat_completions_target(
    *,
    endpoint: str,
    api_key: str,
    deployment: str = "",
    api_version: str = "2024-08-01-preview",
    model: str = _OPENAI_DEFAULT_MODEL,
) -> tuple[str, dict[str, str], str]:
    """Return (url, headers, model) for Azure OpenAI, OpenAI, or Gemini."""
    endpoint = endpoint.rstrip("/")
    deployment = (deployment or "").strip()
    model = (model or "").strip() or _OPENAI_DEFAULT_MODEL

    if deployment:
        url = (
            f"{endpoint}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={api_version or '2024-08-01-preview'}"
        )
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        return url, headers, deployment

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    lowered = endpoint.lower()
    if _GEMINI_HOST in lowered:
        url = (
            f"{endpoint}/chat/completions"
            if lowered.endswith("/openai")
            else f"{endpoint}/v1beta/openai/chat/completions"
        )
        if model == _OPENAI_DEFAULT_MODEL:
            model = _GEMINI_DEFAULT_MODEL
        return url, headers, model

    if lowered.endswith("/v1") or lowered.endswith("/openai"):
        url = f"{endpoint}/chat/completions"
    else:
        url = f"{endpoint}/v1/chat/completions"
    return url, headers, model


def field_ai_configured() -> bool:
    endpoint = (getattr(settings, "CONTRACT_FIELD_AI_ENDPOINT", "") or "").strip()
    key = (getattr(settings, "CONTRACT_FIELD_AI_API_KEY", "") or "").strip()
    return bool(endpoint and key)


def render_pdf_page_png(
    pdf_bytes: bytes, *, page_number: int, scale: float = 1.5
) -> tuple[bytes, float, float]:
    """Render one PDF page to PNG via pypdf + reportlab fallback bitmap.

    Uses Pillow to rasterize a blank white page with embedded page content
    converted through pypdf page box metadata; for robust rendering we prefer
    pymupdf when available, else a simple white canvas sized to the page so
    AI still receives page dimensions (tests mock this function).
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if page_number < 1 or page_number > len(reader.pages):
        raise ValidationError({"form": [f"PDF has no page {page_number}."]})
    page = reader.pages[page_number - 1]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)

    try:
        import importlib

        fitz = importlib.import_module("fitz")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pix = doc.load_page(page_number - 1).get_pixmap(
            matrix=fitz.Matrix(scale, scale)
        )
        return pix.tobytes("png"), width, height
    except Exception:  # noqa: BLE001
        from PIL import Image, ImageDraw

        img_w = max(1, int(width * scale))
        img_h = max(1, int(height * scale))
        image = Image.new("RGB", (img_w, img_h), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, img_w - 1, img_h - 1), outline=(180, 180, 180))
        draw.text((12, 12), f"Page {page_number}", fill=(40, 40, 40))
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue(), width, height


def _parse_suggestions(
    raw: Any, *, page_number: int, page_width: float, page_height: float
) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
            if not match:
                return []
            try:
                raw = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []
    if isinstance(raw, dict):
        raw = raw.get("fields") or raw.get("suggestions") or []
    if not isinstance(raw, list):
        return []

    suggestions: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ftype = str(item.get("type") or "").strip()
        role = str(item.get("role") or "").strip()
        if ftype not in _ALLOWED_TYPES:
            continue
        if role not in {PREFILL_ROLE, SIGNER_ROLE}:
            # Heuristic: signature/date/initials → Agent; else Prefill.
            role = (
                SIGNER_ROLE
                if ftype in {FieldType.SIGNATURE, FieldType.DATE, FieldType.INITIALS}
                else PREFILL_ROLE
            )
        # Signature/initials are never Prefill — no hub source can stamp them.
        if role == PREFILL_ROLE and ftype in {
            FieldType.SIGNATURE,
            FieldType.INITIALS,
        }:
            role = SIGNER_ROLE
        # Prefer Company only when the model explicitly said so; leave Agent as-is.
        try:
            # Accept normalized 0-1 coords or PDF points.
            x = float(item.get("x"))
            y = float(item.get("y"))
            w = float(item.get("w"))
            h = float(item.get("h"))
        except (TypeError, ValueError):
            continue
        if 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1:
            x *= page_width
            y *= page_height
            w *= page_width
            h *= page_height
        name = str(item.get("name") or "").strip()
        if not name:
            label = ftype[:1].upper() + ftype[1:]
            name = f"{role}{label}"
        suggestions.append(
            {
                "id": new_field_id(),
                "name": name,
                "type": ftype,
                "role": role,
                "page": page_number,
                "x": round(x, 3),
                "y": round(y, 3),
                "w": round(w, 3),
                "h": round(h, 3),
                "suggested": True,
            }
        )
    # Normalize names / coords through the same validator when possible.
    try:
        return normalize_field_layout(
            [{k: v for k, v in row.items() if k != "suggested"} for row in suggestions]
        )
    except ValidationError:
        return suggestions


def suggest_fields_for_pdf(
    pdf_bytes: bytes, *, max_pages: int = 8
) -> list[dict[str, Any]]:
    """Call Azure OpenAI, OpenAI, or Gemini vision chat to propose field boxes."""
    if not field_ai_configured():
        raise ValidationError(
            {"form": ["Field AI is not configured (endpoint and API key required)."]}
        )

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_count = min(len(reader.pages), max(1, max_pages))
    url, headers, model = _chat_completions_target(
        endpoint=settings.CONTRACT_FIELD_AI_ENDPOINT or "",
        api_key=settings.CONTRACT_FIELD_AI_API_KEY,
        deployment=getattr(settings, "CONTRACT_FIELD_AI_DEPLOYMENT", "") or "",
        api_version=getattr(settings, "CONTRACT_FIELD_AI_API_VERSION", "")
        or "2024-08-01-preview",
        model=getattr(settings, "CONTRACT_FIELD_AI_MODEL", _OPENAI_DEFAULT_MODEL)
        or _OPENAI_DEFAULT_MODEL,
    )

    import urllib.error
    import urllib.request

    all_fields: list[dict[str, Any]] = []
    for page_number in range(1, page_count + 1):
        png, page_width, page_height = render_pdf_page_png(
            pdf_bytes, page_number=page_number
        )
        b64 = base64.b64encode(png).decode("ascii")
        prompt = (
            "You help place DocuSign-style form fields on an agent ICA PDF. "
            'Return JSON only: {"fields":[{"name","type","role","x","y","w","h"}]}. '
            "type is one of text,signature,date,initials,checkbox. "
            "role is Prefill (brokerage-filled commercial text/date/checkbox) or "
            "Agent (signer). Signature and initials MUST use role Agent. "
            "Coordinates are PDF points with origin at the top-left of the page. "
            f"Page size is {page_width:.1f} x {page_height:.1f} points. "
            "Prefer Agent signature and Agent date near signature lines."
        )
        body = {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            logger.warning("field AI request failed page=%s", page_number)
            raise ValidationError(
                {"form": ["Field AI request failed. Try again later."]}
            ) from exc

        content = ""
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = ""
        all_fields.extend(
            _parse_suggestions(
                content,
                page_number=page_number,
                page_width=page_width,
                page_height=page_height,
            )
        )

    # Ensure unique names.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for field in all_fields:
        name = str(field["name"])
        base = name
        n = 2
        while name in seen:
            name = f"{base}{n}"
            n += 1
        field["name"] = name
        seen.add(name)
        unique.append(field)
    return unique
