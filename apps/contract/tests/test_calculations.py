"""Table-driven mentor/referral commission calculation tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.contract.calculations import (
    CURRENT_RULE_VERSION,
    ContractTermsInput,
    SideTerms,
    SplitTerms,
    TransactionInput,
    calculate_commission,
    summarize_terms_for_display,
)
from apps.contract.terms import CommissionBasis

GCI = Decimal("10000.00")


def _split(
    agent: str = "70", office: str = "30", fee: str | None = "100"
) -> SplitTerms:
    return SplitTerms(
        agent_split_percent=Decimal(agent),
        office_split_percent=Decimal(office),
        transaction_fee_amount=Decimal(fee) if fee is not None else None,
        transaction_fee_percent=None,
    )


def _side(
    role: str,
    *,
    percent: str | None = None,
    fixed: str | None = None,
    cap: str | None = None,
    basis: str = CommissionBasis.AGENT_SIDE_AFTER_FEES,
    payee_id: int = 1,
) -> SideTerms:
    return SideTerms(
        role=role,
        percent=Decimal(percent) if percent is not None else None,
        fixed_amount=Decimal(fixed) if fixed is not None else None,
        cap_amount=Decimal(cap) if cap is not None else None,
        basis=basis,
        payee_id=payee_id,
    )


def _terms(
    *,
    mentor: SideTerms | None = None,
    referral: SideTerms | None = None,
    split: SplitTerms | None = None,
    rule_version: str = CURRENT_RULE_VERSION,
) -> ContractTermsInput:
    return ContractTermsInput(
        split=split or _split(),
        mentor=mentor or SideTerms(role="mentor"),
        referral=referral or SideTerms(role="referral"),
        rule_version=rule_version,
    )


@pytest.mark.parametrize(
    ("basis", "expected_mentor"),
    [
        # GCI 10000; agent 70% = 7000; fee 100 → after fees 6900.
        (CommissionBasis.GROSS_COMMISSION, Decimal("1000.00")),  # 10% of 10000
        (CommissionBasis.AGENT_SIDE_BEFORE_FEES, Decimal("700.00")),  # 10% of 7000
        (CommissionBasis.AGENT_SIDE_AFTER_FEES, Decimal("690.00")),  # 10% of 6900
    ],
)
def test_mentor_bases_are_independent_of_referral(basis, expected_mentor):
    result = calculate_commission(
        TransactionInput(gross_commission=GCI),
        _terms(
            mentor=_side("mentor", percent="10", basis=basis),
            referral=_side(
                "referral",
                percent="5",
                basis=CommissionBasis.GROSS_COMMISSION,
                payee_id=2,
            ),
        ),
    )
    assert result.mentor is not None
    assert result.referral is not None
    assert result.mentor.amount == expected_mentor
    assert result.referral.amount == Decimal("500.00")
    # Parallel, not chained: referral still uses full GCI.
    assert result.mentor.basis != result.referral.basis or basis == (
        CommissionBasis.GROSS_COMMISSION
    )


def test_mentor_and_referral_on_same_basis_do_not_chain():
    """Both use agent-after-fees of 6900 — neither reduces the other's base."""
    result = calculate_commission(
        TransactionInput(gross_commission=GCI),
        _terms(
            mentor=_side("mentor", percent="10", payee_id=1),
            referral=_side("referral", percent="10", payee_id=2),
        ),
    )
    assert result.mentor is not None
    assert result.referral is not None
    assert result.mentor.amount == Decimal("690.00")
    assert result.referral.amount == Decimal("690.00")
    assert result.agent_net == Decimal("5520.00")  # 6900 - 690 - 690


def test_fixed_plus_percent_with_cap():
    result = calculate_commission(
        TransactionInput(gross_commission=GCI),
        _terms(
            mentor=_side(
                "mentor",
                percent="10",
                fixed="50",
                cap="500",
                basis=CommissionBasis.AGENT_SIDE_AFTER_FEES,
            )
        ),
    )
    # 10% of 6900 = 690 + 50 = 740 → capped at 500
    assert result.mentor is not None
    assert result.mentor.amount == Decimal("500.00")
    assert result.mentor.cap_applied is True


def test_fixed_only_basis():
    result = calculate_commission(
        TransactionInput(gross_commission=GCI),
        _terms(
            mentor=_side(
                "mentor",
                fixed="250.00",
                basis=CommissionBasis.FIXED_ONLY,
            )
        ),
    )
    assert result.mentor is not None
    assert result.mentor.amount == Decimal("250.00")
    assert result.mentor.percent_component == Decimal("0.00")


