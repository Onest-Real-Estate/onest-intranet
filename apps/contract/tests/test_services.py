"""Query scope, draft creation authority, and permission separation."""

from __future__ import annotations

from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.contract.services import (
    agent_contract_status,
    contract_status_options,
    create_draft_contract,
    recipient_contract_queryset,
    scoped_contract_queryset,
    serialize_contract,
)
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, branch_admin, company_admin, office
from apps.user.administration_fields import DEPARTED
from apps.user.services.agent_administration import contract_domain, contract_status
from apps.user.services.user_directory import contract_filter_options
from apps.user.tests.test_profile import completed_user


@pytest.mark.django_db
def test_contract_domain_is_connected(seeded_offices):
    assert contract_domain() is not None
    options = contract_status_options()
    assert any(item["value"] == ContractStatus.ACTIVE for item in options)


@pytest.mark.django_db
def test_create_draft_requires_manage_permission(seeded_offices):
    plain = agent(seeded_offices)
    recipient = agent(seeded_offices, email="other@example.com", slug="harrisburg")
    with pytest.raises(PermissionDenied):
        create_draft_contract(plain, recipient=recipient, effective_on=date.today())


@pytest.mark.django_db
def test_create_draft_rejects_inactive_and_departed_agents(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    recipient.is_active = False
    recipient.save(update_fields=["is_active"])
    with pytest.raises(ValidationError):
        create_draft_contract(admin, recipient=recipient, effective_on=date.today())

    recipient.is_active = True
    recipient.agent_status = DEPARTED
    recipient.save(update_fields=["is_active", "agent_status"])
    with pytest.raises(ValidationError):
        create_draft_contract(admin, recipient=recipient, effective_on=date.today())


@pytest.mark.django_db
def test_create_draft_rejects_cross_scope_recipient(seeded_offices):
    actor = branch_admin(seeded_offices, slug="fairfax-va")
    outsider = agent(seeded_offices, email="out@example.com", slug="harrisburg")
    with pytest.raises(ValidationError) as exc:
        create_draft_contract(actor, recipient=outsider, effective_on=date.today())
    assert "recipient" in exc.value.message_dict


@pytest.mark.django_db
def test_scoped_queryset_hides_other_offices(seeded_offices):
    fairfax_admin = branch_admin(seeded_offices, slug="fairfax-va")
    company = company_admin(seeded_offices)
    local = agent(seeded_offices, email="local@example.com", slug="fairfax-va")
    remote = agent(seeded_offices, email="remote@example.com", slug="harrisburg")

    local_contract = create_draft_contract(
        company, recipient=local, effective_on=date.today()
    )
    remote_contract = create_draft_contract(
        company, recipient=remote, effective_on=date.today()
    )

    visible = set(scoped_contract_queryset(fairfax_admin).values_list("pk", flat=True))
    assert local_contract.pk in visible
    assert remote_contract.pk not in visible

    assert set(scoped_contract_queryset(company).values_list("pk", flat=True)) >= {
        local_contract.pk,
        remote_contract.pk,
    }


@pytest.mark.django_db
def test_recipient_queryset_is_self_only(seeded_offices):
    company = company_admin(seeded_offices)
    me = agent(seeded_offices, email="me@example.com")
    other = agent(seeded_offices, email="them@example.com", slug="harrisburg")
    mine = create_draft_contract(company, recipient=me, effective_on=date.today())
    create_draft_contract(company, recipient=other, effective_on=date.today())

    pks = set(recipient_contract_queryset(me).values_list("pk", flat=True))
    assert pks == {mine.pk}


@pytest.mark.django_db
def test_serialize_omits_commission_and_notes_without_grants(seeded_offices):
    company = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        company,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="70",
        office_split_percent="30",
        internal_notes="Sensitive broker note",
    )

    # Viewer with metadata only (no commission / notes).
    viewer = completed_user(email="tc@example.com", office=office("fairfax-va"))
    from apps.contract.tests.conftest import assign

    assign(viewer, "transaction_coordinator", "office", office("fairfax-va"))

    payload = serialize_contract(viewer, contract)
    assert payload["publicId"] == str(contract.public_id)
    assert "commission" not in payload
    assert "internalNotes" not in payload
    assert "termsSnapshot" not in payload

    full = serialize_contract(company, contract)
    assert full["commission"]["agentSplitPercent"] == "70.000"
    assert full["internalNotes"] == "Sensitive broker note"


@pytest.mark.django_db
def test_recipient_sees_own_commission_with_own_grant(seeded_offices):
    company = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    from apps.contract.tests.conftest import assign

    assign(recipient, "realtor", "office", office("fairfax-va"))
    contract = create_draft_contract(
        company,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="75",
        office_split_percent="25",
        internal_notes="Never for the agent",
    )
    payload = serialize_contract(recipient, contract)
    assert payload["commission"]["agentSplitPercent"] == "75.000"
    assert "internalNotes" not in payload


@pytest.mark.django_db
def test_agent_contract_status_and_directory_filter(seeded_offices):
    company = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    create_draft_contract(company, recipient=recipient, effective_on=date.today())
    status = agent_contract_status(recipient)
    assert status["available"] is True
    assert status["status"] == ContractStatus.DRAFT

    # Wired through agent_administration import shim.
    wired = contract_status(recipient)
    assert wired["available"] is True
    assert wired["status"] == ContractStatus.DRAFT

    filters = contract_filter_options(company)
    assert filters["available"] is True
    assert any(opt["value"] == ContractStatus.ACTIVE for opt in filters["options"])


@pytest.mark.django_db
def test_serialize_includes_payee_summary(seeded_offices):
    from decimal import Decimal

    from apps.contract.administration import update_draft_contract
    from apps.contract.lifecycle import contract_version

    company = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    mentor = agent(seeded_offices, email="mentor.payee@example.com", slug="fairfax-va")
    contract = create_draft_contract(
        company,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="70",
        office_split_percent="30",
    )
    contract = update_draft_contract(
        company,
        contract,
        expected_version=contract_version(contract),
        mentor_percent=Decimal("5"),
        mentor_basis="agent_side_before_fees",
        mentor_payee=mentor,
    )

    payload = serialize_contract(company, contract)
    payee = payload["commission"]["mentor"]["payee"]
    assert payee["id"] == mentor.pk
    assert payee["email"] == mentor.email
    assert payee["name"]
