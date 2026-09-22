"""Field placement normalization for transaction signature packages.

The contract builder keys fields by a fixed role vocabulary (``Prefill`` /
``Agent`` / ``Company``). A deal package has an open-ended signer list instead,
so the role key here is the signer's ``public_id`` string. Geometry rules match
the contract placer: top-left origin, page numbers are 1-based, and the same
name grammar keeps stored names safe to echo in audit payloads.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError

from apps.transactions.taxonomy import (
    SIGNATURE_FIELD_TYPE_CODES,
    SignatureFieldType,
)

FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,79}$")

#: Types whose ink comes from the signing pad rather than a typed value.
DRAWN_FIELD_TYPES = frozenset(
    {SignatureFieldType.SIGNATURE, SignatureFieldType.INITIALS}
)

#: Types the signer fills with characters during the ceremony.
TYPED_FIELD_TYPES = frozenset({SignatureFieldType.DATE, SignatureFieldType.TEXT})

MAX_PACKAGE_FIELDS = 400


def _error(message: str) -> ValidationError:
    return ValidationError({"fields": [message]})


def _key(value: Any) -> str:
    """Accept a UUID, a UUID string, or a model public_id and return its text."""
    if isinstance(value, UUID):
        return str(value)
    return str(value or "").strip()


def _geometry(
    item: dict[str, Any], *, name: str
) -> tuple[int, float, float, float, float]:
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
        raise _error(f"Field {name} has invalid page or coordinates.") from exc

    if page < 1:
        raise _error(f"Field {name} page must be >= 1.")
    if w <= 0 or h <= 0:
        raise _error(f"Field {name} width and height must be positive.")
    if x < 0 or y < 0:
        raise _error(f"Field {name} coordinates cannot be negative.")
    return page, x, y, w, h


def _normalize_field(
    item: Any,
    *,
    index: int,
    signer_keys: frozenset[str],
    document_keys: frozenset[str],
    page_counts: dict[str, int] | None,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _error(f"Field at index {index} must be an object.")

    name = str(item.get("name") or "").strip()
    if not name or not FIELD_NAME_RE.match(name):
        raise _error(
            f"Field at index {index} needs a name matching [A-Za-z][A-Za-z0-9_.]*."
        )

    field_type = str(item.get("type") or "").strip()
    if field_type not in SIGNATURE_FIELD_TYPE_CODES:
        raise _error(f"Field {name} has unsupported type {field_type or '(empty)'}.")

    signer_key = _key(
        item.get("signerKey") or item.get("signer_key") or item.get("signer")
    )
    if not signer_key:
        raise _error(f"Field {name} must name the signer it belongs to.")
    if signer_keys and signer_key not in signer_keys:
        raise _error(f"Field {name} names a signer that is not on this package.")

    document_key = _key(
        item.get("documentKey") or item.get("document_key") or item.get("document")
    )
    if not document_key:
        raise _error(f"Field {name} must name the document it sits on.")
    if document_keys and document_key not in document_keys:
        raise _error(f"Field {name} names a document that is not in this package.")

    page, x, y, w, h = _geometry(item, name=name)
    if page_counts is not None:
        limit = page_counts.get(document_key)
        if limit is not None and page > limit:
            raise _error(f"Field {name} is on page {page} of a {limit}-page document.")

    required = item.get("required")
    return {
        "name": name,
        "type": field_type,
        "signerKey": signer_key,
        "documentKey": document_key,
        "page": page,
        "x": round(x, 3),
        "y": round(y, 3),
        "w": round(w, 3),
        "h": round(h, 3),
        "required": True if required is None else bool(required),
    }


def normalize_package_fields(
    raw: Any,
    *,
    signer_keys: set[str] | frozenset[str] = frozenset(),
    document_keys: set[str] | frozenset[str] = frozenset(),
    page_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Validate a package field layout and return storage-ready dicts.

    ``page_counts`` maps a document key to its page count; when supplied, a
    field beyond the last page is refused rather than silently dropped at
    stamp time.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise _error("Field layout must be an array.")
    if len(raw) > MAX_PACKAGE_FIELDS:
        raise _error(f"A package can carry at most {MAX_PACKAGE_FIELDS} fields.")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        field = _normalize_field(
            item,
            index=index,
            signer_keys=frozenset(signer_keys),
            document_keys=frozenset(document_keys),
            page_counts=page_counts,
        )
        name = field["name"]
        if name in seen:
            raise _error(f"Duplicate field name: {name}.")
        seen.add(name)
        normalized.append(field)
    return normalized


def fields_for_signer(
    fields: list[dict[str, Any]], *, signer_key: str
) -> list[dict[str, Any]]:
    key = _key(signer_key)
    return [item for item in fields if item.get("signerKey") == key]


def fields_for_document(
    fields: list[dict[str, Any]], *, document_key: str
) -> list[dict[str, Any]]:
    key = _key(document_key)
    return [item for item in fields if item.get("documentKey") == key]


def signer_keys_with_required_fields(fields: list[dict[str, Any]]) -> set[str]:
    return {str(item["signerKey"]) for item in fields if item.get("required", True)}


def typed_field_names(fields: list[dict[str, Any]]) -> set[str]:
    """Names a signer may submit values for — drawn ink is not a text value."""
    return {
        str(item["name"])
        for item in fields
        if str(item.get("type")) in TYPED_FIELD_TYPES
    }


__all__ = [
    "DRAWN_FIELD_TYPES",
    "FIELD_NAME_RE",
    "MAX_PACKAGE_FIELDS",
    "TYPED_FIELD_TYPES",
    "fields_for_document",
    "fields_for_signer",
    "normalize_package_fields",
    "signer_keys_with_required_fields",
    "typed_field_names",
]
