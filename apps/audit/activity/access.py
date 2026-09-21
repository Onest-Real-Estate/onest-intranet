"""Record-type registry and access gates for activity timelines."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

TIMELINE_PERMISSION = "audit.can_view_activity_timeline"

RECORD_USER = "user"
RECORD_CONTRACT = "contract"
RECORD_TRANSACTION = "transaction"
RECORD_LEAD = "lead"
RECORD_RESERVATION = "reservation"
RECORD_SUPPORT = "support"

SUPPORTED_RECORD_TYPES = frozenset(
    {
        RECORD_USER,
        RECORD_CONTRACT,
        RECORD_TRANSACTION,
        RECORD_LEAD,
        RECORD_RESERVATION,
        RECORD_SUPPORT,
    }
)


@dataclass(frozen=True)
class RecordTypeConfig:
    key: str
    target_types: frozenset[str]
    action_prefixes: tuple[str, ...]
    domain_permission: str
    label: str


RECORD_TYPES: dict[str, RecordTypeConfig] = {
    RECORD_USER: RecordTypeConfig(
        key=RECORD_USER,
        target_types=frozenset({"user.user"}),
        action_prefixes=("user.",),
        domain_permission="user.view_user_administration",
        label="user",
    ),
    RECORD_CONTRACT: RecordTypeConfig(
        key=RECORD_CONTRACT,
        target_types=frozenset({"contract.contract", "contract"}),
        action_prefixes=("contract.",),
        domain_permission="web.view_agent_contracts",
        label="contract",
    ),
    RECORD_TRANSACTION: RecordTypeConfig(
        key=RECORD_TRANSACTION,
        target_types=frozenset(
            {"transaction.transaction", "transactions.transaction", "transaction"}
        ),
        action_prefixes=("transaction.",),
        domain_permission="web.view_transactions",
        label="transaction",
    ),
    RECORD_LEAD: RecordTypeConfig(
        key=RECORD_LEAD,
        target_types=frozenset({"crm.lead", "lead"}),
        action_prefixes=("lead.",),
        domain_permission="web.view_own_leads",
        label="lead",
    ),
    RECORD_RESERVATION: RecordTypeConfig(
        key=RECORD_RESERVATION,
        target_types=frozenset({"reservation.reservation", "reservation"}),
        action_prefixes=("reservation.",),
        domain_permission="web.view_reservations",
        label="reservation",
    ),
    RECORD_SUPPORT: RecordTypeConfig(
        key=RECORD_SUPPORT,
        target_types=frozenset({"support.ticket", "support"}),
        action_prefixes=("support.",),
        domain_permission="web.view_it_support",
        label="support record",
    ),
}


def _require_permission(viewer: User, permission: str, message: str) -> None:
    if getattr(viewer, "is_superuser", False):
        return
    if not has_effective_permission(viewer, permission):
        raise PermissionDenied(message)


def _resolve_user(viewer: User, record_id: str) -> User:
    from apps.user.services.agent_administration import administered_user_queryset

    try:
        pk = int(record_id)
    except (TypeError, ValueError) as exc:
        raise Http404("User not found.") from exc
    target = administered_user_queryset(viewer).filter(pk=pk).first()
    if target is None:
        raise Http404("User not found.")
    return target


def assert_can_view_record_activity(
    viewer: User,
    record_type: str,
    record_id: str,
    *,
    require_timeline_permission: bool = True,
) -> RecordTypeConfig:
    """Authorize timeline access for one concrete record.

    Missing / out-of-scope records raise ``Http404`` so direct APIs cannot probe
    identifiers. Capability failures raise ``PermissionDenied``.
    """
    config = RECORD_TYPES.get(record_type)
    if config is None:
        raise Http404("Unknown activity record type.")

    if require_timeline_permission:
        _require_permission(
            viewer,
            TIMELINE_PERMISSION,
            "You do not have permission to view activity timelines.",
        )

    if record_type == RECORD_USER:
        _resolve_user(viewer, record_id)
        return config

    if record_type == RECORD_TRANSACTION:
        _resolve_transaction(viewer, record_id)
        return config

    _require_permission(
        viewer,
        config.domain_permission,
        f"You do not have permission to view this {config.label}.",
    )
    if not str(record_id).strip():
        raise Http404(f"{config.label.capitalize()} not found.")
    return config


def _resolve_transaction(viewer: User, record_id: str):
    from uuid import UUID

    from apps.transactions.services import scoped_transaction_queryset

    try:
        public_id = UUID(str(record_id))
    except (TypeError, ValueError) as exc:
        raise Http404("Transaction not found.") from exc
    tx = scoped_transaction_queryset(viewer).filter(public_id=public_id).first()
    if tx is None:
        raise Http404("Transaction not found.")
    return tx
