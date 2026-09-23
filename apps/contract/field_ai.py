"""Vision-assisted field placement suggestions for Hub template authoring."""

from __future__ import annotations

import io
import urllib.error
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from pypdf import PdfReader

from apps.contract.document_ocr import (
    ocr_configured,
    ocr_document,
    suggest_layout_from_ocr,
)

_GEMINI_HOST = "generativelanguage.googleapis.com"
_GEMINI_DEFAULT_MODEL = "gemini-3.6-flash"
_OPENAI_DEFAULT_MODEL = "gpt-4o"
# Gemini OpenAI-compat used to inherit gpt-4o, then gemini-2.5-flash. Google
# returns 404 for those ids for new API keys.
_GEMINI_LEGACY_MODELS = frozenset({_OPENAI_DEFAULT_MODEL, "gemini-2.5-flash"})


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
        if model in _GEMINI_LEGACY_MODELS:
            model = _GEMINI_DEFAULT_MODEL
        return url, headers, model

    if lowered.endswith("/v1") or lowered.endswith("/openai"):
        url = f"{endpoint}/chat/completions"
    else:
        url = f"{endpoint}/v1/chat/completions"
    return url, headers, model


def _http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read()[:400].decode("utf-8", errors="replace")
    except (OSError, AttributeError, UnicodeError):
        return ""


def _field_ai_http_message(status: int) -> str:
    if status in {401, 403}:
        return "Field AI rejected the API key."
    if status == 404:
        return (
            "Field AI model was not found. Set CONTRACT_FIELD_AI_MODEL to a "
            "current model (for Gemini, gemini-3.6-flash)."
        )
    if status == 429:
        return "Field AI is rate-limited. Try again in a moment."
    return "Field AI request failed. Try again later."


def field_ai_configured() -> bool:
    endpoint = (getattr(settings, "CONTRACT_FIELD_AI_ENDPOINT", "") or "").strip()
    key = (getattr(settings, "CONTRACT_FIELD_AI_API_KEY", "") or "").strip()
    return bool(endpoint and key)


def _page_sizes(pdf_bytes: bytes, *, max_pages: int) -> dict[int, tuple[float, float]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    sizes: dict[int, tuple[float, float]] = {}
    for index, page in enumerate(reader.pages[: max(1, max_pages)], start=1):
        sizes[index] = (float(page.mediabox.width), float(page.mediabox.height))
    return sizes


def suggest_fields_for_pdf(
    pdf_bytes: bytes, *, max_pages: int = 8
) -> list[dict[str, Any]]:
    """Propose field boxes from Mistral OCR blocks + annotation labels."""
    if not ocr_configured():
        raise ValidationError(
            {"form": ["Document OCR is not configured. Set MISTRAL_API_KEY."]}
        )

    page_sizes = _page_sizes(pdf_bytes, max_pages=max_pages)
    if not page_sizes:
        raise ValidationError({"form": ["Document OCR requires a PDF with pages."]})

    response = ocr_document(pdf_bytes, max_pages=max_pages)
    return suggest_layout_from_ocr(
        response,
        page_sizes=page_sizes,
        pdf_bytes=pdf_bytes,
    )