def test_zero_gross_and_zero_terms():
    result = calculate_commission(
        TransactionInput(gross_commission=Decimal("0")),
        _terms(split=_split(fee=None)),
    )
    assert result.agent_net == Decimal("0.00")
    assert result.mentor is None
    assert result.referral is None


def test_bankers_rounding_on_fractional_cents():
    # 70% of 100.015 → intermediate then quantized; use odd cent edge.
    result = calculate_commission(
        TransactionInput(gross_commission=Decimal("100.015")),
        _terms(
            split=_split(agent="70", office="30", fee=None),
            mentor=_side(
                "mentor",
                percent="10",
                basis=CommissionBasis.AGENT_SIDE_BEFORE_FEES,
            ),
        ),
    )
    # GCI rounds to 100.02 (HALF_EVEN from 100.015 → 100.02)
    assert result.intermediates["grossCommission"] == "100.02"
    assert result.mentor is not None
    assert result.mentor.amount == Decimal("7.00")  # 10% of 70.01


def test_deterministic_for_same_inputs():
    terms = _terms(
        mentor=_side("mentor", percent="8"),
        referral=_side("referral", percent="2", payee_id=9),
    )
    txn = TransactionInput(gross_commission=GCI)
    a = calculate_commission(txn, terms)
    b = calculate_commission(txn, terms)
    assert a.to_snapshot() == b.to_snapshot()
    assert a.fingerprint_payload() == b.fingerprint_payload()


def test_totals_reconcile_invariant():
    result = calculate_commission(
        TransactionInput(gross_commission=GCI),
        _terms(
            mentor=_side("mentor", percent="5"),
            referral=_side("referral", percent="3", payee_id=2),
        ),
    )
    mentor = result.mentor.amount if result.mentor else Decimal("0")
    referral = result.referral.amount if result.referral else Decimal("0")
    agent_after = Decimal(result.intermediates["agentSideAfterFees"])
    assert result.agent_net + mentor + referral == agent_after
    assert result.agent_net >= Decimal("0")
    assert mentor >= Decimal("0")
    assert referral >= Decimal("0")


def test_missing_payee_rejected():
    with pytest.raises(ValidationError) as exc:
        calculate_commission(
            TransactionInput(gross_commission=GCI),
            _terms(
                mentor=SideTerms(
                    role="mentor",
                    percent=Decimal("10"),
                    basis=CommissionBasis.GROSS_COMMISSION,
                    payee_id=None,
                )
            ),
        )
    assert "mentor_payee" in exc.value.message_dict


def test_unknown_basis_rejected():
    with pytest.raises(ValidationError) as exc:
        calculate_commission(
            TransactionInput(gross_commission=GCI),
            _terms(
                mentor=SideTerms(
                    role="mentor",
                    percent=Decimal("10"),
                    basis="made_up_basis",
                    payee_id=1,
                )
            ),
        )
    assert "mentor_basis" in exc.value.message_dict


def test_negative_gross_rejected():
    with pytest.raises(ValidationError):
        calculate_commission(
            TransactionInput(gross_commission=Decimal("-1")),
            _terms(),
        )


def test_unsupported_rule_version_rejected():
    with pytest.raises(ValidationError) as exc:
        calculate_commission(
            TransactionInput(gross_commission=GCI),
            _terms(rule_version="9.9.9"),
        )
    assert "rule_version" in exc.value.message_dict


def test_agent_side_basis_requires_split():
    with pytest.raises(ValidationError):
        calculate_commission(
            TransactionInput(gross_commission=GCI),
            _terms(
                split=SplitTerms(),
                mentor=_side(
                    "mentor",
                    percent="10",
                    basis=CommissionBasis.AGENT_SIDE_AFTER_FEES,
                ),
            ),
        )


def test_deductions_cannot_exceed_agent_side():
    with pytest.raises(ValidationError):
        calculate_commission(
            TransactionInput(gross_commission=GCI),
            _terms(
                mentor=_side("mentor", percent="80"),
                referral=_side("referral", percent="80", payee_id=2),
            ),
        )


def test_summary_labels_mentor_and_referral_separately():
    lines = summarize_terms_for_display(
        _terms(
            mentor=_side("mentor", percent="10"),
            referral=_side("referral", percent="5", payee_id=2),
        )
    )
    joined = "\n".join(lines)
    assert "Mentor deduction" in joined
    assert "Referral deduction" in joined
    assert joined.index("Mentor") < joined.index("Referral")


def test_explanation_keeps_roles_distinct():
    result = calculate_commission(
        TransactionInput(gross_commission=GCI),
        _terms(
            mentor=_side("mentor", percent="10"),
            referral=_side("referral", percent="5", payee_id=2),
        ),
    )
    text = "\n".join(result.explanation)
    assert "Mentor deduction" in text
    assert "Referral deduction" in text
