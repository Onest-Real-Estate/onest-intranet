"""Versioned commission calculation rules (brokerage/legal v1).

Policy sign-off for bases, order, and rounding is captured here and in
``docs/agent-contracts.md``. Changing ``CURRENT_RULE_VERSION`` must not silently
reinterpret issued contracts: each contract freezes ``calculation_rule_version``
at creation, and every persisted calculation stores that version with its
snapshots.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from apps.contract.terms import CommissionBasis

#: Semantic version of this calculation policy. Bump when order, bases, or
#: rounding semantics change. Historical rows keep the version they were run
#: under and are never auto-recalculated.
CURRENT_RULE_VERSION = "1.0.0"

SUPPORTED_RULE_VERSIONS: frozenset[str] = frozenset({CURRENT_RULE_VERSION})

CURRENCY_USD = "USD"
DEFAULT_CURRENCY = CURRENCY_USD
SUPPORTED_CURRENCIES: frozenset[str] = frozenset({CURRENCY_USD})

MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.001")
ROUNDING = ROUND_HALF_EVEN

#: Documented pipeline for rule ``1.0.0``. Mentor and referral are computed in
#: parallel from named shared bases — never chained off each other — so the
#: two deductions cannot be conflated.
#
#: 1. Validate transaction gross commission income (GCI) and contract terms.
#: 2. Quantize GCI to cents (ROUND_HALF_EVEN).
#: 3. Apply agent/office split to GCI → agent_side_before_fees, office_side.
#: 4. Compute transaction fee (fixed + percent-of-GCI), quantize, subtract from
#:    agent side → agent_side_after_fees (floor at zero).
#: 5. Resolve mentor basis amount; apply percent and/or fixed; apply cap;
#:    quantize → mentor_amount (requires payee when non-zero terms).
#: 6. Resolve referral basis amount independently the same way → referral_amount.
#: 7. Agent net = agent_side_after_fees − mentor − referral (must stay ≥ 0).
#: 8. Office net = office_side (fees and mentor/referral do not increase office).
CALCULATION_ORDER_V1: tuple[str, ...] = (
    "validate_inputs",
    "quantize_gross_commission",
    "apply_agent_office_split",
    "apply_transaction_fee",
    "compute_mentor_deduction",
    "compute_referral_deduction",
    "reconcile_agent_net",
    "build_explanation",
)

BASIS_LABELS: dict[str, str] = {
    CommissionBasis.GROSS_COMMISSION: "gross commission income",
    CommissionBasis.AGENT_SIDE_BEFORE_FEES: "agent side before fees",
    CommissionBasis.AGENT_SIDE_AFTER_FEES: "agent side after fees",
    CommissionBasis.FIXED_ONLY: "fixed amount only",
}


def money_round(value: Decimal) -> Decimal:
    """Round a money amount to cents with the documented banker's rule."""
    return value.quantize(MONEY_QUANTUM, rounding=ROUNDING)


def percent_round(value: Decimal) -> Decimal:
    """Round a percentage to three decimal places (policy precision)."""
    return value.quantize(PERCENT_QUANTUM, rounding=ROUNDING)
