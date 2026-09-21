"""Exhaustive transition table, guards, preconditions, and audit/events."""

from __future__ import annotations

from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditEvent, DomainEvent
from apps.transactions.lifecycle import (
    ConcurrentUpdate,
    TransitionError,
    available_transitions,
    transition,
)
from apps.transactions.permissions import MANAGE_TRANSACTIONS, TRANSITION_TRANSACTIONS
from apps.transactions.taxonomy import (
    TRANSITIONS,
    TransactionStatus,
    find_transition,
    transitions_from,
)
from apps.transactions.tests.conftest import (
    ALL_PERMS,
    advance_to,
    make_draft,
    office,
)
from apps.user.tests.test_profile import completed_user


@pytest.mark.django_db
def test_transition_index_covers_declared_pairs():
    for move in TRANSITIONS:
        assert find_transition(move.source, move.target) is move


@pytest.mark.django_db
def test_illegal_transition_refused(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.life.mgr@example.com", office=office("fairfax-va"))
    with pytest.raises(TransitionError):
        transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=tx,
            to_status=TransactionStatus.CLOSED,
            expected_status=TransactionStatus.DRAFT,
        )


@pytest.mark.django_db
def test_stale_expected_status_is_concurrent(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.race.mgr@example.com", office=office("fairfax-va"))
    transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=tx,
        to_status=TransactionStatus.PREPARING,
        expected_status=TransactionStatus.DRAFT,
    )
    with pytest.raises(ConcurrentUpdate):
        transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=tx,
            to_status=TransactionStatus.PREPARING,
            expected_status=TransactionStatus.DRAFT,
        )


@pytest.mark.django_db
def test_idempotent_same_target(seeded, django_capture_on_commit_callbacks):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.idem.mgr@example.com", office=office("fairfax-va"))
    with django_capture_on_commit_callbacks(execute=True):
        transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=tx,
            to_status=TransactionStatus.PREPARING,
            expected_status=TransactionStatus.DRAFT,
        )
    before = AuditEvent.objects.filter(action="transaction.status_changed").count()
    before_events = DomainEvent.objects.filter(
        name="transaction.status_changed"
    ).count()
    with django_capture_on_commit_callbacks(execute=True):
        again = transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=tx,
            to_status=TransactionStatus.PREPARING,
            expected_status=TransactionStatus.PREPARING,
        )
    assert again.status == TransactionStatus.PREPARING
    assert (
        AuditEvent.objects.filter(action="transaction.status_changed").count() == before
    )
    assert (
        DomainEvent.objects.filter(name="transaction.status_changed").count()
        == before_events
    )


@pytest.mark.django_db
def test_permission_required_for_close(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.close.mgr@example.com", office=office("fairfax-va"))
    ready = advance_to(tx, TransactionStatus.READY_TO_CLOSE, user=mgr)
    agent = ready.primary_agent
    with pytest.raises(PermissionDenied):
        transition(
            user=agent,
            permissions=frozenset(),
            tx=ready,
            to_status=TransactionStatus.CLOSED,
            expected_status=TransactionStatus.READY_TO_CLOSE,
        )


@pytest.mark.django_db
def test_assignee_may_start_preparing(seeded):
    tx = make_draft(seeded=seeded)
    agent = tx.primary_agent
    moved = transition(
        user=agent,
        permissions=frozenset(),
        tx=tx,
        to_status=TransactionStatus.PREPARING,
        expected_status=TransactionStatus.DRAFT,
    )
    assert moved.status == TransactionStatus.PREPARING


@pytest.mark.django_db
def test_close_requires_compliance_and_closing_date(seeded):
    tx = make_draft(seeded=seeded, closing_date=None)
    mgr = completed_user(
        email="txn.precond.mgr@example.com", office=office("fairfax-va")
    )
    # Manually walk until ready_to_close would fail without closing_date.
    current = advance_to(tx, TransactionStatus.COMPLIANCE_REVIEW, user=mgr)
    with pytest.raises(ValidationError):
        transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=current,
            to_status=TransactionStatus.READY_TO_CLOSE,
            expected_status=TransactionStatus.COMPLIANCE_REVIEW,
        )

    current.closing_date = date(2026, 4, 15)
    current.save(update_fields=["closing_date", "updated_at"])
    ready = transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=current,
        to_status=TransactionStatus.READY_TO_CLOSE,
        expected_status=TransactionStatus.COMPLIANCE_REVIEW,
    )
    assert ready.compliance_approved_at is not None

    # Strip clearance and attempt close.
    ready.compliance_approved_at = None
    ready.save(update_fields=["compliance_approved_at", "updated_at"])
    with pytest.raises(ValidationError) as exc:
        transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=ready,
            to_status=TransactionStatus.CLOSED,
            expected_status=TransactionStatus.READY_TO_CLOSE,
        )
    assert "compliance" in str(exc.value).lower()


@pytest.mark.django_db
def test_archive_only_from_closed(seeded, django_capture_on_commit_callbacks):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.arch.mgr@example.com", office=office("fairfax-va"))
    closed = advance_to(tx, TransactionStatus.CLOSED, user=mgr)
    with django_capture_on_commit_callbacks(execute=True):
        archived = transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=closed,
            to_status=TransactionStatus.ARCHIVED,
            expected_status=TransactionStatus.CLOSED,
            archive_reason="year-end retention",
        )
    assert archived.status == TransactionStatus.ARCHIVED
    assert archived.archived_at is not None
    assert AuditEvent.objects.filter(action="transaction.archived").exists()
    assert DomainEvent.objects.filter(name="transaction.archived").exists()


