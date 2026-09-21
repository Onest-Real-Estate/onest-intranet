"""Scoped transaction list payloads for agent and ops surfaces."""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.transactions.models import Transaction
from apps.transactions.permissions import (
    CREATE_OWN_TRANSACTIONS,
    MANAGE_TRANSACTIONS,
    VIEW_OWN_TRANSACTIONS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.services import (
    scoped_transaction_queryset,
    serialize_transaction,
)
from apps.transactions.taxonomy import STATUS_CODES, TYPE_CODES
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission
from apps.web.contracts import list_response
from apps.web.operations import operations_scope_payload

PAGE_SIZE = 25


def _property_line(tx: Transaction) -> str:
    snap = tx.property_snapshot or {}
    parts = [
        snap.get("line1") or snap.get("address_line1") or "",
        snap.get("city") or "",
        snap.get("state") or "",
    ]
    return ", ".join(p for p in parts if p)


def _list_row(user: User, tx: Transaction) -> dict[str, Any]:
    base = serialize_transaction(user, tx)
    return {
        "publicId": base["publicId"],
        "reference": base["reference"],
        "transactionType": base["transactionType"],
        "representationType": base["representationType"],
        "status": base["status"],
        "statusLabel": base["statusLabel"],
        "office": base["office"],
        "primaryAgent": base["primaryAgent"],
        "coordinator": base["coordinator"],
        "propertyLine": _property_line(tx),
        "mlsNumber": base["mlsNumber"],
        "acceptanceDate": base["acceptanceDate"],
        "closingDate": base["closingDate"],
        "updatedAt": base["updatedAt"],
        **(
            {"listPrice": base["listPrice"], "contractPrice": base["contractPrice"]}
            if "listPrice" in base
            else {}
        ),
    }


def build_transaction_list(
    user: User,
    *,
    q: str = "",
    status: str = "",
    transaction_type: str = "",
    page: int = 1,
    mine_only: bool = False,
) -> dict[str, Any]:
    qs = scoped_transaction_queryset(user).select_related(
        "office", "primary_agent", "coordinator"
    )
    if mine_only:
        qs = qs.filter(
            Q(primary_agent=user)
            | Q(coordinator=user)
            | Q(assignments__user=user, assignments__ended_at__isnull=True)
        ).distinct()

    needle = (q or "").strip()
    if needle:
        qs = qs.filter(
            Q(reference__icontains=needle)
            | Q(mls_number__icontains=needle)
            | Q(property_snapshot__line1__icontains=needle)
            | Q(property_snapshot__city__icontains=needle)
        )

    status_key = (status or "").strip()
    if status_key and status_key in STATUS_CODES:
        qs = qs.filter(status=status_key)

    type_key = (transaction_type or "").strip()
    if type_key and type_key in TYPE_CODES:
        qs = qs.filter(transaction_type=type_key)

    qs = qs.order_by("-updated_at", "-pk")
    total = qs.count()
    current = max(1, int(page or 1))
    start = (current - 1) * PAGE_SIZE
    rows = [_list_row(user, tx) for tx in qs[start : start + PAGE_SIZE]]

    can_create = (
        getattr(user, "is_superuser", False)
        or has_effective_permission(user, MANAGE_TRANSACTIONS)
        or has_effective_permission(user, CREATE_OWN_TRANSACTIONS)
    )

    return {
        "items": list_response(
            rows,
            page=current,
            page_size=PAGE_SIZE,
            total_items=total,
            filters={
                "q": needle,
                "status": status_key if status_key in STATUS_CODES else "",
                "transactionType": type_key if type_key in TYPE_CODES else "",
            },
            sort_key="updatedAt",
            sort_direction="desc",
        ),
        "capabilities": {
            "create": can_create,
            "manage": getattr(user, "is_superuser", False)
            or has_effective_permission(user, MANAGE_TRANSACTIONS),
            "view": getattr(user, "is_superuser", False)
            or has_effective_permission(user, VIEW_TRANSACTIONS)
            or has_effective_permission(user, VIEW_OWN_TRANSACTIONS)
            or has_effective_permission(user, CREATE_OWN_TRANSACTIONS),
        },
        "scope": operations_scope_payload(user),
    }


__all__ = ["PAGE_SIZE", "build_transaction_list"]
