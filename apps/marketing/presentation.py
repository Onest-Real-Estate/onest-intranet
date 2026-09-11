"""Presentation adapters for marketing taxonomy codes."""

from __future__ import annotations

from typing import Any

from apps.marketing.models import MarketingCategory
from apps.marketing.taxonomy import ASSET_TYPE_CHOICES

_TONE_BY_TYPE = {
    "logo": "brand",
    "guideline": "info",
    "template": "neutral",
    "flyer": "success",
    "email_signature": "info",
    "vendor_guidance": "warning",
    "campaign": "brand",
}

_LABEL_BY_TYPE = dict(ASSET_TYPE_CHOICES)


def present_category(category: MarketingCategory | None) -> dict[str, Any] | None:
    if category is None:
        return None
    return {
        "code": category.code,
        "label": category.label,
        "tone": "neutral",
        "known": True,
    }


def present_asset_type(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "label": _LABEL_BY_TYPE.get(code, code),
        "tone": _TONE_BY_TYPE.get(code, "neutral"),
        "known": code in _LABEL_BY_TYPE,
    }
