"""Optimistic concurrency helpers for transaction workspace writes."""

from __future__ import annotations

from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext_lazy as _

from apps.transactions.models import Transaction, TransactionAssignment
from apps.transactions.permissions import (
    CREATE_OWN_TRANSACTIONS,
    MANAGE_TRANSACTIONS,
    TRANSITION_TRANSACTIONS,
)
from apps.transactions.services import scoped_transaction_queryset
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission


class StaleTransactionVersion(ValidationError):
    """Somebody else saved the deal while the caller was editing."""

    def __init__(self, message: str | None = None):
        super().__init__(
            message
            or _(
                "Somebody else saved this transaction while you were working. "
                "Refresh and try again."
            )
        )


def transaction_version(tx: Transaction) -> str:
    """Opaque concurrency token derived from ``updated_at`` (ISO µs)."""
    return tx.updated_at.isoformat(timespec="microseconds")


def assert_fresh(tx: Transaction, expected_version: str) -> None:
    if transaction_version(tx) != (expected_version or ""):
        raise StaleTransactionVersion()


def lock_transaction(pk: int) -> Transaction:
    """Row lock without joining nullable FKs (PostgreSQL FOR UPDATE rule)."""
    return Transaction.objects.select_for_update(of=("self",)).get(pk=pk)


def touch_transaction(tx: Transaction) -> None:
    """Bump ``updated_at`` so expectedVersion advances on workspace writes."""
    tx.save(update_fields=["updated_at"])


def can_manage_workspace(user: User, tx: Transaction) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if has_effective_permission(user, MANAGE_TRANSACTIONS):
        return True
    if has_effective_permission(user, CREATE_OWN_TRANSACTIONS):
        return (
            tx.primary_agent_pk == user.pk
            or TransactionAssignment.objects.filter(
                transaction_id=tx.pk, user_id=user.pk, ended_at__isnull=True
            ).exists()
        )
    return False


def can_view_broker_notes(user: User) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return has_effective_permission(
        user, MANAGE_TRANSACTIONS
    ) or has_effective_permission(user, TRANSITION_TRANSACTIONS)


def load_workspace_transaction(user: User, public_id: UUID) -> Transaction:
    tx = (
        scoped_transaction_queryset(user)
        .select_related("office", "primary_agent", "coordinator", "created_by")
        .filter(public_id=public_id)
        .first()
    )
    if tx is None:
        raise Transaction.DoesNotExist
    return tx


def require_writable_transaction(
    user: User,
    public_id: UUID,
    *,
    expected_version: str,
) -> Transaction:
    """Load, authorize manage, lock, and assert concurrency for a mutation.

    Callers must already be inside ``transaction.atomic()``.
    """
    visible = load_workspace_transaction(user, public_id)
    if not can_manage_workspace(user, visible):
        raise PermissionDenied("You cannot edit this transaction.")
    locked = lock_transaction(visible.pk)
    assert_fresh(locked, expected_version)
    return locked


__all__ = [
    "StaleTransactionVersion",
    "assert_fresh",
    "can_manage_workspace",
    "can_view_broker_notes",
    "load_workspace_transaction",
    "lock_transaction",
    "require_writable_transaction",
    "touch_transaction",
    "transaction_version",
]
