"""Pure Decimal commission engine for mentor and referral deductions.

No database access. Prefer :func:`calculate_commission`, which validates then
computes. Results are deterministic for a given rule version + inputs.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.contract.calculations.rules import (
    BASIS_LABELS,
    SUPPORTED_RULE_VERSIONS,
    money_round,
)
from apps.contract.calculations.types import (
    CalculationResult,
    CalculationStep,
    ContractTermsInput,
    SideResult,
    SideTerms,
    TransactionInput,
)
from apps.contract.calculations.validation import (
    validate_contract_terms,
    validate_transaction_input,
)
from apps.contract.terms import HUNDRED, ZERO, CommissionBasis


def calculate_commission(
    transaction: TransactionInput,
    terms: ContractTermsInput,
) -> CalculationResult:
    """Validate then compute. Prefer this entry point from services/tests."""
    transaction = validate_transaction_input(transaction)
    terms = validate_contract_terms(terms)
    return _calculate(transaction, terms)


def _calculate(
    transaction: TransactionInput,
    terms: ContractTermsInput,
) -> CalculationResult:
    if terms.rule_version not in SUPPORTED_RULE_VERSIONS:
        raise ValidationError(
            {"rule_version": _("No calculator registered for this rule version.")}
        )

    steps: list[CalculationStep] = []
    explanation: list[str] = []
    gci = money_round(transaction.gross_commission)
    steps.append(
        CalculationStep(
            key="gross_commission",
            label="Gross commission income",
            amount=gci,
            detail=f"Transaction GCI quantized to cents: {gci} {transaction.currency}.",
        )
    )
    explanation.append(f"Gross commission income is {gci} {transaction.currency}.")

    agent_pct = terms.split.agent_split_percent
    office_pct = terms.split.office_split_percent
    if agent_pct is None or office_pct is None:
        agent_before = gci
        office_side = ZERO
        explanation.append(
            "No agent/office split configured; agent side before fees equals GCI."
        )
    else:
        agent_before = money_round(gci * agent_pct / HUNDRED)
        office_side = money_round(gci - agent_before)
        steps.append(
            CalculationStep(
                key="agent_office_split",
                label="Agent / office split",
                amount=agent_before,
                detail=(
                    f"Agent {agent_pct}% → {agent_before}; "
                    f"office {office_pct}% → {office_side}."
                ),
            )
        )
        explanation.append(
            f"Agent/office split {agent_pct}/{office_pct}% yields agent "
            f"{agent_before} and office {office_side} before fees."
        )

    fee_fixed = terms.split.transaction_fee_amount or ZERO
    fee_pct = terms.split.transaction_fee_percent or ZERO
    fee_from_percent = money_round(gci * fee_pct / HUNDRED) if fee_pct else ZERO
    transaction_fee = money_round(fee_fixed + fee_from_percent)
    agent_after = money_round(agent_before - transaction_fee)
    if agent_after < ZERO:
        raise ValidationError(
            {
                "transaction_fee": _(
                    "Transaction fee %(fee)s exceeds agent side before fees %(agent)s."
                )
                % {"fee": transaction_fee, "agent": agent_before}
            }
        )
    if transaction_fee:
        steps.append(
            CalculationStep(
                key="transaction_fee",
                label="Transaction fee",
                amount=transaction_fee,
                detail=(
                    f"Fixed {fee_fixed} + {fee_pct}% of GCI ({fee_from_percent}) "
                    f"= {transaction_fee}; agent after fees {agent_after}."
                ),
            )
        )
        explanation.append(
            f"Transaction fee {transaction_fee} leaves agent side after fees "
            f"at {agent_after}."
        )
    else:
        explanation.append(
            "No transaction fee; agent side after fees equals before fees."
        )

    bases: dict[str, Decimal] = {
        CommissionBasis.GROSS_COMMISSION: gci,
        CommissionBasis.AGENT_SIDE_BEFORE_FEES: agent_before,
        CommissionBasis.AGENT_SIDE_AFTER_FEES: agent_after,
        CommissionBasis.FIXED_ONLY: ZERO,
    }

    mentor = None
    if terms.mentor.has_financial_terms:
        mentor = _side_deduction(terms.mentor, bases)
        steps.extend(mentor.steps)
        explanation.extend(_side_explanation(mentor))

    referral = None
    if terms.referral.has_financial_terms:
        referral = _side_deduction(terms.referral, bases)
        steps.extend(referral.steps)
        explanation.extend(_side_explanation(referral))

    mentor_amount = mentor.amount if mentor else ZERO
    referral_amount = referral.amount if referral else ZERO
    agent_net = money_round(agent_after - mentor_amount - referral_amount)
    if agent_net < ZERO:
        raise ValidationError(
            {
                "__all__": _(
                    "Mentor (%(mentor)s) and referral (%(referral)s) deductions "
                    "exceed agent side after fees (%(agent)s)."
                )
                % {
                    "mentor": mentor_amount,
                    "referral": referral_amount,
                    "agent": agent_after,
                }
            }
        )

    steps.append(
        CalculationStep(
            key="agent_net",
            label="Agent net after mentor and referral",
            amount=agent_net,
            detail=(
                f"{agent_after} − mentor {mentor_amount} − referral "
                f"{referral_amount} = {agent_net}."
            ),
        )
    )
    explanation.append(
        f"Agent net is {agent_net} {transaction.currency} after separate mentor "
        f"({mentor_amount}) and referral ({referral_amount}) deductions."
    )
    explanation.append(
        f"Office net remains {office_side} {transaction.currency} "
        "(mentor and referral do not increase the office share)."
    )

    intermediates = {
        "grossCommission": format(gci, "f"),
        "agentSideBeforeFees": format(agent_before, "f"),
        "agentSideAfterFees": format(agent_after, "f"),
        "officeSide": format(office_side, "f"),
        "transactionFee": format(transaction_fee, "f"),
        "mentorAmount": format(mentor_amount, "f"),
        "referralAmount": format(referral_amount, "f"),
        "agentNet": format(agent_net, "f"),
        "officeNet": format(office_side, "f"),
    }

    return CalculationResult(
        rule_version=terms.rule_version,
        currency=transaction.currency,
        input_snapshot=transaction.to_snapshot(),
        terms_snapshot=terms.to_snapshot(),
        intermediates=intermediates,
        mentor=mentor,
        referral=referral,
        agent_net=agent_net,
        office_net=office_side,
        transaction_fee=transaction_fee,
        steps=tuple(steps),
        explanation=tuple(explanation),
    )


def _side_deduction(side: SideTerms, bases: dict[str, Decimal]) -> SideResult:
    basis = side.basis
    if basis not in bases:
        raise ValidationError(
            {
                f"{side.role}_basis": _("Unknown calculation basis %(basis)s.")
                % {"basis": basis}
            }
        )
    basis_amount = bases[basis]
    percent_component = ZERO
    if side.percent is not None and basis != CommissionBasis.FIXED_ONLY:
        percent_component = money_round(basis_amount * side.percent / HUNDRED)
    fixed_component = side.fixed_amount or ZERO
    uncapped = money_round(percent_component + fixed_component)
    cap_applied = False
    amount = uncapped
    if side.cap_amount is not None and amount > side.cap_amount:
        amount = money_round(side.cap_amount)
        cap_applied = True

    label = "Mentor" if side.role == "mentor" else "Referral"
    basis_label = BASIS_LABELS.get(basis, basis)
    step_list = [
        CalculationStep(
            key=f"{side.role}_basis",
            label=f"{label} basis ({basis_label})",
            amount=basis_amount,
            detail=f"{label} uses basis {basis} = {basis_amount}.",
        ),
        CalculationStep(
            key=f"{side.role}_components",
            label=f"{label} percent and fixed components",
            amount=uncapped,
            detail=(
                f"Percent component {percent_component} + fixed {fixed_component} "
                f"= {uncapped} before cap."
            ),
        ),
    ]
    if cap_applied:
        step_list.append(
            CalculationStep(
                key=f"{side.role}_cap",
                label=f"{label} cap applied",
                amount=amount,
                detail=f"Capped at {side.cap_amount}; result {amount}.",
            )
        )
    else:
        step_list.append(
            CalculationStep(
                key=f"{side.role}_amount",
                label=f"{label} deduction",
                amount=amount,
                detail=f"{label} deduction is {amount}.",
            )
        )

    return SideResult(
        role=side.role,
        basis=basis,
        basis_amount=basis_amount,
        percent_component=percent_component,
        fixed_component=fixed_component,
        uncapped_amount=uncapped,
        amount=amount,
        cap_applied=cap_applied,
        payee_id=side.payee_id,
        steps=tuple(step_list),
    )


def _side_explanation(side: SideResult) -> list[str]:
    label = "Mentor" if side.role == "mentor" else "Referral"
    basis_label = BASIS_LABELS.get(side.basis, side.basis)
    lines = [
        f"{label} deduction uses {basis_label} ({side.basis_amount}): "
        f"percent {side.percent_component} + fixed {side.fixed_component} "
        f"= {side.uncapped_amount} before cap."
    ]
    if side.cap_applied:
        lines.append(
            f"{label} cap applied; final {label.lower()} amount is {side.amount}."
        )
    else:
        lines.append(f"{label} deduction is {side.amount}.")
    return lines


def summarize_terms_for_display(terms: ContractTermsInput) -> list[str]:
    """Human-readable lines that keep mentor and referral distinctly labeled."""
    terms = validate_contract_terms(terms)
    lines: list[str] = []
    split = terms.split
    if split.agent_split_percent is not None and split.office_split_percent is not None:
        lines.append(
            f"Agent/office split: {split.agent_split_percent}/"
            f"{split.office_split_percent}%."
        )
    if split.transaction_fee_amount or split.transaction_fee_percent:
        lines.append(
            "Transaction fee: "
            f"fixed {split.transaction_fee_amount or ZERO}, "
            f"percent {split.transaction_fee_percent or ZERO}%."
        )
    lines.extend(_summarize_side(terms.mentor))
    lines.extend(_summarize_side(terms.referral))
    if terms.special_arrangements:
        lines.append(f"Special arrangements: {terms.special_arrangements}")
    return lines


def _summarize_side(side: SideTerms) -> list[str]:
    if not side.has_financial_terms:
        return []
    label = "Mentor" if side.role == "mentor" else "Referral"
    basis_label = BASIS_LABELS.get(side.basis, side.basis or "unspecified")
    parts = [f"{label} deduction — basis {basis_label}"]
    if side.percent is not None:
        parts.append(f"{side.percent}%")
    if side.fixed_amount is not None:
        parts.append(f"fixed {side.fixed_amount}")
    if side.cap_amount is not None:
        parts.append(f"cap {side.cap_amount}")
    if side.payee_id is not None:
        parts.append(f"payee #{side.payee_id}")
    return ["; ".join(parts) + "."]
