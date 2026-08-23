"""Persist and replay mentor/referral commission calculations.

Pure math stays in :mod:`apps.contract.calculations`. This module maps contract
rows onto calculation inputs, stores immutable result rows, and reuses
identical fingerprints so the same worksheet is idempotent.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.contract.calculations import (
    CURRENT_RULE_VERSION,
    ContractTermsInput,
    SideTerms,
    SplitTerms,
    TransactionInput,
    calculate_commission,
)
from apps.contract.calculations.types import CalculationResult
from apps.contract.models import AgentContract, CommissionCalculation
from apps.contract.permissions import MANAGE_AGENT_CONTRACTS, VIEW_COMMISSION_TERMS
from apps.contract.statuses import ContractStatus
from apps.contract.terms import ZERO
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

_ISSUED_STATUSES = frozenset(
    {
        ContractStatus.SENT,
        ContractStatus.VIEWED,
        ContractStatus.SIGNED,
        ContractStatus.ACTIVE,
        ContractStatus.SUPERSEDED,
        ContractStatus.EXPIRED,
        ContractStatus.TERMINATED,
    }
)


def terms_input_from_contract(
    contract: AgentContract,
    *,
    rule_version: str | None = None,
) -> ContractTermsInput:
    """Build calculation terms from a contract, preferring frozen snapshots."""
    version = rule_version or contract.calculation_rule_version or CURRENT_RULE_VERSION
    snap = contract.terms_snapshot or {}
    if snap.get("mentor") is not None or snap.get("agentSplitPercent") is not None:
        mentor = snap.get("mentor") or {}
        referral = snap.get("referral") or {}
        return ContractTermsInput(
            split=SplitTerms(
                agent_split_percent=_parse_dec(snap.get("agentSplitPercent")),
                office_split_percent=_parse_dec(snap.get("officeSplitPercent")),
                transaction_fee_amount=_parse_dec(snap.get("transactionFeeAmount")),
                transaction_fee_percent=_parse_dec(snap.get("transactionFeePercent")),
            ),
            mentor=SideTerms(
                role="mentor",
                percent=_parse_dec(mentor.get("percent")),
                fixed_amount=_parse_dec(mentor.get("fixedAmount")),
                cap_amount=_parse_dec(mentor.get("capAmount")),
                basis=mentor.get("basis") or "",
                payee_id=mentor.get("payeeId"),
                notes=mentor.get("notes") or "",
            ),
            referral=SideTerms(
                role="referral",
                percent=_parse_dec(referral.get("percent")),
                fixed_amount=_parse_dec(referral.get("fixedAmount")),
                cap_amount=_parse_dec(referral.get("capAmount")),
                basis=referral.get("basis") or "",
                payee_id=referral.get("payeeId"),
                notes=referral.get("notes") or "",
            ),
            special_arrangements=snap.get("specialArrangements") or "",
            rule_version=version,
        )
    return ContractTermsInput(
        split=SplitTerms(
            agent_split_percent=contract.agent_split_percent,
            office_split_percent=contract.office_split_percent,
            transaction_fee_amount=contract.transaction_fee_amount,
            transaction_fee_percent=contract.transaction_fee_percent,
        ),
        mentor=SideTerms(
            role="mentor",
            percent=contract.mentor_percent,
            fixed_amount=contract.mentor_fixed_amount,
            cap_amount=contract.mentor_cap_amount,
            basis=contract.mentor_basis or "",
            payee_id=contract.mentor_payee_id,
            notes=contract.mentor_notes or "",
        ),
        referral=SideTerms(
            role="referral",
            percent=contract.referral_percent,
            fixed_amount=contract.referral_fixed_amount,
            cap_amount=contract.referral_cap_amount,
            basis=contract.referral_basis or "",
            payee_id=contract.referral_payee_id,
            notes=contract.referral_notes or "",
        ),
        special_arrangements=contract.special_arrangements or "",
        rule_version=version,
    )


def preview_commission(
    contract: AgentContract,
    *,
    gross_commission: Decimal | str,
    currency: str = "USD",
    rule_version: str | None = None,
) -> CalculationResult:
    """Run the pure calculator without persisting."""
    terms = terms_input_from_contract(contract, rule_version=rule_version)
    txn = TransactionInput(
        gross_commission=Decimal(str(gross_commission)),
        currency=currency,
    )
    return calculate_commission(txn, terms)


def persist_commission_calculation(
    actor: User,
    contract: AgentContract,
    *,
    gross_commission: Decimal | str,
    currency: str = "USD",
    rule_version: str | None = None,
) -> CommissionCalculation:
    """Calculate and store (or reuse) an immutable calculation row."""
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, MANAGE_AGENT_CONTRACTS)
    ):
        raise PermissionDenied(_("You cannot manage agent contracts."))

    from apps.contract.services import scoped_contract_queryset

    if (
        not getattr(actor, "is_superuser", False)
        and not scoped_contract_queryset(actor).filter(pk=contract.pk).exists()
    ):
        raise PermissionDenied(_("Contract is outside your scope."))
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, VIEW_COMMISSION_TERMS)
        or has_effective_permission(actor, MANAGE_AGENT_CONTRACTS)
    ):
        raise PermissionDenied(_("Commission terms are not visible to you."))

    if contract.status in _ISSUED_STATUSES:
        version = contract.calculation_rule_version
        if rule_version and rule_version != version:
            raise ValidationError(
                {
                    "rule_version": _(
                        "Issued contracts must calculate under their frozen "
                        "rule version %(version)s."
                    )
                    % {"version": version}
                }
            )
    else:
        version = rule_version or contract.calculation_rule_version

    result = preview_commission(
        contract,
        gross_commission=gross_commission,
        currency=currency,
        rule_version=version,
    )
    fingerprint = _fingerprint(result)

    existing = CommissionCalculation.objects.filter(
        contract=contract, fingerprint=fingerprint
    ).first()
    if existing is not None:
        return existing

    mentor_amount = result.mentor.amount if result.mentor else ZERO
    referral_amount = result.referral.amount if result.referral else ZERO

    with transaction.atomic():
        row = CommissionCalculation(
            contract=contract,
            rule_version=result.rule_version,
            currency=result.currency,
            fingerprint=fingerprint,
            input_snapshot=result.input_snapshot,
            terms_snapshot=result.terms_snapshot,
            intermediate_snapshot=result.intermediates,
            result_snapshot=result.to_snapshot(),
            explanation=list(result.explanation),
            mentor_amount=mentor_amount,
            referral_amount=referral_amount,
            agent_net_amount=result.agent_net,
            office_net_amount=result.office_net,
            transaction_fee_amount=result.transaction_fee,
            created_by=actor,
        )
        row.full_clean()
        row.save()
    return row


def serialize_commission_calculation(row: CommissionCalculation) -> dict[str, Any]:
    """CamelCase payload for Inertia / PDF shared breakdowns."""
    return {
        "publicId": str(row.public_id),
        "contractPublicId": str(row.contract.public_id),
        "ruleVersion": row.rule_version,
        "currency": row.currency,
        "fingerprint": row.fingerprint,
        "input": row.input_snapshot,
        "terms": row.terms_snapshot,
        "intermediates": row.intermediate_snapshot,
        "result": row.result_snapshot,
        "explanation": row.explanation,
        "mentorAmount": format(row.mentor_amount, "f"),
        "referralAmount": format(row.referral_amount, "f"),
        "agentNetAmount": format(row.agent_net_amount, "f"),
        "officeNetAmount": format(row.office_net_amount, "f"),
        "transactionFeeAmount": format(row.transaction_fee_amount, "f"),
        "createdAt": row.created_at.isoformat(),
    }


def _fingerprint(result: CalculationResult) -> str:
    payload = json.dumps(
        result.fingerprint_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))
