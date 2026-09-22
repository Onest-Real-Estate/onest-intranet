"""Transaction workspace shell payload and section availability."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied

from apps.audit.activity import project_record_activity
from apps.transactions.concurrency import (
    StaleTransactionVersion,
    can_manage_workspace,
    can_view_broker_notes,
    load_workspace_transaction,
    lock_transaction,
    require_writable_transaction,
    touch_transaction,
    transaction_version,
)
from apps.transactions.key_dates import serialize_key_dates
from apps.transactions.lifecycle import available_transitions
from apps.transactions.models import Transaction
from apps.transactions.notes import serialize_notes_for_reader
from apps.transactions.parties import serialize_parties
from apps.transactions.permissions import (
    CREATE_OWN_TRANSACTIONS,
    MANAGE_TRANSACTIONS,
    TRANSITION_TRANSACTIONS,
    VIEW_OWN_TRANSACTIONS,
    VIEW_TRANSACTION_CLIENTS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.property_data import serialize_property_history
from apps.transactions.services import (
    scoped_transaction_queryset,
    serialize_transaction,
)
from apps.transactions.taxonomy import (
    DEFAULT_WORKSPACE_SECTION,
    LIVE_WORKSPACE_SECTIONS,
    STUB_WORKSPACE_SECTIONS,
    WORKSPACE_SECTION_CODES,
    WORKSPACE_SECTION_LABELS,
    WorkspaceSection,
)
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission


def resolve_section(raw: str | None) -> str:
    value = (raw or "").strip().lower() or DEFAULT_WORKSPACE_SECTION
    if value not in WORKSPACE_SECTION_CODES:
        return DEFAULT_WORKSPACE_SECTION
    return value


def _section_nav(*, can_edit: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code in (
        WorkspaceSection.OVERVIEW,
        WorkspaceSection.PARTIES,
        WorkspaceSection.PROPERTY,
        WorkspaceSection.DATES,
        WorkspaceSection.NOTES,
        WorkspaceSection.ASSIGNMENTS,
        WorkspaceSection.ACTIVITY,
        WorkspaceSection.DOCUMENTS,
        WorkspaceSection.CHECKLIST,
        WorkspaceSection.TASKS,
        WorkspaceSection.SIGNATURES,
        WorkspaceSection.COMMISSION,
        WorkspaceSection.COMPLIANCE,
    ):
        live = code in LIVE_WORKSPACE_SECTIONS
        rows.append(
            {
                "id": code,
                "label": str(WORKSPACE_SECTION_LABELS[code]),
                "live": live,
                "stub": code in STUB_WORKSPACE_SECTIONS,
                "writable": live
                and can_edit
                and code
                not in {
                    WorkspaceSection.OVERVIEW,
                    WorkspaceSection.ACTIVITY,
                },
            }
        )
    return rows


def _allowed_lifecycle_actions(user: User, tx: Transaction) -> list[dict[str, str]]:
    if getattr(user, "is_superuser", False):
        perms = frozenset({TRANSITION_TRANSACTIONS, MANAGE_TRANSACTIONS})
    else:
        perms = frozenset(
            code
            for code in (TRANSITION_TRANSACTIONS, MANAGE_TRANSACTIONS)
            if has_effective_permission(user, code)
        )
    return [
        {"to": move.target, "code": move.target}
        for move in available_transitions(tx, permissions=perms, user=user)
    ]


def _activity_page(user: User, tx: Transaction, *, limit: int) -> dict[str, Any] | None:
    try:
        page = project_record_activity(
            user,
            "transaction",
            str(tx.public_id),
            limit=limit,
            require_timeline_permission=False,
        )
    except PermissionDenied:
        return None
    return page.to_payload()


def workspace_payload(
    user: User,
    tx: Transaction,
    *,
    section: str | None = None,
) -> dict[str, Any]:
    """Full Inertia props for the sectioned workspace shell."""
    active = resolve_section(section)
    can_edit = can_manage_workspace(user, tx)
    can_view = (
        getattr(user, "is_superuser", False)
        or has_effective_permission(user, VIEW_TRANSACTIONS)
        or has_effective_permission(user, VIEW_OWN_TRANSACTIONS)
        or has_effective_permission(user, CREATE_OWN_TRANSACTIONS)
        or has_effective_permission(user, MANAGE_TRANSACTIONS)
        or scoped_transaction_queryset(user).filter(pk=tx.pk).exists()
    )

    payload: dict[str, Any] = {
        "transaction": serialize_transaction(user, tx),
        "expectedVersion": transaction_version(tx),
        "section": active,
        "sections": _section_nav(can_edit=can_edit),
        "capabilities": {
            "manage": can_edit,
            "view": can_view,
            "transition": has_effective_permission(user, TRANSITION_TRANSACTIONS)
            or getattr(user, "is_superuser", False),
            "viewBrokerNotes": can_view_broker_notes(user),
            "viewClients": getattr(user, "is_superuser", False)
            or has_effective_permission(user, VIEW_TRANSACTION_CLIENTS),
        },
        "allowedLifecycleActions": _allowed_lifecycle_actions(user, tx),
        "parties": serialize_parties(user, tx),
        "propertyHistory": serialize_property_history(tx),
        "keyDates": serialize_key_dates(tx),
        "notes": serialize_notes_for_reader(user, tx),
        "documents": [],
        "documentSchema": None,
        "signaturePackages": [],
        "signatureSchema": None,
        "activity": None,
        "activityTeaser": None,
    }

    if active == WorkspaceSection.SIGNATURES:
        from apps.transactions.deal_documents import serialize_documents_for_reader
        from apps.transactions.signing.serialize import (
            serialize_packages_for_reader,
            signature_schema_payload,
        )

        payload["signaturePackages"] = serialize_packages_for_reader(user, tx)
        payload["signatureSchema"] = signature_schema_payload()
        # A package is built from document versions already on the deal, so the
        # authoring picker needs the same projection the Documents section uses.
        payload["documents"] = serialize_documents_for_reader(user, tx)
    elif active == WorkspaceSection.DOCUMENTS:
        from apps.transactions.deal_documents import (
            document_schema_payload,
            serialize_documents_for_reader,
        )

        payload["documents"] = serialize_documents_for_reader(user, tx)
        payload["documentSchema"] = document_schema_payload()
    elif active == WorkspaceSection.ACTIVITY:
        payload["activity"] = _activity_page(user, tx, limit=20) or {
            "entries": [],
            "nextCursor": None,
            "hasMore": False,
            "timezone": "",
        }
    elif active == WorkspaceSection.OVERVIEW:
        payload["activityTeaser"] = _activity_page(user, tx, limit=5)

    return payload


__all__ = [
    "StaleTransactionVersion",
    "can_manage_workspace",
    "can_view_broker_notes",
    "load_workspace_transaction",
    "lock_transaction",
    "require_writable_transaction",
    "resolve_section",
    "touch_transaction",
    "transaction_version",
    "workspace_payload",
]
