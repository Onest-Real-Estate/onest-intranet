"""Transaction create, assignment, and presentation services.

Lifecycle moves live in :mod:`apps.transactions.lifecycle`. This module owns
draft creation, assignment mutations, and camelCase serialization with
field-level projection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
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
from apps.transactions.lifecycle import AUDIT_FIELDS
from apps.transactions.models import Transaction, TransactionAssignment
from apps.transactions.money import quantize_money
from apps.transactions.permissions import (
    MANAGE_TRANSACTIONS,
    VIEW_TRANSACTION_CLIENTS,
    VIEW_TRANSACTION_FINANCIALS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.taxonomy import (
    ASSIGNMENT_ROLE_CODES,
    REPRESENTATION_CODES,
    SINGLETON_ASSIGNMENT_ROLES,
    TYPE_CODES,
    AssignmentRole,
    TransactionStatus,
)
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)

logger = logging.getLogger("apps.transactions")


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


@dataclass(frozen=True)
class ActorContext:
    """Who is acting, and what they hold."""

    user: Any
    permissions: frozenset[str]

    def holds(self, *codenames: str) -> bool:
        if getattr(self.user, "is_superuser", False):
            return True
        return any(code in self.permissions for code in codenames)


def _require(actor: ActorContext, *codenames: str) -> None:
    if not actor.holds(*codenames):
        raise PermissionDenied("You do not have permission to change this transaction.")


def next_reference(pk: int) -> str:
    return f"TXN-{pk:06d}"


def scoped_transaction_queryset(user, *, access=None):
    """Transactions visible to ``user`` under effective org/assignment scope."""
    if access is None:
        access = get_effective_access(user)
    return Transaction.objects.for_reader(user, access=access)


def _money_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return quantize_money(value)


def _normalize_property_snapshot(raw: dict | None) -> dict:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError({"property_snapshot": ["Must be an object."]})
    allowed = (
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
    return {k: str(raw[k])[:200] for k in allowed if k in raw and raw[k] is not None}


def _normalize_client_snapshots(raw: list | None) -> list:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValidationError({"client_snapshots": ["Must be a list."]})
    out: list[dict] = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "name": str(item.get("name", ""))[:120],
                "role": str(item.get("role", ""))[:40],
                "email": str(item.get("email", ""))[:120],
                "phone": str(item.get("phone", ""))[:40],
            }
        )
    return out


@transaction.atomic
def create_draft(
    *,
    actor: ActorContext,
    office,
    transaction_type: str,
    representation_type: str,
    primary_agent=None,
    coordinator=None,
    property_snapshot: dict | None = None,
    property_external_ref: str = "",
    mls_number: str = "",
    client_snapshots: list | None = None,
    client_external_refs: list | None = None,
    list_price=None,
    contract_price=None,
    acceptance_date=None,
    closing_date=None,
    lender_ref: str = "",
    title_ref: str = "",
    referral_ref: str = "",
) -> Transaction:
    """Create a Draft transaction and optional primary/coordinator assignments."""
    _require(actor, MANAGE_TRANSACTIONS)

    if transaction_type not in TYPE_CODES:
        raise ValidationError({"transaction_type": ["Unknown transaction type."]})
    if representation_type not in REPRESENTATION_CODES:
        raise ValidationError({"representation_type": ["Unknown representation type."]})
    if office is None:
        raise ValidationError({"office": ["An owning office is required."]})

    tx = Transaction(
        transaction_type=transaction_type,
        representation_type=representation_type,
        office=office,
        primary_agent=primary_agent,
        coordinator=coordinator,
        property_snapshot=_normalize_property_snapshot(property_snapshot),
        property_external_ref=(property_external_ref or "")[:64],
        mls_number=(mls_number or "")[:64],
        client_snapshots=_normalize_client_snapshots(client_snapshots),
        client_external_refs=[str(r)[:64] for r in (client_external_refs or []) if r][
            :20
        ],
        list_price=_money_or_none(list_price),
        contract_price=_money_or_none(contract_price),
        acceptance_date=acceptance_date,
        closing_date=closing_date,
        lender_ref=(lender_ref or "")[:128],
        title_ref=(title_ref or "")[:128],
        referral_ref=(referral_ref or "")[:128],
        status=TransactionStatus.DRAFT,
        created_by=actor.user,
    )
    tx.save()
    tx.reference = next_reference(tx.pk)
    tx.save(update_fields=["reference", "updated_at"])

    if primary_agent is not None:
        upsert_assignment(
            actor=actor,
            tx=tx,
            user=primary_agent,
            role=AssignmentRole.PRIMARY_AGENT,
            _skip_manage_check=True,
        )
    if coordinator is not None:
        upsert_assignment(
            actor=actor,
            tx=tx,
            user=coordinator,
            role=AssignmentRole.COORDINATOR,
            _skip_manage_check=True,
        )

    log_on_commit(
        action="transaction.created",
        actor=actor_from_user(actor.user),
        target=_audit_target(tx),
        after=snapshot_model(tx, fields=AUDIT_FIELDS),
        metadata={
            "transaction_type": transaction_type,
            "representation_type": representation_type,
        },
    )
    publish_event(
        "transaction.created",
        actor_id=str(actor.user.pk),
        subject=str(tx.public_id),
        organization_id=office.stable_key,
        payload={
            "transaction_id": str(tx.public_id),
            "office_id": office.stable_key,
            "transaction_type": transaction_type,
            "actor_id": str(actor.user.pk),
        },
    )
    return tx


@transaction.atomic
def upsert_assignment(
    *,
    actor: ActorContext,
    tx: Transaction,
    user,
    role: str,
    _skip_manage_check: bool = False,
) -> TransactionAssignment:
    """Activate an assignment role for ``user`` on ``tx``.

    Ending a prior active singleton role (primary / coordinator) and mirroring
    the convenience FKs keeps query scope and the assignment table aligned.
    """
    if not _skip_manage_check:
        _require(actor, MANAGE_TRANSACTIONS)

    if role not in ASSIGNMENT_ROLE_CODES:
        raise ValidationError({"role": ["Unknown assignment role."]})
    if user is None:
        raise ValidationError({"user": ["A user is required."]})

    locked = (
        Transaction.objects.select_for_update(of=("self",)).filter(pk=tx.pk).first()
    )
    if locked is None:
        raise ValidationError("This transaction no longer exists.")

    existing = (
        TransactionAssignment.objects.select_for_update(of=("self",))
        .filter(transaction=locked, user=user, role=role, ended_at__isnull=True)
        .first()
    )
    if existing is not None:
        return existing

    if role in SINGLETON_ASSIGNMENT_ROLES:
        prior = (
            TransactionAssignment.objects.select_for_update(of=("self",))
            .filter(transaction=locked, role=role, ended_at__isnull=True)
            .exclude(user=user)
        )
        moment = timezone.now()
        for row in prior:
            row.ended_at = moment
            row.save(update_fields=["ended_at"])

    assignment = TransactionAssignment.objects.create(
        transaction=locked,
        user=user,
        role=role,
        assigned_by=actor.user,
    )

    fk_updates: list[str] = []
    if role == AssignmentRole.PRIMARY_AGENT:
        locked.primary_agent = user
        fk_updates.append("primary_agent")
    elif role == AssignmentRole.COORDINATOR:
        locked.coordinator = user
        fk_updates.append("coordinator")
    if fk_updates:
        fk_updates.append("updated_at")
        locked.save(update_fields=fk_updates)

    log_on_commit(
        action="transaction.assignment_changed",
        actor=actor_from_user(actor.user),
        target=_audit_target(locked),
        metadata={
            "role": role,
            "user_id": str(user.pk),
            "change": "assigned",
        },
    )
    publish_event(
        "transaction.assignment_changed",
        actor_id=str(actor.user.pk),
        subject=str(locked.public_id),
        organization_id=locked.office.stable_key if locked.office_pk else "",
        payload={
            "transaction_id": str(locked.public_id),
            "office_id": locked.office.stable_key if locked.office_pk else "",
            "role": role,
            "user_id": str(user.pk),
            "change": "assigned",
            "actor_id": str(actor.user.pk),
        },
    )
    return assignment


@transaction.atomic
def end_assignment(
    *,
    actor: ActorContext,
    tx: Transaction,
    user,
    role: str,
) -> TransactionAssignment | None:
    """End an active assignment; clears mirrored FKs when singleton roles end."""
    _require(actor, MANAGE_TRANSACTIONS)

    locked = (
        Transaction.objects.select_for_update(of=("self",)).filter(pk=tx.pk).first()
    )
    if locked is None:
        raise ValidationError("This transaction no longer exists.")

    row = (
        TransactionAssignment.objects.select_for_update(of=("self",))
        .filter(transaction=locked, user=user, role=role, ended_at__isnull=True)
        .first()
    )
    if row is None:
        return None

    row.ended_at = timezone.now()
    row.save(update_fields=["ended_at"])

    fk_updates: list[str] = []
    if role == AssignmentRole.PRIMARY_AGENT and locked.primary_agent_pk == user.pk:
        locked.primary_agent = None
        fk_updates.append("primary_agent")
    elif role == AssignmentRole.COORDINATOR and locked.coordinator_pk == user.pk:
        locked.coordinator = None
        fk_updates.append("coordinator")
    if fk_updates:
        fk_updates.append("updated_at")
        locked.save(update_fields=fk_updates)

    log_on_commit(
        action="transaction.assignment_changed",
        actor=actor_from_user(actor.user),
        target=_audit_target(locked),
        metadata={
            "role": role,
            "user_id": str(user.pk),
            "change": "ended",
        },
    )
    publish_event(
        "transaction.assignment_changed",
        actor_id=str(actor.user.pk),
        subject=str(locked.public_id),
        organization_id=locked.office.stable_key if locked.office_pk else "",
        payload={
            "transaction_id": str(locked.public_id),
            "office_id": locked.office.stable_key if locked.office_pk else "",
            "role": role,
            "user_id": str(user.pk),
            "change": "ended",
            "actor_id": str(actor.user.pk),
        },
    )
    return row


def _user_summary(user) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": str(user.pk),
        "displayName": user.preferred_display_name()
        if hasattr(user, "preferred_display_name")
        else str(user),
        "email": getattr(user, "email", "") or "",
    }


def _property_summary(snapshot: dict) -> dict[str, Any]:
    if not snapshot:
        return {}
    line1 = snapshot.get("line1") or snapshot.get("address_line1") or ""
    city = snapshot.get("city") or ""
    state = snapshot.get("state") or ""
    return {
        "line1": line1,
        "city": city,
        "state": state,
        "postalCode": snapshot.get("postal_code") or "",
    }


def serialize_transaction(user, tx: Transaction) -> dict[str, Any]:
    """CamelCase presentation payload with sensitive fields omitted without grants."""
    can_view = (
        getattr(user, "is_superuser", False)
        or has_effective_permission(user, VIEW_TRANSACTIONS)
        or tx.primary_agent_pk == getattr(user, "pk", None)
        or tx.coordinator_pk == getattr(user, "pk", None)
        or TransactionAssignment.objects.filter(
            transaction=tx, user=user, ended_at__isnull=True
        ).exists()
    )
    if not can_view and not scoped_transaction_queryset(user).filter(pk=tx.pk).exists():
        raise PermissionDenied("You do not have permission to view this transaction.")

    show_financials = getattr(user, "is_superuser", False) or has_effective_permission(
        user, VIEW_TRANSACTION_FINANCIALS
    )
    show_clients = getattr(user, "is_superuser", False) or has_effective_permission(
        user, VIEW_TRANSACTION_CLIENTS
    )

    assignments = [
        {
            "publicId": str(row.public_id),
            "role": row.role,
            "roleLabel": row.role_label,
            "user": _user_summary(row.user),
            "assignedAt": row.assigned_at.isoformat() if row.assigned_at else None,
            "endedAt": row.ended_at.isoformat() if row.ended_at else None,
        }
        for row in TransactionAssignment.objects.filter(
            transaction=tx, ended_at__isnull=True
        )
        .select_related("user")
        .order_by("role", "pk")
    ]

    payload: dict[str, Any] = {
        "publicId": str(tx.public_id),
        "reference": tx.reference,
        "transactionType": tx.transaction_type,
        "representationType": tx.representation_type,
        "status": tx.status,
        "statusLabel": tx.status_label,
        "office": {
            "stableKey": tx.office.stable_key,
            "name": tx.office.name,
        }
        if tx.office_pk
        else None,
        "primaryAgent": _user_summary(tx.primary_agent),
        "coordinator": _user_summary(tx.coordinator),
        "property": _property_summary(tx.property_snapshot or {}),
        "mlsNumber": tx.mls_number or "",
        "acceptanceDate": tx.acceptance_date.isoformat()
        if tx.acceptance_date
        else None,
        "closingDate": tx.closing_date.isoformat() if tx.closing_date else None,
        "lenderRef": tx.lender_ref or "",
        "titleRef": tx.title_ref or "",
        "referralRef": tx.referral_ref or "",
        "heldFromStatus": tx.held_from_status or "",
        "complianceApprovedAt": (
            tx.compliance_approved_at.isoformat() if tx.compliance_approved_at else None
        ),
        "closedAt": tx.closed_at.isoformat() if tx.closed_at else None,
        "archivedAt": tx.archived_at.isoformat() if tx.archived_at else None,
        "createdAt": tx.created_at.isoformat() if tx.created_at else None,
        "updatedAt": tx.updated_at.isoformat() if tx.updated_at else None,
        "assignments": assignments,
    }

    if show_financials:
        payload["listPrice"] = str(tx.list_price) if tx.list_price is not None else None
        payload["contractPrice"] = (
            str(tx.contract_price) if tx.contract_price is not None else None
        )

    if show_clients:
        payload["clients"] = tx.client_snapshots or []
        payload["clientExternalRefs"] = tx.client_external_refs or []

    return payload


__all__ = [
    "ActorContext",
    "create_draft",
    "end_assignment",
    "next_reference",
    "scoped_transaction_queryset",
    "serialize_transaction",
    "upsert_assignment",
]
