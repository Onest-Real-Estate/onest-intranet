"""Transaction notes with visibility filtering — never one unrestricted stream."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.service import AuditTarget, actor_from_user, log_on_commit
from apps.transactions.concurrency import (
    can_view_broker_notes,
    require_writable_transaction,
    touch_transaction,
)
from apps.transactions.models import Transaction, TransactionNote
from apps.transactions.taxonomy import NOTE_VISIBILITY_CODES, NoteVisibility
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


def notes_queryset_for_reader(
    user: User, tx: Transaction
) -> models.QuerySet[TransactionNote]:
    """Notes this reader may see on ``tx`` — applied before fetch."""
    qs = TransactionNote.objects.filter(transaction=tx, ended_at__isnull=True)
    if getattr(user, "is_superuser", False):
        return qs
    visibility = Q(visibility=NoteVisibility.TEAM)
    if can_view_broker_notes(user):
        visibility |= Q(visibility=NoteVisibility.BROKER_COMPLIANCE)
    visibility |= Q(visibility=NoteVisibility.PRIVATE_AUTHOR, author=user)
    return qs.filter(visibility)


def serialize_notes_for_reader(user: User, tx: Transaction) -> list[dict[str, Any]]:
    rows = (
        notes_queryset_for_reader(user, tx)
        .select_related("author")
        .order_by("-created_at", "-pk")
    )
    return [
        {
            "publicId": str(row.public_id),
            "body": row.body,
            "visibility": row.visibility,
            "visibilityLabel": row.visibility_label,
            "author": {
                "id": str(row.author.id),
                "displayName": (
                    row.author.preferred_display_name()
                    if hasattr(row.author, "preferred_display_name")
                    else str(row.author)
                ),
            }
            if row.author.id
            else None,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
            "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
            "mine": row.author.id == getattr(user, "pk", None),
        }
        for row in rows
    ]


def _parse_note(raw: dict[str, Any]) -> dict[str, Any]:
    body = str(raw.get("body") or "").strip()
    if not body:
        raise ValidationError({"body": ["A note body is required."]})
    if len(body) > 8000:
        raise ValidationError({"body": ["Notes are limited to 8000 characters."]})
    visibility = str(raw.get("visibility") or NoteVisibility.TEAM).strip()
    if visibility not in NOTE_VISIBILITY_CODES:
        raise ValidationError({"visibility": ["Unknown note visibility."]})
    return {"body": body, "visibility": visibility}


@transaction.atomic
def save_note(
    *,
    actor: User,
    public_id: UUID,
    expected_version: str,
    payload: dict[str, Any],
    note_public_id: UUID | None = None,
) -> tuple[Transaction, TransactionNote]:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    fields = _parse_note(payload)
    if fields[
        "visibility"
    ] == NoteVisibility.BROKER_COMPLIANCE and not can_view_broker_notes(actor):
        raise PermissionDenied("You cannot create broker / compliance notes.")

    note: TransactionNote | None = None
    if note_public_id is not None:
        note = (
            TransactionNote.objects.select_for_update(of=("self",))
            .filter(transaction=tx, public_id=note_public_id, ended_at__isnull=True)
            .first()
        )
        if note is None:
            raise ValidationError({"note": ["Note not found."]})
        if note.author.id != actor.pk and not can_view_broker_notes(actor):
            raise PermissionDenied("You can only edit your own notes.")

    if note is None:
        note = TransactionNote(transaction=tx, author=actor)
    note.body = fields["body"]
    note.visibility = fields["visibility"]
    note.save()
    touch_transaction(tx)
    tx.refresh_from_db(fields=["updated_at"])
    log_on_commit(
        action="transaction.updated",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        metadata={
            "section": "notes",
            "change": "note_saved",
            "visibility": fields["visibility"],
            "fields": ["body", "visibility"],
        },
    )
    return tx, note


@transaction.atomic
def end_note(
    *,
    actor: User,
    public_id: UUID,
    expected_version: str,
    note_public_id: UUID,
) -> Transaction:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    note = (
        TransactionNote.objects.select_for_update(of=("self",))
        .filter(transaction=tx, public_id=note_public_id, ended_at__isnull=True)
        .first()
    )
    if note is None:
        raise ValidationError({"note": ["Note not found."]})
    if note.author.id != actor.pk and not can_view_broker_notes(actor):
        raise PermissionDenied("You can only remove your own notes.")
    note.ended_at = timezone.now()
    note.save(update_fields=["ended_at", "updated_at"])
    touch_transaction(tx)
    tx.refresh_from_db(fields=["updated_at"])
    log_on_commit(
        action="transaction.updated",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        metadata={
            "section": "notes",
            "change": "note_ended",
            "visibility": note.visibility,
            "fields": ["ended_at"],
        },
    )
    return tx


__all__ = [
    "end_note",
    "notes_queryset_for_reader",
    "save_note",
    "serialize_notes_for_reader",
]
