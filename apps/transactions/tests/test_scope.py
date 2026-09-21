"""Scope matrix for Transaction.for_reader."""

from __future__ import annotations

import pytest

from apps.transactions.services import scoped_transaction_queryset, upsert_assignment
from apps.transactions.taxonomy import AssignmentRole
from apps.transactions.tests.conftest import actor, assign, make_draft, office
from apps.user.services.role_assignments import get_effective_access
from apps.user.tests.test_profile import completed_user


@pytest.mark.django_db
def test_company_admin_sees_all(seeded):
    fairfax = make_draft(seeded=seeded, slug="fairfax-va")
    other = make_draft(
        seeded=seeded,
        slug="charlottesville-va",
        manager=completed_user(
            email="txn.cville.mgr@example.com", office=office("charlottesville-va")
        ),
        agent=completed_user(
            email="txn.cville.agent@example.com", office=office("charlottesville-va")
        ),
    )
    admin = completed_user(
        email="txn.admin@example.com", office=office("onest-head-office")
    )
    assign(admin, "system_admin", "company")
    access = get_effective_access(admin)
    ids = set(
        scoped_transaction_queryset(admin, access=access).values_list("pk", flat=True)
    )
    assert fairfax.pk in ids
    assert other.pk in ids


@pytest.mark.django_db
def test_office_scope_excludes_other_branch(seeded):
    local = make_draft(seeded=seeded, slug="fairfax-va")
    make_draft(
        seeded=seeded,
        slug="charlottesville-va",
        manager=completed_user(
            email="txn.cville.mgr2@example.com", office=office("charlottesville-va")
        ),
        agent=completed_user(
            email="txn.cville.agent2@example.com", office=office("charlottesville-va")
        ),
    )
    tc = completed_user(email="txn.tc@example.com", office=office("fairfax-va"))
    assign(tc, "transaction_coordinator", "office", office("fairfax-va"))
    access = get_effective_access(tc)
    ids = set(
        scoped_transaction_queryset(tc, access=access).values_list("pk", flat=True)
    )
    assert ids == {local.pk}


@pytest.mark.django_db
def test_assignee_sees_deal_outside_office_scope(seeded):
    tx = make_draft(seeded=seeded, slug="fairfax-va")
    outsider = completed_user(
        email="txn.outsider@example.com", office=office("charlottesville-va")
    )
    mgr = completed_user(
        email="txn.assign.mgr@example.com", office=office("fairfax-va")
    )
    upsert_assignment(
        actor=actor(mgr),
        tx=tx,
        user=outsider,
        role=AssignmentRole.CO_AGENT,
    )
    access = get_effective_access(outsider)
    ids = set(
        scoped_transaction_queryset(outsider, access=access).values_list(
            "pk", flat=True
        )
    )
    assert tx.pk in ids


@pytest.mark.django_db
def test_unrelated_user_sees_nothing(seeded):
    make_draft(seeded=seeded)
    stranger = completed_user(
        email="txn.stranger@example.com", office=office("charlottesville-va")
    )
    access = get_effective_access(stranger)
    assert not scoped_transaction_queryset(stranger, access=access).exists()


@pytest.mark.django_db
def test_superuser_sees_all(seeded):
    tx = make_draft(seeded=seeded)
    admin = completed_user(
        email="txn.super@example.com", office=office("onest-head-office")
    )
    admin.is_superuser = True
    admin.save(update_fields=["is_superuser"])
    access = get_effective_access(admin)
    assert scoped_transaction_queryset(admin, access=access).filter(pk=tx.pk).exists()
