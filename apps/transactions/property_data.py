"""Property field updates with immutable snapshot history."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.service import AuditTarget, actor_from_user, log_on_commit
from apps.transactions.concurrency import (
    require_writable_transaction,
    touch_transaction,
)
from apps.transactions.models import Transaction, TransactionPropertySnapshot
from apps.user.models import User

_PROPERTY_KEYS = (
    "line1",
    "address_line1",
    "line2",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "country",
    "parcel_id",
    "unit",
)


def _audit_target(tx: Transaction) -> AuditTarget:
    return AuditTarget(
        target_type="transaction.transaction",
        target_id=str(tx.public_id),
        target_label=tx.reference or str(tx.public_id),
        target_snapshot={
            "public_id": str(tx.public_id),
            "reference": tx.reference,
            "status": tx.status,
            "office_id": tx.office.stable_key if tx.office_pk else "",
        },
    )


def _normalize_snapshot(raw: dict | None) -> dict[str, str]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError({"property": ["Must be an object."]})
    out: dict[str, str] = {}
    for key in _PROPERTY_KEYS:
        camel = "".join(
            part.capitalize() if i else part for i, part in enumerate(key.split("_"))
        )
        # Accept both snake and camel (line1 / addressLine1 style).
        value = raw.get(key)
        if value is None and key == "line1":
            value = raw.get("addressLine1") or raw.get("address_line1")
        elif value is None and key == "line2":
            value = raw.get("addressLine2") or raw.get("address_line2")
        elif value is None and key == "postal_code":
            value = raw.get("postalCode") or raw.get("postal_code")
        elif value is None and "_" in key:
            value = raw.get(camel) if camel != key else None
        if value is not None and str(value).strip():
            out[key] = str(value).strip()[:200]
    return out


def _material_diff(
    before: dict, after: dict, *, mls_before: str, mls_after: str
) -> list[str]:
    changed: list[str] = []
    keys = sorted(set(before) | set(after))
    for key in keys:
        if (before.get(key) or "") != (after.get(key) or ""):
            changed.append(key)
    if (mls_before or "") != (mls_after or ""):
        changed.append("mls_number")
    return changed


def serialize_property_history(tx: Transaction) -> list[dict[str, Any]]:
    rows = TransactionPropertySnapshot.objects.filter(transaction=tx).order_by(
        "-recorded_at", "-pk"
    )[:25]
    return [
        {
            "publicId": str(row.public_id),
            "snapshot": row.snapshot or {},
            "mlsNumber": row.mls_number or "",
            "recordedAt": row.recorded_at.isoformat() if row.recorded_at else None,
            "changeSummary": row.change_summary or [],
        }
        for row in rows
    ]


@transaction.atomic
def save_property(
    *,
    actor: User,
    public_id: UUID,
    expected_version: str,
    payload: dict[str, Any],
) -> Transaction:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    before_snap = dict(tx.property_snapshot or {})
    before_mls = tx.mls_number or ""
    property_raw = payload.get("property")
    after_snap = _normalize_snapshot(
        property_raw if isinstance(property_raw, dict) else payload
    )
    after_mls = str(
        payload.get("mlsNumber") or payload.get("mls_number") or ""
    ).strip()[:64]
    changed = _material_diff(
        before_snap, after_snap, mls_before=before_mls, mls_after=after_mls
    )
    if not changed:
        return tx

    tx.property_snapshot = after_snap
    tx.mls_number = after_mls
    tx.save(update_fields=["property_snapshot", "mls_number", "updated_at"])
    TransactionPropertySnapshot.objects.create(
        transaction=tx,
        snapshot=after_snap,
        mls_number=after_mls,
        recorded_by=actor,
        change_summary=changed,
    )
    touch_transaction(tx)
    tx.refresh_from_db(fields=["updated_at", "property_snapshot", "mls_number"])

    log_on_commit(
        action="transaction.updated",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        metadata={
            "section": "property",
            "change": "property_updated",
            "fields": changed,
        },
    )
    return tx


__all__ = ["save_property", "serialize_property_history"]
