"""Presentation adapters for training taxonomy codes."""

from __future__ import annotations

from typing import Any

from apps.training.models import TrainingCategory
from apps.training.taxonomy import CONTENT_TYPE_CHOICES

_TYPE_LABELS = dict(CONTENT_TYPE_CHOICES)

_TONE_BY_TYPE = {
    "article": "neutral",
    "guide": "info",
    "video": "brand",
    "checklist": "success",
    "course": "brand",
    "quiz": "warning",
    "live_session": "urgent",
    "recording": "brand",
    "tool_onboarding": "info",
}


def present_category(category: TrainingCategory | None) -> dict[str, Any]:
    if category is None:
        return {
            "code": "",
            "label": "Uncategorized",
            "tone": "neutral",
            "known": False,
        }
    return {
        "code": category.code,
        "label": category.label,
        "tone": "neutral",
        "known": True,
    }


def present_content_type(code: str) -> dict[str, Any]:
    normalized = (code or "").strip()
    label = _TYPE_LABELS.get(normalized, normalized or "Unknown")
    return {
        "code": normalized,
        "label": label,
        "tone": _TONE_BY_TYPE.get(normalized, "neutral"),
        "known": normalized in _TYPE_LABELS,
    }
