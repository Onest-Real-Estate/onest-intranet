"""Version-bound document review comments with visibility filtering."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.service import AuditTarget, actor_from_user, log_on_commit
from apps.transactions.concurrency import (
    can_view_broker_notes,
    require_writable_transaction,
    touch_transaction,
)
from apps.transactions.models import (
    Transaction,
    TransactionDocumentReviewComment,
    TransactionDocumentVersion,
)
from apps.transactions.taxonomy import (
    DOCUMENT_REVIEW_RESOLUTION_CODES,
    NOTE_VISIBILITY_CODES,
    DocumentReviewResolution,
    NoteVisibility,
)
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


def comments_queryset_for_reader(
    user: User, version: TransactionDocumentVersion
) -> models.QuerySet[TransactionDocumentReviewComment]:
    qs = TransactionDocumentReviewComment.objects.filter(
        version=version, ended_at__isnull=True
    )
    if getattr(user, "is_superuser", False):
        return qs
    visibility = Q(visibility=NoteVisibility.TEAM)
    if can_view_broker_notes(user):
        visibility |= Q(visibility=NoteVisibility.BROKER_COMPLIANCE)
    visibility |= Q(visibility=NoteVisibility.PRIVATE_AUTHOR, author=user)
    return qs.filter(visibility)


def serialize_comments_for_reader(
    user: User, version: TransactionDocumentVersion
) -> list[dict[str, Any]]:
    rows = (
        comments_queryset_for_reader(user, version)
        .select_related("author", "resolved_by")
        .order_by("-created_at", "-pk")
    )
    return [
        {
            "publicId": str(row.public_id),
            "body": row.body,
            "visibility": row.visibility,
            "visibilityLabel": row.visibility_label,
            "resolutionState": row.resolution_state,
            "resolutionLabel": row.resolution_label,
            "author": {
                "id": str(row.author.pk),
                "displayName": (
                    row.author.preferred_display_name()
                    if hasattr(row.author, "preferred_display_name")
                    else str(row.author)
                ),
            },
            "resolvedAt": row.resolved_at.isoformat() if row.resolved_at else None,
            "resolvedBy": {
                "id": str(row.resolved_by.pk),
                "displayName": (
                    row.resolved_by.preferred_display_name()
                    if hasattr(row.resolved_by, "preferred_display_name")
                    else str(row.resolved_by)
                ),
            }
            if row.resolved_by is not None
            else None,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
            "mine": row.author.pk == getattr(user, "pk", None),
        }
        for row in rows
    ]


def _parse_comment(raw: dict[str, Any]) -> dict[str, Any]:
    body = str(raw.get("body") or "").strip()
    if not body:
        raise ValidationError({"body": ["A comment body is required."]})
    if len(body) > 8000:
        raise ValidationError({"body": ["Comments are limited to 8000 characters."]})
    visibility = str(raw.get("visibility") or NoteVisibility.TEAM).strip()
    if visibility not in NOTE_VISIBILITY_CODES:
        raise ValidationError({"visibility": ["Unknown note visibility."]})
    return {"body": body, "visibility": visibility}


@transaction.atomic
def save_review_comment(
    *,
    actor: User,
    public_id: UUID,
    version_public_id: UUID,
    expected_version: str,
    payload: dict[str, Any],
) -> TransactionDocumentReviewComment:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    version = (
        TransactionDocumentVersion.objects.select_related("document")
        .filter(
            public_id=version_public_id,
            document__transaction=tx,
            document__ended_at__isnull=True,
            is_active=True,
        )
        .first()
    )
    if version is None:
        raise ValidationError({"version": ["No version matches that id."]})
    fields = _parse_comment(payload)
    if fields[
        "visibility"
    ] == NoteVisibility.BROKER_COMPLIANCE and not can_view_broker_notes(actor):
        raise ValidationError(
            {"visibility": ["You cannot post broker/compliance comments."]}
        )
    row = TransactionDocumentReviewComment(
        version=version,
        body=fields["body"],
        visibility=fields["visibility"],
        author=actor,
        resolution_state=DocumentReviewResolution.OPEN,
    )
    row.full_clean()
    row.save()
    touch_transaction(tx)
    log_on_commit(
        "transaction.document_review_commented",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        after={
            "comment_id": str(row.public_id),
            "version_id": str(version.public_id),
            "visibility": row.visibility,
        },
    )
    return row


@transaction.atomic
def resolve_review_comment(
    *,
    actor: User,
    public_id: UUID,
    comment_public_id: UUID,
    expected_version: str,
    payload: dict[str, Any] | None = None,
) -> TransactionDocumentReviewComment:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    raw = payload or {}
    state = str(
        raw.get("resolutionState")
        or raw.get("resolution_state")
        or DocumentReviewResolution.RESOLVED
    ).strip()
    if state not in DOCUMENT_REVIEW_RESOLUTION_CODES:
        raise ValidationError({"resolutionState": ["Unknown resolution state."]})

    row = (
        TransactionDocumentReviewComment.objects.select_for_update(of=("self",))
        .select_related("version", "version__document")
        .filter(
            public_id=comment_public_id,
            version__document__transaction=tx,
            ended_at__isnull=True,
        )
        .first()
    )
    if row is None:
        raise ValidationError({"comment": ["No comment matches that id."]})

    row.resolution_state = state
    if state == DocumentReviewResolution.RESOLVED:
        row.resolved_at = timezone.now()
        row.resolved_by = actor
    else:
        row.resolved_at = None
        row.resolved_by = None
    row.save(
        update_fields=[
            "resolution_state",
            "resolved_at",
            "resolved_by",
            "updated_at",
        ]
    )
    touch_transaction(tx)
    log_on_commit(
        "transaction.document_review_resolved",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        after={
            "comment_id": str(row.public_id),
            "resolution_state": row.resolution_state,
        },
    )
    return row


@transaction.atomic
def end_review_comment(
    *,
    actor: User,
    public_id: UUID,
    comment_public_id: UUID,
    expected_version: str,
) -> TransactionDocumentReviewComment:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    row = (
        TransactionDocumentReviewComment.objects.select_for_update(of=("self",))
        .select_related("version", "version__document")
        .filter(
            public_id=comment_public_id,
            version__document__transaction=tx,
            ended_at__isnull=True,
        )
        .first()
    )
    if row is None:
        raise ValidationError({"comment": ["No comment matches that id."]})
    if row.author.pk != actor.pk and not getattr(actor, "is_superuser", False):
        raise ValidationError({"comment": ["Only the author can remove this comment."]})
    row.ended_at = timezone.now()
    row.save(update_fields=["ended_at", "updated_at"])
    touch_transaction(tx)
    return row


__all__ = [
    "comments_queryset_for_reader",
    "end_review_comment",
    "resolve_review_comment",
    "save_review_comment",
    "serialize_comments_for_reader",
]
