"""Presentation adapters for compliance taxonomy codes."""

from __future__ import annotations

from typing import Any

from apps.compliance.models import PolicyCategory, PolicyVersion

_STATUS_TONE = {
    PolicyVersion.Status.DRAFT: "neutral",
    PolicyVersion.Status.IN_REVIEW: "info",
    PolicyVersion.Status.APPROVED: "info",
    PolicyVersion.Status.PUBLISHED: "success",
    PolicyVersion.Status.SUPERSEDED: "warning",
    PolicyVersion.Status.RETIRED: "neutral",
}

_STATUS_LABEL = dict(PolicyVersion.Status.choices)


def present_category(category: PolicyCategory | None) -> dict[str, Any] | None:
    if category is None:
        return None
    return {
        "code": category.code,
        "label": category.label,
        "tone": "neutral",
        "known": True,
    }


def present_status(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "label": _STATUS_LABEL.get(code, code),
        "tone": _STATUS_TONE.get(code, "neutral"),
        "known": code in _STATUS_LABEL,
    }
