"""Structured transaction party CRUD with primary-role uniqueness and snapshots."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.service import (
    AuditTarget,
    actor_from_user,
    log_on_commit,
)
from apps.transactions.concurrency import (
    require_writable_transaction,
    touch_transaction,
)
from apps.transactions.models import Transaction, TransactionParty
from apps.transactions.permissions import VIEW_TRANSACTION_CLIENTS
from apps.transactions.taxonomy import (
    PARTY_KIND_CODES,
    PARTY_ROLE_CODES,
    PRIMARY_PARTY_ROLES,
    REPRESENTATION_CODES,
    PartyKind,
    PartyRole,
    RepresentationType,
)
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

_REP_TO_PARTY_ROLE: dict[str, str] = {
    RepresentationType.BUYER: PartyRole.BUYER,
    RepresentationType.SELLER: PartyRole.SELLER,
    RepresentationType.TENANT: PartyRole.TENANT,
    RepresentationType.LANDLORD: PartyRole.LANDLORD,
    RepresentationType.DUAL: PartyRole.BUYER,
}

_ROLE_ALIASES: dict[str, str] = {
    "buyer": PartyRole.BUYER,
    "buyers": PartyRole.BUYER,
    "buyer_agency": PartyRole.BUYER,
    "buyer agency": PartyRole.BUYER,
    "seller": PartyRole.SELLER,
    "sellers": PartyRole.SELLER,
    "seller_agency": PartyRole.SELLER,
    "seller agency": PartyRole.SELLER,
    "tenant": PartyRole.TENANT,
    "tenants": PartyRole.TENANT,
    "tenant_agency": PartyRole.TENANT,
    "tenant agency": PartyRole.TENANT,
    "landlord": PartyRole.LANDLORD,
    "landlords": PartyRole.LANDLORD,
    "landlord_agency": PartyRole.LANDLORD,
    "landlord agency": PartyRole.LANDLORD,
}


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


def _can_see_contacts(user: User) -> bool:
    return getattr(user, "is_superuser", False) or has_effective_permission(
        user, VIEW_TRANSACTION_CLIENTS
    )


def _party_snapshot(data: dict[str, Any]) -> dict[str, str]:
    return {
        "display_name": str(data.get("display_name") or "")[:255],
        "organization_name": str(data.get("organization_name") or "")[:255],
        "kind": str(data.get("kind") or PartyKind.PERSON)[:20],
        "role": str(data.get("role") or "")[:32],
        "representation": str(data.get("representation") or "")[:20],
        "is_primary": "1" if data.get("is_primary") else "0",
    }


def _serialize_party(user: User, party: TransactionParty) -> dict[str, Any]:
    row: dict[str, Any] = {
        "publicId": str(party.public_id),
        "role": party.role,
        "roleLabel": party.role_label,
        "kind": party.kind,
        "displayName": party.display_name,
        "organizationName": party.organization_name or "",
        "representation": party.representation or "",
        "isPrimary": party.is_primary,
        "validFrom": party.valid_from.isoformat() if party.valid_from else None,
        "validUntil": party.valid_until.isoformat() if party.valid_until else None,
        "snapshot": party.snapshot or {},
    }
    if _can_see_contacts(user):
        row["email"] = party.email or ""
        row["phone"] = party.phone or ""
    return row


def serialize_parties(user: User, tx: Transaction) -> list[dict[str, Any]]:
    rows = TransactionParty.objects.filter(
        transaction=tx, ended_at__isnull=True
    ).order_by("role", "-is_primary", "display_name", "pk")
    return [_serialize_party(user, row) for row in rows]


def _party_role_for_client(client: dict[str, Any], representation_type: str) -> str:
    raw = str(client.get("role") or "").strip().casefold().replace("-", "_")
    if raw in PARTY_ROLE_CODES:
        return raw
    aliased = _ROLE_ALIASES.get(raw) or _ROLE_ALIASES.get(raw.replace("_", " "))
    if aliased:
        return aliased
    return _REP_TO_PARTY_ROLE.get(representation_type, PartyRole.BUYER)


def ensure_parties_from_client_snapshots(
    *, actor: User, tx: Transaction
) -> list[TransactionParty]:
    """Materialize create-form client snapshots as structured parties.

    Idempotent: skips when live parties already exist, or when a matching
    email/name for the role is already on the deal. Safe to call from prepare,
    draft save, and workspace load (one-shot backfill for older deals).
    """
    clients = [
        item
        for item in (tx.client_snapshots or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    if not clients:
        return []

    if TransactionParty.objects.filter(transaction=tx, ended_at__isnull=True).exists():
        return []

    created: list[TransactionParty] = []
    primary_claimed: set[str] = set()
    for client in clients:
        display_name = str(client.get("name") or "").strip()[:255]
        role = _party_role_for_client(client, tx.representation_type)
        email = str(client.get("email") or "").strip()[:254]
        phone = str(client.get("phone") or "").strip()[:40]
        is_primary = role in PRIMARY_PARTY_ROLES and role not in primary_claimed
        if is_primary:
            primary_claimed.add(role)

        fields = {
            "role": role,
            "kind": PartyKind.PERSON,
            "display_name": display_name,
            "organization_name": "",
            "email": email,
            "phone": phone,
            "representation": tx.representation_type or "",
            "is_primary": is_primary,
        }
        party = TransactionParty(
            transaction=tx,
            created_by=actor,
            snapshot=_party_snapshot(fields),
            **fields,
        )
        party.save()
        created.append(party)

    if created:
        touch_transaction(tx)
        log_on_commit(
            action="transaction.updated",
            actor=actor_from_user(actor),
            target=_audit_target(tx),
            metadata={
                "section": "parties",
                "change": "parties_seeded_from_clients",
                "count": len(created),
                "fields": ["display_name", "email", "phone", "role"],
            },
        )
    return created


def _parse_party_fields(raw: dict[str, Any]) -> dict[str, Any]:
    role = str(raw.get("role") or "").strip()
    if role not in PARTY_ROLE_CODES:
        raise ValidationError({"role": ["Unknown party role."]})
    kind = str(raw.get("kind") or PartyKind.PERSON).strip()
    if kind not in PARTY_KIND_CODES:
        raise ValidationError({"kind": ["Unknown party kind."]})
    display_name = str(raw.get("displayName") or raw.get("display_name") or "").strip()
    if not display_name:
        raise ValidationError({"displayName": ["A display name is required."]})
    representation = str(
        raw.get("representation") or raw.get("representationType") or ""
    ).strip()
    if representation and representation not in REPRESENTATION_CODES:
        raise ValidationError({"representation": ["Unknown representation."]})
    is_primary = bool(raw.get("isPrimary", raw.get("is_primary", False)))
    if role not in PRIMARY_PARTY_ROLES:
        # Co-parties and vendors may still be marked primary within their role;
        # only PRIMARY_PARTY_ROLES enforce uniqueness.
        pass
    return {
        "role": role,
        "kind": kind,
        "display_name": display_name[:255],
        "organization_name": str(
            raw.get("organizationName") or raw.get("organization_name") or ""
        ).strip()[:255],
        "email": str(raw.get("email") or "").strip()[:254],
        "phone": str(raw.get("phone") or "").strip()[:40],
        "representation": representation,
        "is_primary": is_primary,
    }


@transaction.atomic
def save_party(
    *,
    actor: User,
    public_id: UUID,
    expected_version: str,
    payload: dict[str, Any],
    party_public_id: UUID | None = None,
) -> tuple[Transaction, TransactionParty]:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    fields = _parse_party_fields(payload)

    party: TransactionParty | None = None
    if party_public_id is not None:
        party = (
            TransactionParty.objects.select_for_update(of=("self",))
            .filter(
                transaction=tx,
                public_id=party_public_id,
                ended_at__isnull=True,
            )
            .first()
        )
        if party is None:
            raise ValidationError({"party": ["Party not found."]})

    if fields["is_primary"] and fields["role"] in PRIMARY_PARTY_ROLES:
        rivals = TransactionParty.objects.filter(
            transaction=tx,
            role=fields["role"],
            is_primary=True,
            ended_at__isnull=True,
        )
        if party is not None:
            rivals = rivals.exclude(pk=party.pk)
        rivals.update(is_primary=False, updated_at=timezone.now())

    snap = _party_snapshot(fields)
    if party is None:
        party = TransactionParty(transaction=tx, created_by=actor)
    for key, value in fields.items():
        setattr(party, key, value)
    party.snapshot = snap
    party.save()
    touch_transaction(tx)
    tx.refresh_from_db(fields=["updated_at"])

    log_on_commit(
        action="transaction.updated",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        metadata={
            "section": "parties",
            "change": "party_saved",
            "party_role": fields["role"],
            "fields": sorted(snap.keys()),
        },
    )
    return tx, party


@transaction.atomic
def end_party(
    *,
    actor: User,
    public_id: UUID,
    expected_version: str,
    party_public_id: UUID,
) -> Transaction:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    party = (
        TransactionParty.objects.select_for_update(of=("self",))
        .filter(transaction=tx, public_id=party_public_id, ended_at__isnull=True)
        .first()
    )
    if party is None:
        raise ValidationError({"party": ["Party not found."]})
    party.ended_at = timezone.now()
    party.save(update_fields=["ended_at", "updated_at"])
    touch_transaction(tx)
    tx.refresh_from_db(fields=["updated_at"])
    log_on_commit(
        action="transaction.updated",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        metadata={
            "section": "parties",
            "change": "party_ended",
            "party_role": party.role,
            "fields": ["ended_at"],
        },
    )
    return tx


__all__ = [
    "end_party",
    "ensure_parties_from_client_snapshots",
    "save_party",
    "serialize_parties",
]
