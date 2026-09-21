"""Central transaction status machine.

Every status change goes through :func:`transition`. Product forms, serializers,
and Django admin must not assign ``status`` directly — the model refuses
unguarded writes.

Concurrency uses ``select_for_update(of=("self",))`` plus ``expected_status``.
Idempotent retries of the same target are no-ops (no second audit or event).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.events import publish as publish_event
from apps.audit.service import (
    AuditTarget,
    actor_from_user,
    log_on_commit,
    snapshot_model,
)
from apps.transactions.models import Transaction, TransactionAssignment
from apps.transactions.taxonomy import (
    REQUIRED_FIELDS,
    STATUS_ENTERED_AT,
    TransactionStatus,
    Transition,
    find_transition,
    transitions_from,
)

logger = logging.getLogger("apps.transactions")

_STATUS_WRITE_ALLOWED: ContextVar[bool] = ContextVar(
    "transaction_status_write_allowed", default=False
)

AUDIT_FIELDS = [
    "reference",
    "transaction_type",
    "representation_type",
    "status",
    "office",
    "primary_agent",
    "coordinator",
    "acceptance_date",
    "closing_date",
    "mls_number",
    "compliance_approved_at",
]


class TransitionError(ValidationError):
    """The requested move is not legal from the transaction's current state."""


class ConcurrentUpdate(ValidationError):
    """Somebody else moved the transaction since the caller last read it."""


@contextmanager
def allow_status_write():
    """Permit ``Transaction.status`` mutation inside the lifecycle only."""
    token = _STATUS_WRITE_ALLOWED.set(True)
    try:
        yield
    finally:
        _STATUS_WRITE_ALLOWED.reset(token)


def status_write_allowed() -> bool:
    return bool(_STATUS_WRITE_ALLOWED.get())


def _actor_is_assignee(tx: Transaction, user: Any) -> bool:
    user_pk = getattr(user, "pk", None)
    if user_pk is None:
        return False
    if tx.primary_agent_pk == user_pk or tx.coordinator_pk == user_pk:
        return True
    return TransactionAssignment.objects.filter(
        transaction_id=tx.pk, user_id=user_pk, ended_at__isnull=True
    ).exists()


def _audit_target(tx: Transaction) -> AuditTarget:
    """Audit target without Decimal money fields in the snapshot."""
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


def available_transitions(
    tx: Transaction, *, permissions: frozenset[str], user
) -> list[Transition]:
    """Legal moves this actor could make right now."""
    is_assignee = _actor_is_assignee(tx, user)
    is_super = getattr(user, "is_superuser", False)
    allowed: list[Transition] = []
    for candidate in transitions_from(tx.status):
        holds_perm = is_super or any(p in permissions for p in candidate.permissions)
        if holds_perm or (candidate.by_assignee and is_assignee):
            if candidate.resumes and tx.held_from_status != candidate.target:
                continue
            allowed.append(candidate)
    return allowed


def _require_fields(tx: Transaction, target: str) -> None:
    required = REQUIRED_FIELDS.get(target, ())
    errors: dict[str, list[str]] = {}
    for field in required:
        value = getattr(tx, field, None)
        if field == "property_snapshot":
            if not isinstance(value, dict) or not (
                value.get("line1") or value.get("address_line1")
            ):
                errors[field] = ["A property street address is required."]
            continue
        if field == "primary_agent" and tx.primary_agent_pk is None:
            errors[field] = ["A primary agent is required."]
            continue
        if field == "office" and tx.office_pk is None:
            errors[field] = ["An owning office is required."]
            continue
        if value is None or value == "" or value == [] or value == {}:
            errors[field] = [f"{field.replace('_', ' ').capitalize()} is required."]
    if errors:
        raise ValidationError(errors)


