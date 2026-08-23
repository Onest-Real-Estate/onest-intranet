"""Validation for mentor/referral terms and transaction inputs.

Ambiguous configurations fail closed — never invent a basis, payee, or split.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.contract.calculations.rules import (
    SUPPORTED_CURRENCIES,
    SUPPORTED_RULE_VERSIONS,
)
from apps.contract.calculations.types import (
    ContractTermsInput,
    SideTerms,
    SplitTerms,
    TransactionInput,
)
from apps.contract.terms import (
    HUNDRED,
    ZERO,
    CommissionBasis,
    quantize_money,
    quantize_percent,
)


def validate_transaction_input(transaction: TransactionInput) -> TransactionInput:
    if transaction.currency not in SUPPORTED_CURRENCIES:
        raise ValidationError(
            {
                "currency": _(
                    "Unsupported currency %(currency)s. Supported: %(supported)s."
                )
                % {
                    "currency": transaction.currency,
                    "supported": ", ".join(sorted(SUPPORTED_CURRENCIES)),
                }
            }
        )
    try:
        gross = quantize_money(transaction.gross_commission)
    except ValidationError as exc:
        raise ValidationError({"gross_commission": exc.messages}) from exc
    if gross is None:
        raise ValidationError({"gross_commission": _("Gross commission is required.")})
    if gross < ZERO:
        raise ValidationError(
            {"gross_commission": _("Gross commission cannot be negative.")}
        )
    return TransactionInput(gross_commission=gross, currency=transaction.currency)


def validate_side_terms(side: SideTerms) -> SideTerms:
    """Normalize and reject incomplete or conflicting mentor/referral terms."""
    errors: dict[str, list[str]] = {}
    prefix = side.role

    try:
        percent = quantize_percent(side.percent)
    except ValidationError as exc:
        errors.setdefault(f"{prefix}_percent", []).extend(exc.messages)
        percent = side.percent

    try:
        fixed = quantize_money(side.fixed_amount)
    except ValidationError as exc:
        errors.setdefault(f"{prefix}_fixed_amount", []).extend(exc.messages)
        fixed = side.fixed_amount

    try:
        cap = quantize_money(side.cap_amount)
    except ValidationError as exc:
        errors.setdefault(f"{prefix}_cap_amount", []).extend(exc.messages)
        cap = side.cap_amount

    basis = (side.basis or "").strip()
    has_money = percent is not None or fixed is not None

    if has_money and not basis:
        errors.setdefault(f"{prefix}_basis", []).append(
            str(
                _(
                    "A calculation basis is required when percent or fixed "
                    "amount is set."
                )
            )
        )
    if basis and basis not in CommissionBasis.values:
        errors.setdefault(f"{prefix}_basis", []).append(
            str(_("Unknown calculation basis %(basis)s.") % {"basis": basis})
        )
    if basis == CommissionBasis.FIXED_ONLY and percent is not None:
        errors.setdefault(f"{prefix}_percent", []).append(
            str(_("fixed_only basis cannot include a percentage."))
        )
    if basis == CommissionBasis.FIXED_ONLY and fixed is None:
        errors.setdefault(f"{prefix}_fixed_amount", []).append(
            str(_("fixed_only basis requires a fixed amount."))
        )
    if has_money and side.payee_id is None:
        errors.setdefault(f"{prefix}_payee", []).append(
            str(
                _("A payee is required when %(role)s financial terms are set.")
                % {"role": side.role}
            )
        )
    if basis and not has_money:
        errors.setdefault(f"{prefix}_percent", []).append(
            str(_("Percent or fixed amount is required when a basis is set."))
        )
    if cap is not None and not has_money:
        errors.setdefault(f"{prefix}_cap_amount", []).append(
            str(_("A cap requires percent and/or fixed amount terms."))
        )

    if errors:
        raise ValidationError(errors)

    return SideTerms(
        role=side.role,
        percent=percent,
        fixed_amount=fixed,
        cap_amount=cap,
        basis=basis,
        payee_id=side.payee_id,
        notes=side.notes or "",
    )


def validate_split_terms(split: SplitTerms) -> SplitTerms:
    errors: dict[str, list[str]] = {}
    try:
        agent = quantize_percent(split.agent_split_percent)
    except ValidationError as exc:
        errors.setdefault("agent_split_percent", []).extend(exc.messages)
        agent = split.agent_split_percent
    try:
        office = quantize_percent(split.office_split_percent)
    except ValidationError as exc:
        errors.setdefault("office_split_percent", []).extend(exc.messages)
        office = split.office_split_percent
    try:
        fee_amount = quantize_money(split.transaction_fee_amount)
    except ValidationError as exc:
        errors.setdefault("transaction_fee_amount", []).extend(exc.messages)
        fee_amount = split.transaction_fee_amount
    try:
        fee_percent = quantize_percent(split.transaction_fee_percent)
    except ValidationError as exc:
        errors.setdefault("transaction_fee_percent", []).extend(exc.messages)
        fee_percent = split.transaction_fee_percent

    if (agent is None) ^ (office is None):
        errors.setdefault("agent_split_percent", []).append(
            str(_("Agent and office splits must both be set or both omitted."))
        )
    elif agent is not None and office is not None and agent + office != HUNDRED:
        errors.setdefault("agent_split_percent", []).append(
            str(_("Agent and office splits must sum to 100 percent."))
        )

    if errors:
        raise ValidationError(errors)

    return SplitTerms(
        agent_split_percent=agent,
        office_split_percent=office,
        transaction_fee_amount=fee_amount,
        transaction_fee_percent=fee_percent,
    )


def validate_contract_terms(terms: ContractTermsInput) -> ContractTermsInput:
    if terms.rule_version not in SUPPORTED_RULE_VERSIONS:
        raise ValidationError(
            {
                "rule_version": _("Unsupported calculation rule version %(version)s.")
                % {"version": terms.rule_version}
            }
        )
    split = validate_split_terms(terms.split)
    mentor = validate_side_terms(
        SideTerms(
            role="mentor",
            percent=terms.mentor.percent,
            fixed_amount=terms.mentor.fixed_amount,
            cap_amount=terms.mentor.cap_amount,
            basis=terms.mentor.basis,
            payee_id=terms.mentor.payee_id,
            notes=terms.mentor.notes,
        )
    )
    referral = validate_side_terms(
        SideTerms(
            role="referral",
            percent=terms.referral.percent,
            fixed_amount=terms.referral.fixed_amount,
            cap_amount=terms.referral.cap_amount,
            basis=terms.referral.basis,
            payee_id=terms.referral.payee_id,
            notes=terms.referral.notes,
        )
    )

    for side in (mentor, referral):
        if side.basis in {
            CommissionBasis.AGENT_SIDE_BEFORE_FEES,
            CommissionBasis.AGENT_SIDE_AFTER_FEES,
        } and (split.agent_split_percent is None or split.office_split_percent is None):
            raise ValidationError(
                {
                    f"{side.role}_basis": _(
                        "Agent-side bases require agent and office split percents."
                    )
                }
            )

    return ContractTermsInput(
        split=split,
        mentor=mentor,
        referral=referral,
        special_arrangements=terms.special_arrangements or "",
        rule_version=terms.rule_version,
    )
