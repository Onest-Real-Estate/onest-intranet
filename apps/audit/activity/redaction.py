"""Field-level redaction for user-facing activity projections."""

from __future__ import annotations

from typing import Any

from apps.audit.service import redact as audit_redact
from apps.user.services.role_assignments import has_effective_permission

SENSITIVE_FIELD_PERMISSIONS: dict[str, str] = {
    "email": "user.view_user_administration",
    "phone": "user.view_user_administration",
    "street_address": "user.view_user_administration",
    "zip_code": "user.view_user_administration",
    "internal_notes": "user.view_user_administration",
    "license_number": "user.view_user_administration",
    "ssn": "audit.can_view_audit_events",
    "bank_account": "audit.can_view_audit_events",
    "commission_rate": "web.view_own_commission",
    "document": "web.manage_documents",
    "content": "web.manage_documents",
    "headshot": "user.view_user_administration",
}

ALWAYS_REDACT_FRAGMENTS = frozenset(
    {
        "password",
        "token",
        "secret",
        "credential",
        "ssn",
        "credit_card",
        "cvv",
    }
)

REDACTED = "[REDACTED]"


def _field_allowed(viewer, field_name: str) -> bool:
    permission = SENSITIVE_FIELD_PERMISSIONS.get(field_name)
    if permission is None:
        lowered = field_name.lower()
        if any(fragment in lowered for fragment in ALWAYS_REDACT_FRAGMENTS):
            return False
        return has_effective_permission(viewer, "audit.can_view_audit_events")
    return has_effective_permission(viewer, permission)


def summarize_changes(
    changes: dict[str, Any] | None,
    *,
    viewer,
) -> tuple[tuple[str, ...], dict[str, Any], str]:
    """Return (labels, safe change map, visibility)."""
    changes = changes or {}
    if not changes:
        return (), {}, "full"

    labels: list[str] = []
    safe: dict[str, Any] = {}
    hidden = 0
    shown = 0

    for field_name in sorted(changes):
        change = changes[field_name]
        if not _field_allowed(viewer, field_name):
            labels.append(field_name)
            hidden += 1
            continue
        labels.append(field_name)
        shown += 1
        if isinstance(change, dict):
            safe[field_name] = {
                "before": audit_redact(change.get("before")),
                "after": audit_redact(change.get("after")),
            }
        else:
            safe[field_name] = audit_redact(change)

    if hidden and shown:
        visibility = "redacted"
    elif hidden:
        visibility = "summary"
    else:
        visibility = "full"
    return tuple(labels), safe, visibility


def scrub_metadata(metadata: dict[str, Any] | None, *, viewer) -> dict[str, Any]:
    if not metadata:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = key.lower()
        if any(fragment in lowered for fragment in ALWAYS_REDACT_FRAGMENTS):
            continue
        if key in SENSITIVE_FIELD_PERMISSIONS and not _field_allowed(viewer, key):
            cleaned[key] = REDACTED
            continue
        cleaned[key] = audit_redact(value)
    return cleaned
