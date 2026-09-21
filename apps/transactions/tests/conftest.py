"""Shared fixtures for the transactions domain tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.transactions.lifecycle import transition
from apps.transactions.models import Transaction
from apps.transactions.permissions import (
    MANAGE_TRANSACTIONS,
    TRANSITION_TRANSACTIONS,
    VIEW_TRANSACTION_CLIENTS,
    VIEW_TRANSACTION_FINANCIALS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.services import ActorContext, create_draft
from apps.transactions.taxonomy import (
    RepresentationType,
    TransactionStatus,
    TransactionType,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

ALL_PERMS = frozenset(
    {
        VIEW_TRANSACTIONS,
        MANAGE_TRANSACTIONS,
        TRANSITION_TRANSACTIONS,
        VIEW_TRANSACTION_FINANCIALS,
        VIEW_TRANSACTION_CLIENTS,
    }
)


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def actor(user: User, *extra: str) -> ActorContext:
    return ActorContext(user=user, permissions=frozenset(ALL_PERMS | set(extra)))


def make_draft(
    *,
    seeded,
    manager: User | None = None,
    agent: User | None = None,
    slug: str = "fairfax-va",
    **kwargs,
) -> Transaction:
    mgr = manager or completed_user(
        email="txn.manager@example.com", office=office(slug)
    )
    primary = agent or completed_user(
        email="txn.agent@example.com", office=office(slug)
    )
    return create_draft(
        actor=actor(mgr),
        office=office(slug),
        transaction_type=kwargs.pop("transaction_type", TransactionType.BUY),
        representation_type=kwargs.pop("representation_type", RepresentationType.BUYER),
        primary_agent=primary,
        property_snapshot=kwargs.pop(
            "property_snapshot",
            {"line1": "123 Main St", "city": "Fairfax", "state": "VA"},
        ),
        contract_price=kwargs.pop("contract_price", Decimal("450000.00")),
        list_price=kwargs.pop("list_price", Decimal("475000.00")),
        acceptance_date=kwargs.pop("acceptance_date", date(2026, 3, 1)),
        closing_date=kwargs.pop("closing_date", date(2026, 4, 15)),
        client_snapshots=kwargs.pop(
            "client_snapshots",
            [{"name": "Pat Client", "role": "buyer", "email": "pat@example.com"}],
        ),
        **kwargs,
    )


def advance_to(
    tx: Transaction,
    target: str,
    *,
    user: User,
    permissions: frozenset[str] = ALL_PERMS,
) -> Transaction:
    """Walk the happy path (and resume from hold) until ``target``."""
    order = [
        TransactionStatus.DRAFT,
        TransactionStatus.PREPARING,
        TransactionStatus.UNDER_CONTRACT,
        TransactionStatus.PENDING,
        TransactionStatus.COMPLIANCE_REVIEW,
        TransactionStatus.READY_TO_CLOSE,
        TransactionStatus.CLOSED,
        TransactionStatus.ARCHIVED,
    ]
    current = Transaction.objects.get(pk=tx.pk)
    if current.status == target:
        return current
    start = order.index(current.status)
    end = order.index(target)
    for next_status in order[start + 1 : end + 1]:
        current = transition(
            user=user,
            permissions=permissions,
            tx=current,
            to_status=next_status,
            expected_status=current.status,
            note="advance",
            archive_reason="retention"
            if next_status == TransactionStatus.ARCHIVED
            else "",
        )
    return current