def _stamp_entry(tx: Transaction, target: str, *, moment, actor) -> list[str]:
    """Apply timestamp and side-effect fields for entering ``target``."""
    update_fields: list[str] = ["status", "updated_at"]
    stamp = STATUS_ENTERED_AT.get(target)
    if stamp and getattr(tx, stamp) is None:
        setattr(tx, stamp, moment)
        update_fields.append(stamp)

    if target == TransactionStatus.READY_TO_CLOSE and tx.compliance_approved_at is None:
        tx.compliance_approved_at = moment
        update_fields.append("compliance_approved_at")

    if target == TransactionStatus.ON_HOLD:
        # held_from_status set by caller before stamp
        if tx.on_hold_at is None:
            tx.on_hold_at = moment
            if "on_hold_at" not in update_fields:
                update_fields.append("on_hold_at")
        update_fields.append("held_from_status")

    if target != TransactionStatus.ON_HOLD and tx.held_from_status:
        # Leaving any non-hold status that isn't the hold itself clears hold memory
        # when resuming; also clear on_hold_at stays as historical first-hold time.
        pass

    if target == TransactionStatus.ARCHIVED:
        tx.archived_by = actor
        update_fields.append("archived_by")

    return update_fields


@transaction.atomic
def transition(
    *,
    user,
    permissions: frozenset[str],
    tx: Transaction,
    to_status: str,
    expected_status: str | None = None,
    note: str = "",
    archive_reason: str = "",
) -> Transaction:
    """Move a transaction, or explain why it cannot move."""
    locked = (
        Transaction.objects.select_for_update(of=("self",)).filter(pk=tx.pk).first()
    )
    if locked is None:
        raise ValidationError("This transaction no longer exists.")

    if expected_status is not None and locked.status != expected_status:
        raise ConcurrentUpdate(
            "Somebody else updated this transaction while you were working. "
            "Refresh and try again."
        )

    # Idempotent same-target retry.
    if locked.status == to_status:
        return locked

    move = find_transition(locked.status, to_status)
    if move is None:
        raise TransitionError(f"Cannot move from {locked.status!r} to {to_status!r}.")

    is_super = getattr(user, "is_superuser", False)
    holds_perm = is_super or any(p in permissions for p in move.permissions)
    if not holds_perm and not (move.by_assignee and _actor_is_assignee(locked, user)):
        raise PermissionDenied(
            "You do not have permission to transition this transaction."
        )

    if move.requires_note and not (note or "").strip():
        raise ValidationError({"note": ["A note is required for this transition."]})

    if move.resumes and locked.held_from_status != to_status:
        raise TransitionError(
            f"On Hold can only resume to {locked.held_from_status!r}."
        )

    if move.holds:
        locked.held_from_status = locked.status

    # Preconditions before mutating.
    _require_fields(locked, to_status)
    if to_status == TransactionStatus.CLOSED and locked.compliance_approved_at is None:
        raise ValidationError(
            {
                "compliance_approved_at": [
                    "Closing requires an approved compliance clearance."
                ]
            }
        )
    if (
        to_status == TransactionStatus.ARCHIVED
        and locked.status != TransactionStatus.CLOSED
    ):
        raise TransitionError("Only a closed transaction can be archived.")

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    moment = timezone.now()
    previous = locked.status
    locked.status = to_status

    update_fields = _stamp_entry(locked, to_status, moment=moment, actor=user)

    if move.resumes:
        locked.held_from_status = ""
        if "held_from_status" not in update_fields:
            update_fields.append("held_from_status")

    if move.archives:
        locked.archive_reason = (archive_reason or note or "").strip()[:255]
        update_fields.append("archive_reason")

    with allow_status_write():
        locked.save(update_fields=update_fields)

    after = snapshot_model(locked, fields=AUDIT_FIELDS)
    action = "transaction.archived" if move.archives else "transaction.status_changed"
    log_on_commit(
        action=action,
        actor=actor_from_user(user),
        target=_audit_target(locked),
        before=before,
        after=after,
        metadata={
            "from": previous,
            "to": to_status,
            "note": (note or "").strip()[:500],
        },
    )

    event_name = (
        "transaction.archived" if move.archives else "transaction.status_changed"
    )
    publish_event(
        event_name,
        actor_id=str(user.pk),
        subject=str(locked.public_id),
        organization_id=locked.office.stable_key if locked.office_pk else "",
        payload={
            "transaction_id": str(locked.public_id),
            "office_id": locked.office.stable_key if locked.office_pk else "",
            "from": previous,
            "to": to_status,
            "actor_id": str(user.pk),
        },
    )
    return locked


__all__ = [
    "AUDIT_FIELDS",
    "ConcurrentUpdate",
    "TransitionError",
    "allow_status_write",
    "available_transitions",
    "status_write_allowed",
    "transition",
]
