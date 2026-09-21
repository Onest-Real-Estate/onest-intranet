"""Model constraints, money quantization, and PROTECT semantics."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.transactions.lifecycle import allow_status_write
from apps.transactions.models import Transaction, TransactionAssignment
from apps.transactions.money import quantize_money
from apps.transactions.services import create_draft, end_assignment, upsert_assignment
from apps.transactions.taxonomy import (
    AssignmentRole,
    RepresentationType,
    TransactionStatus,
)
from apps.transactions.tests.conftest import actor, make_draft, office
from apps.user.tests.test_profile import completed_user


@pytest.mark.django_db
def test_quantize_money_rejects_negative():
    with pytest.raises(ValidationError):
        quantize_money("-1.00")


@pytest.mark.django_db
def test_create_draft_sets_reference_and_assignment(seeded):
    tx = make_draft(seeded=seeded)
    assert tx.reference.startswith("TXN-")
    assert tx.status == TransactionStatus.DRAFT
    assert TransactionAssignment.objects.filter(
        transaction=tx,
        role=AssignmentRole.PRIMARY_AGENT,
        ended_at__isnull=True,
    ).exists()
    assert tx.list_price == Decimal("475000.00")
    assert tx.contract_price == Decimal("450000.00")


@pytest.mark.django_db
def test_office_protect_blocks_delete(seeded):
    tx = make_draft(seeded=seeded)
    owning = tx.office
    with pytest.raises(IntegrityError), transaction.atomic():
        owning.delete()
    assert Transaction.objects.filter(pk=tx.pk).exists()


@pytest.mark.django_db
def test_direct_status_save_refused(seeded):
    tx = make_draft(seeded=seeded)
    tx.status = TransactionStatus.PREPARING
    with pytest.raises(ValidationError) as exc:
        tx.save()
    assert "lifecycle" in str(exc.value).lower() or "status" in str(exc.value).lower()


@pytest.mark.django_db
def test_queryset_update_status_refused(seeded):
    tx = make_draft(seeded=seeded)
    with pytest.raises(ValidationError):
        Transaction.objects.filter(pk=tx.pk).update(status=TransactionStatus.PREPARING)


@pytest.mark.django_db
def test_allow_status_write_permits_lifecycle_save(seeded):
    tx = make_draft(seeded=seeded)
    with allow_status_write():
        tx.status = TransactionStatus.PREPARING
        tx.preparing_at = tx.created_at
        tx.save(update_fields=["status", "preparing_at", "updated_at"])
    tx.refresh_from_db()
    assert tx.status == TransactionStatus.PREPARING


@pytest.mark.django_db
def test_singleton_primary_assignment(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.mgr2@example.com", office=office("fairfax-va"))
    other = completed_user(email="txn.other@example.com", office=office("fairfax-va"))
    upsert_assignment(
        actor=actor(mgr),
        tx=tx,
        user=other,
        role=AssignmentRole.PRIMARY_AGENT,
    )
    active = list(
        TransactionAssignment.objects.filter(
            transaction=tx,
            role=AssignmentRole.PRIMARY_AGENT,
            ended_at__isnull=True,
        )
    )
    assert len(active) == 1
    assert active[0].user_id == other.pk
    tx.refresh_from_db()
    assert tx.primary_agent_pk == other.pk


@pytest.mark.django_db
def test_end_assignment_clears_fk(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.mgr3@example.com", office=office("fairfax-va"))
    agent = tx.primary_agent
    end_assignment(
        actor=actor(mgr),
        tx=tx,
        user=agent,
        role=AssignmentRole.PRIMARY_AGENT,
    )
    tx.refresh_from_db()
    assert tx.primary_agent_pk is None
    assert not TransactionAssignment.objects.filter(
        transaction=tx,
        role=AssignmentRole.PRIMARY_AGENT,
        ended_at__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_unknown_type_rejected(seeded):
    mgr = completed_user(email="txn.bad@example.com", office=office("fairfax-va"))
    with pytest.raises(ValidationError):
        create_draft(
            actor=actor(mgr),
            office=office("fairfax-va"),
            transaction_type="lease",
            representation_type=RepresentationType.TENANT,
        )


@pytest.mark.django_db
def test_status_vocabulary_constraint(seeded):
    """Illegal status strings are rejected by the database check constraint."""
    tx = make_draft(seeded=seeded)
    from django.db import connection

    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE transactions_transaction SET status = %s WHERE id = %s",
            ["not_a_status", tx.pk],
        )
