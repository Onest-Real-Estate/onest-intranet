"""The one place announcement taxonomy becomes something a badge can render.

What crosses this boundary is a **semantic tone** — ``neutral``, ``info``,
``success``, ``warning``, ``destructive`` — matching
``frontend/types/design-system.ts``. Tones are meanings, not colors: the
design system decides what ``warning`` looks like, in either theme, and can
change that without touching a row or a payload here.

Two rules keep this adapter honest:

* **Nothing about appearance is stored.** The domain model holds codes; this
  module holds the map from code to meaning. Adding a category through the
  admin therefore needs no deploy — it simply lands on the documented default
  tone until someone decides it deserves another.
* **Color is never the only carrier.** Every payload carries a ``label`` and a
  ``srLabel`` sentence, so priority is legible to a screen reader and to
  anyone who cannot separate the tones. See ``docs/announcements.md``.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from apps.announcements.taxonomy import (
    FALLBACK_CATEGORY_CODE,
    PRIORITY_IMPORTANT,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    ResolvedCategory,
    ResolvedPriority,
    resolve_category,
    resolve_priority,
)

Tone = Literal["neutral", "info", "success", "warning", "destructive"]

#: Priority is a closed set, so this map is total by construction.
PRIORITY_TONES: dict[str, Tone] = {
    PRIORITY_URGENT: "destructive",
    PRIORITY_IMPORTANT: "warning",
    PRIORITY_NORMAL: "neutral",
}

#: Categories are admin-managed, so this map is deliberately partial. A code
#: that is not listed — including every category created after this deploy —
#: renders on ``DEFAULT_CATEGORY_TONE``. That is the documented fallback, not
#: an omission to fix each time the vocabulary grows.
CATEGORY_TONES: dict[str, Tone] = {
    "company_announcement": "info",
    "market_update": "neutral",
    "event": "success",
    "training_notice": "info",
    "compliance_update": "warning",
    "office_notice": "neutral",
    "technology_notice": "neutral",
    "urgent_operational_notice": "destructive",
}

DEFAULT_CATEGORY_TONE: Tone = "neutral"


class BadgePayload(TypedDict):
    code: str
    label: str
    tone: str
    srLabel: str
    known: bool


class PriorityBadgePayload(BadgePayload):
    rank: int


def priority_tone(code: str | None) -> Tone:
    return PRIORITY_TONES.get(resolve_priority(code).code, DEFAULT_CATEGORY_TONE)


def category_tone(code: str | None) -> Tone:
    return CATEGORY_TONES.get(code or "", DEFAULT_CATEGORY_TONE)


def _priority_sentence(resolved: ResolvedPriority) -> str:
    if not resolved.known and resolved.requested_code:
        return (
            f"Priority: {resolved.label} "
            f"(unrecognized code “{resolved.requested_code}”, shown as "
            f"{resolved.label.lower()})"
        )
    return f"Priority: {resolved.label}"


def _category_sentence(resolved: ResolvedCategory) -> str:
    if resolved.code == FALLBACK_CATEGORY_CODE:
        return "Category: not set"
    if not resolved.is_active:
        return f"Category: {resolved.label} (retired)"
    return f"Category: {resolved.label}"


def present_priority(code: str | None) -> PriorityBadgePayload:
    resolved = resolve_priority(code)
    return {
        "code": resolved.code,
        "label": resolved.label,
        "tone": PRIORITY_TONES.get(resolved.code, DEFAULT_CATEGORY_TONE),
        "srLabel": _priority_sentence(resolved),
        "known": resolved.known,
        "rank": resolved.rank,
    }


def present_category(category) -> BadgePayload:
    resolved = resolve_category(category)
    return {
        "code": resolved.code,
        "label": resolved.label,
        "tone": category_tone(resolved.code),
        "srLabel": _category_sentence(resolved),
        "known": resolved.known,
    }