@pytest.mark.django_db
def test_on_hold_and_resume(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.hold.mgr@example.com", office=office("fairfax-va"))
    pending = advance_to(tx, TransactionStatus.PENDING, user=mgr)
    held = transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=pending,
        to_status=TransactionStatus.ON_HOLD,
        expected_status=TransactionStatus.PENDING,
        note="waiting on appraisal",
    )
    assert held.held_from_status == TransactionStatus.PENDING
    with pytest.raises(TransitionError):
        transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=held,
            to_status=TransactionStatus.PREPARING,
            expected_status=TransactionStatus.ON_HOLD,
        )
    resumed = transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=held,
        to_status=TransactionStatus.PENDING,
        expected_status=TransactionStatus.ON_HOLD,
    )
    assert resumed.status == TransactionStatus.PENDING
    assert resumed.held_from_status == ""


@pytest.mark.django_db
def test_cancelled_and_withdrawn_paths(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.side.mgr@example.com", office=office("fairfax-va"))
    preparing = transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=tx,
        to_status=TransactionStatus.PREPARING,
        expected_status=TransactionStatus.DRAFT,
    )
    cancelled = transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=preparing,
        to_status=TransactionStatus.CANCELLED,
        expected_status=TransactionStatus.PREPARING,
        note="buyer walked",
    )
    assert cancelled.cancelled_at is not None

    other = make_draft(
        seeded=seeded,
        manager=completed_user(
            email="txn.side.mgr2@example.com", office=office("fairfax-va")
        ),
        agent=completed_user(
            email="txn.side.agent2@example.com", office=office("fairfax-va")
        ),
    )
    under = advance_to(other, TransactionStatus.UNDER_CONTRACT, user=mgr)
    withdrawn = transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=under,
        to_status=TransactionStatus.WITHDRAWN,
        expected_status=TransactionStatus.UNDER_CONTRACT,
        note="offer withdrawn",
    )
    assert withdrawn.withdrawn_at is not None


@pytest.mark.django_db
def test_available_transitions_respect_resume_target(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(email="txn.avail.mgr@example.com", office=office("fairfax-va"))
    pending = advance_to(tx, TransactionStatus.PENDING, user=mgr)
    held = transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=pending,
        to_status=TransactionStatus.ON_HOLD,
        expected_status=TransactionStatus.PENDING,
        note="pause",
    )
    allowed = available_transitions(held, permissions=ALL_PERMS, user=mgr)
    targets = {t.target for t in allowed}
    assert TransactionStatus.PENDING in targets
    assert TransactionStatus.PREPARING not in targets


@pytest.mark.django_db
def test_every_declared_transition_is_reachable_from_source():
    for source in {t.source for t in TRANSITIONS}:
        outs = transitions_from(source)
        assert outs
        for move in outs:
            assert move.source == source


@pytest.mark.django_db
def test_create_emits_audit_and_domain_event(
    seeded, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        make_draft(seeded=seeded)
    assert AuditEvent.objects.filter(action="transaction.created").exists()
    assert DomainEvent.objects.filter(name="transaction.created").exists()


@pytest.mark.django_db
def test_under_contract_requires_price_and_property(seeded):
    tx = make_draft(
        seeded=seeded,
        property_snapshot={},
        contract_price=None,
        acceptance_date=None,
    )
    mgr = completed_user(email="txn.req.mgr@example.com", office=office("fairfax-va"))
    preparing = transition(
        user=mgr,
        permissions=ALL_PERMS,
        tx=tx,
        to_status=TransactionStatus.PREPARING,
        expected_status=TransactionStatus.DRAFT,
    )
    with pytest.raises(ValidationError):
        transition(
            user=mgr,
            permissions=ALL_PERMS,
            tx=preparing,
            to_status=TransactionStatus.UNDER_CONTRACT,
            expected_status=TransactionStatus.PREPARING,
        )


@pytest.mark.django_db
def test_transition_grant_without_manage_still_works(seeded):
    tx = make_draft(seeded=seeded)
    mgr = completed_user(
        email="txn.trans.only@example.com", office=office("fairfax-va")
    )
    moved = transition(
        user=mgr,
        permissions=frozenset({TRANSITION_TRANSACTIONS}),
        tx=tx,
        to_status=TransactionStatus.PREPARING,
        expected_status=TransactionStatus.DRAFT,
    )
    assert moved.status == TransactionStatus.PREPARING
    # manage alone also authorizes
    other = make_draft(
        seeded=seeded,
        manager=completed_user(
            email="txn.mgmt.only@example.com", office=office("fairfax-va")
        ),
        agent=completed_user(
            email="txn.mgmt.agent@example.com", office=office("fairfax-va")
        ),
    )
    moved2 = transition(
        user=mgr,
        permissions=frozenset({MANAGE_TRANSACTIONS}),
        tx=other,
        to_status=TransactionStatus.PREPARING,
        expected_status=TransactionStatus.DRAFT,
    )
    assert moved2.status == TransactionStatus.PREPARING
