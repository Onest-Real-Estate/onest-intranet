"""Key date CRUD with soft-supersede history."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.audit.service import AuditTarget, actor_from_user, log_on_commit
from apps.transactions.concurrency import (
    require_writable_transaction,
    touch_transaction,
)
from apps.transactions.models import Transaction, TransactionKeyDate
from apps.transactions.taxonomy import KEY_DATE_TYPE_CODES, KeyDateType
from apps.user.models import User


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


def _parse_occurs_at(raw: Any, tz_name: str) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        value = raw
    else:
        text = str(raw).strip()
        # datetime-local often omits seconds; normalize for parse_datetime.
        if len(text) == 16 and text[10] == "T":
            text = f"{text}:00"
        value = parse_datetime(text)
        if value is None:
            raise ValidationError({"occursAt": ["Enter a valid date and time."]})
    if timezone.is_naive(value):
        if not tz_name:
            raise ValidationError(
                {"timezone": ["A timezone is required for naive datetimes."]}
            )
        try:
            value = timezone.make_aware(value, ZoneInfo(tz_name))
        except ZoneInfoNotFoundError as exc:
            raise ValidationError({"timezone": ["Unknown timezone."]}) from exc
    return value


def serialize_key_dates(tx: Transaction) -> list[dict[str, Any]]:
    rows = TransactionKeyDate.objects.filter(
        transaction=tx, ended_at__isnull=True
    ).order_by("occurs_at", "date_type", "pk")
    return [
        {
            "publicId": str(row.public_id),
            "dateType": row.date_type,
            "dateTypeLabel": row.date_type_label,
            "label": row.label or "",
            "occursAt": row.occurs_at.isoformat() if row.occurs_at else None,
            "timezone": row.timezone or "",
            "source": row.source or "",
            "isRequired": row.is_required,
        }
        for row in rows
    ]


def _parse_fields(raw: dict[str, Any]) -> dict[str, Any]:
    date_type = str(raw.get("dateType") or raw.get("date_type") or "").strip()
    if date_type not in KEY_DATE_TYPE_CODES:
        raise ValidationError({"dateType": ["Unknown key date type."]})
    tz_name = str(raw.get("timezone") or "").strip()
    if tz_name:
        try:
            ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError({"timezone": ["Unknown timezone."]}) from exc
    occurs_raw = raw.get("occursAt", raw.get("occurs_at"))
    occurs_at = _parse_occurs_at(occurs_raw, tz_name)
    return {
        "date_type": date_type,
        "label": str(raw.get("label") or "").strip()[:120],
        "occurs_at": occurs_at,
        "timezone": tz_name[:64],
        "source": str(raw.get("source") or "").strip()[:64],
        "is_required": bool(raw.get("isRequired", raw.get("is_required", False))),
    }


@transaction.atomic
def save_key_date(
    *,
    actor: User,
    public_id: UUID,
    expected_version: str,
    payload: dict[str, Any],
    key_date_public_id: UUID | None = None,
) -> tuple[Transaction, TransactionKeyDate]:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    fields = _parse_fields(payload)

    existing: TransactionKeyDate | None = None
    if key_date_public_id is not None:
        existing = (
            TransactionKeyDate.objects.select_for_update(of=("self",))
            .filter(
                transaction=tx,
                public_id=key_date_public_id,
                ended_at__isnull=True,
            )
            .first()
        )
        if existing is None:
            raise ValidationError({"keyDate": ["Key date not found."]})

    # Soft-supersede: end the previous active row of the same type when replacing.
    if existing is None and fields["date_type"] != KeyDateType.OTHER:
        prior = (
            TransactionKeyDate.objects.select_for_update(of=("self",))
            .filter(
                transaction=tx,
                date_type=fields["date_type"],
                ended_at__isnull=True,
            )
            .first()
        )
        if prior is not None:
            existing = prior

    row = TransactionKeyDate(transaction=tx, created_by=actor)
    for key, value in fields.items():
        setattr(row, key, value)
    row.save()

    if existing is not None and existing.pk != row.pk:
        existing.ended_at = timezone.now()
        existing.superseded_by = row
        existing.save(update_fields=["ended_at", "superseded_by", "updated_at"])

    # Mirror acceptance / closing onto the transaction convenience columns.
    if fields["date_type"] == KeyDateType.ACCEPTANCE and fields["occurs_at"]:
        tx.acceptance_date = timezone.localdate(fields["occurs_at"])
        tx.save(update_fields=["acceptance_date", "updated_at"])
    elif fields["date_type"] == KeyDateType.CLOSING and fields["occurs_at"]:
        tx.closing_date = timezone.localdate(fields["occurs_at"])
        tx.save(update_fields=["closing_date", "updated_at"])
    else:
        touch_transaction(tx)

    tx.refresh_from_db(fields=["updated_at", "acceptance_date", "closing_date"])
    log_on_commit(
        action="transaction.updated",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        metadata={
            "section": "dates",
            "change": "key_date_saved",
            "date_type": fields["date_type"],
            "fields": ["occurs_at", "timezone", "is_required"],
        },
    )
    return tx, row


@transaction.atomic
def end_key_date(
    *,
    actor: User,
    public_id: UUID,
    expected_version: str,
    key_date_public_id: UUID,
) -> Transaction:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    row = (
        TransactionKeyDate.objects.select_for_update(of=("self",))
        .filter(transaction=tx, public_id=key_date_public_id, ended_at__isnull=True)
        .first()
    )
    if row is None:
        raise ValidationError({"keyDate": ["Key date not found."]})
    row.ended_at = timezone.now()
    row.save(update_fields=["ended_at", "updated_at"])
    touch_transaction(tx)
    tx.refresh_from_db(fields=["updated_at"])
    log_on_commit(
        action="transaction.updated",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        metadata={
            "section": "dates",
            "change": "key_date_ended",
            "date_type": row.date_type,
            "fields": ["ended_at"],
        },
    )
    return tx


__all__ = ["end_key_date", "save_key_date", "serialize_key_dates"]
