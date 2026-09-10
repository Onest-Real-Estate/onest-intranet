"""Hub-owned field placement layout for contract templates."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any
from uuid import uuid4

from django.core.exceptions import ValidationError

FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,79}$")

PREFILL_ROLE = "Prefill"
SIGNER_ROLE = "Agent"
COMPANY_ROLE = "Company"


class FieldType(StrEnum):
    TEXT = "text"
    SIGNATURE = "signature"
    DATE = "date"
    INITIALS = "initials"
    CHECKBOX = "checkbox"


class SignerRole(StrEnum):
    """Human ceremony roles that leave ink on the PDF (not Prefill)."""

    AGENT = SIGNER_ROLE
    COMPANY = COMPANY_ROLE


ALLOWED_FIELD_TYPES = frozenset(member.value for member in FieldType)
ALLOWED_ROLES = frozenset({PREFILL_ROLE, SIGNER_ROLE, COMPANY_ROLE})
HUMAN_SIGNER_ROLES = frozenset({SIGNER_ROLE, COMPANY_ROLE})

# Hub stamps Prefill values from merge sources at generation time. Signature /
# initials have no merge source — they are captured on a signing pad.
PREFILL_FIELD_TYPES = frozenset(
    {
        FieldType.TEXT,
        FieldType.DATE,
        FieldType.CHECKBOX,
    }
)
SIGNING_ONLY_FIELD_TYPES = frozenset(
    {
        FieldType.SIGNATURE,
        FieldType.INITIALS,
    }
)


def new_field_id() -> str:
    return str(uuid4())


def normalize_field_layout(raw: Any) -> list[dict[str, Any]]:
    """Validate and normalize a field layout list for persistence."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError({"field_layout": ["Field layout must be an array."]})

    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValidationError(
                {"field_layout": [f"Field at index {index} must be an object."]}
            )
        field = _normalize_field(item, index=index)
        name = str(field["name"])
        if name in seen_names:
            raise ValidationError({"field_layout": [f"Duplicate field name: {name}."]})
        seen_names.add(name)
        normalized.append(field)
    return normalized


def _normalize_field(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    name = str(item.get("name") or "").strip()
    if not name or not FIELD_NAME_RE.match(name):
        raise ValidationError(
            {
                "field_layout": [
                    f"Field at index {index} needs a name matching "
                    "[A-Za-z][A-Za-z0-9_.]*."
                ]
            }
        )

    field_type = str(item.get("type") or "").strip()
    if field_type not in ALLOWED_FIELD_TYPES:
        raise ValidationError(
            {
                "field_layout": [
                    f"Field {name} has unsupported type {field_type or '(empty)'}."
                ]
            }
        )

    role = str(item.get("role") or "").strip()
    if role not in ALLOWED_ROLES:
        raise ValidationError(
            {
                "field_layout": [
                    f"Field {name} must use role Prefill, Agent, or Company."
                ]
            }
        )

    if role == PREFILL_ROLE and field_type in SIGNING_ONLY_FIELD_TYPES:
        raise ValidationError(
            {
                "field_layout": [
                    f"Field {name} is a {field_type} box — use the Agent or "
                    "Company role. Signatures and initials are drawn at signing, "
                    "not prefilled from hub data."
                ]
            }
        )

    try:
        raw_page = item.get("page")
        raw_x = item.get("x")
        raw_y = item.get("y")
        raw_w = item.get("w")
        raw_h = item.get("h")
        if (
            raw_page is None
            or raw_x is None
            or raw_y is None
            or raw_w is None
            or raw_h is None
        ):
            raise TypeError("missing geometry")
        page = int(raw_page)
        x = float(raw_x)
        y = float(raw_y)
        w = float(raw_w)
        h = float(raw_h)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            {"field_layout": [f"Field {name} has invalid page or coordinates."]}
        ) from exc

    if page < 1:
        raise ValidationError({"field_layout": [f"Field {name} page must be >= 1."]})
    if w <= 0 or h <= 0:
        raise ValidationError(
            {"field_layout": [f"Field {name} width and height must be positive."]}
        )
    if x < 0 or y < 0:
        raise ValidationError(
            {"field_layout": [f"Field {name} coordinates cannot be negative."]}
        )

    field_id = str(item.get("id") or "").strip() or new_field_id()
    return {
        "id": field_id,
        "name": name,
        "type": field_type,
        "role": role,
        "page": page,
        "x": round(x, 3),
        "y": round(y, 3),
        "w": round(w, 3),
        "h": round(h, 3),
    }


def prefill_field_names(layout: list[dict[str, Any]]) -> list[str]:
    """Prefill names that need hub merge mapping (excludes signing-only types)."""
    return [
        str(item["name"])
        for item in layout
        if str(item.get("role")) == PREFILL_ROLE
        and str(item.get("type") or "") in PREFILL_FIELD_TYPES
        and str(item.get("name") or "").strip()
    ]


def _has_signature_and_date(layout: list[dict[str, Any]], *, role: str) -> bool:
    has_signature = False
    has_date = False
    for item in layout:
        if str(item.get("role")) != role:
            continue
        field_type = str(item.get("type") or "")
        if field_type == FieldType.SIGNATURE:
            has_signature = True
        elif field_type == FieldType.DATE:
            has_date = True
    return has_signature and has_date


def has_required_agent_fields(layout: list[dict[str, Any]]) -> bool:
    """Publish requires at least one Agent signature and one Agent date."""
    return _has_signature_and_date(layout, role=SIGNER_ROLE)


def has_required_company_fields(layout: list[dict[str, Any]]) -> bool:
    """Publish requires at least one Company signature and one Company date."""
    return _has_signature_and_date(layout, role=COMPANY_ROLE)


def assert_publishable_layout(layout: list[dict[str, Any]]) -> None:
    if not layout:
        raise ValidationError(
            {"field_layout": ["Place at least one field before publishing."]}
        )
    if not has_required_agent_fields(layout):
        raise ValidationError(
            {
                "field_layout": [
                    "Add Agent signature and Agent date fields before publishing."
                ]
            }
        )
    if not has_required_company_fields(layout):
        raise ValidationError(
            {
                "field_layout": [
                    "Add Company signature and Company date fields before publishing."
                ]
            }
        )


def agent_fields(layout: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in layout if str(item.get("role")) == SIGNER_ROLE]


def company_fields(layout: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in layout if str(item.get("role")) == COMPANY_ROLE]


def fields_for_role(layout: list[dict[str, Any]], *, role: str) -> list[dict[str, Any]]:
    return [item for item in layout if str(item.get("role")) == role]
