"""Persistence and rule-version freeze for commission calculations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.contract.calculations import CURRENT_RULE_VERSION
from apps.contract.models import CommissionCalculation
from apps.contract.services import create_draft_contract
from apps.contract.services.calculation_service import (
    persist_commission_calculation,
    preview_commission,
    serialize_commission_calculation,
)
from apps.contract.statuses import ContractStatus
from apps.contract.terms import CommissionBasis
from apps.contract.tests.conftest import agent, company_admin


@pytest.mark.django_db
def test_persist_is_idempotent(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    mentor = agent(seeded_offices, email="mentor@example.com")
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="70",
        office_split_percent="30",
        transaction_fee_amount="100",
        mentor_percent="10",
        mentor_basis=CommissionBasis.AGENT_SIDE_AFTER_FEES,
        mentor_payee=mentor,
        referral_percent="5",
        referral_basis=CommissionBasis.GROSS_COMMISSION,
        referral_payee=admin,
    )
    first = persist_commission_calculation(admin, contract, gross_commission="10000.00")
    second = persist_commission_calculation(
        admin, contract, gross_commission="10000.00"
    )
    assert first.pk == second.pk
    assert CommissionCalculation.objects.filter(contract=contract).count() == 1
    assert first.rule_version == CURRENT_RULE_VERSION
    assert first.mentor_amount == Decimal("690.00")
    assert first.referral_amount == Decimal("500.00")
    payload = serialize_commission_calculation(first)
    assert payload["mentorAmount"] == "690.00"
    assert payload["referralAmount"] == "500.00"
    assert any("Mentor deduction" in line for line in payload["explanation"])
    assert any("Referral deduction" in line for line in payload["explanation"])


@pytest.mark.django_db
def test_issued_contract_rejects_foreign_rule_version(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    mentor = agent(seeded_offices, email="mentor2@example.com")
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="70",
        office_split_percent="30",
        mentor_percent="10",
        mentor_basis=CommissionBasis.AGENT_SIDE_BEFORE_FEES,
        mentor_payee=mentor,
    )
    from apps.contract.lifecycle import allow_status_write

    contract.status = ContractStatus.SENT
    with allow_status_write():
        contract.save(update_fields=["status"])
    assert contract.calculation_rule_version == CURRENT_RULE_VERSION
    with pytest.raises(ValidationError) as exc:
        persist_commission_calculation(
            admin,
            contract,
            gross_commission="10000",
            rule_version="2.0.0",
        )
    assert "rule_version" in exc.value.message_dict
    # Frozen version still calculates.
    row = persist_commission_calculation(admin, contract, gross_commission="10000")
    assert row.rule_version == CURRENT_RULE_VERSION


@pytest.mark.django_db
def test_preview_uses_frozen_contract_terms(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    mentor = agent(seeded_offices, email="mentor3@example.com")
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="70",
        office_split_percent="30",
        transaction_fee_amount="0",
        mentor_percent="10",
        mentor_basis=CommissionBasis.AGENT_SIDE_BEFORE_FEES,
        mentor_payee=mentor,
    )
    # Mutating live fields must not affect preview when terms_snapshot exists.
    contract.mentor_percent = Decimal("99")
    result = preview_commission(contract, gross_commission="10000")
    assert result.mentor is not None
    assert result.mentor.amount == Decimal("700.00")


@pytest.mark.django_db
def test_persist_requires_manage_permission(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin, recipient=recipient, effective_on=date.today()
    )
    with pytest.raises(PermissionDenied):
        persist_commission_calculation(recipient, contract, gross_commission="1000")
