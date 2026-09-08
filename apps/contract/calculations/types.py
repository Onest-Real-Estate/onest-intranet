"""Pure value objects for mentor/referral commission calculations.

No Django model or ORM imports — keep rendering and persistence outside.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from apps.contract.calculations.rules import CURRENT_RULE_VERSION, DEFAULT_CURRENCY


@dataclass(frozen=True, slots=True)
class SideTerms:
    """One independently configured mentor *or* referral deduction block."""

    role: str  # "mentor" | "referral"
    percent: Decimal | None = None
    fixed_amount: Decimal | None = None
    cap_amount: Decimal | None = None
    basis: str = ""
    payee_id: int | None = None
    notes: str = ""

    @property
    def is_configured(self) -> bool:
        return (
            self.percent is not None
            or self.fixed_amount is not None
            or bool(self.basis)
            or self.payee_id is not None
            or bool(self.notes)
        )

    @property
    def has_financial_terms(self) -> bool:
        return self.percent is not None or self.fixed_amount is not None

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "percent": _dec(self.percent),
            "fixedAmount": _dec(self.fixed_amount),
            "capAmount": _dec(self.cap_amount),
            "basis": self.basis,
            "payeeId": self.payee_id,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class SplitTerms:
    agent_split_percent: Decimal | None = None
    office_split_percent: Decimal | None = None
    transaction_fee_amount: Decimal | None = None
    transaction_fee_percent: Decimal | None = None

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "agentSplitPercent": _dec(self.agent_split_percent),
            "officeSplitPercent": _dec(self.office_split_percent),
            "transactionFeeAmount": _dec(self.transaction_fee_amount),
            "transactionFeePercent": _dec(self.transaction_fee_percent),
        }


@dataclass(frozen=True, slots=True)
class TransactionInput:
    """Per-deal figures supplied by a commission worksheet or preview."""

    gross_commission: Decimal
    currency: str = DEFAULT_CURRENCY

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "grossCommission": _dec(self.gross_commission),
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class ContractTermsInput:
    """Commercial terms frozen for a calculation (usually from a snapshot)."""

    split: SplitTerms = field(default_factory=SplitTerms)
    mentor: SideTerms = field(default_factory=lambda: SideTerms(role="mentor"))
    referral: SideTerms = field(default_factory=lambda: SideTerms(role="referral"))
    special_arrangements: str = ""
    rule_version: str = CURRENT_RULE_VERSION

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "ruleVersion": self.rule_version,
            "split": self.split.to_snapshot(),
            "mentor": self.mentor.to_snapshot(),
            "referral": self.referral.to_snapshot(),
            "specialArrangements": self.special_arrangements,
        }


@dataclass(frozen=True, slots=True)
class CalculationStep:
    key: str
    label: str
    amount: Decimal | None = None
    detail: str = ""

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "amount": _dec(self.amount),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class SideResult:
    role: str
    basis: str
    basis_amount: Decimal
    percent_component: Decimal
    fixed_component: Decimal
    uncapped_amount: Decimal
    amount: Decimal
    cap_applied: bool
    payee_id: int | None
    steps: tuple[CalculationStep, ...] = ()

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "basis": self.basis,
            "basisAmount": _dec(self.basis_amount),
            "percentComponent": _dec(self.percent_component),
            "fixedComponent": _dec(self.fixed_component),
            "uncappedAmount": _dec(self.uncapped_amount),
            "amount": _dec(self.amount),
            "capApplied": self.cap_applied,
            "payeeId": self.payee_id,
            "steps": [step.to_snapshot() for step in self.steps],
        }


@dataclass(frozen=True, slots=True)
class CalculationResult:
    """Deterministic outcome of one rule/input/terms combination."""

    rule_version: str
    currency: str
    input_snapshot: dict[str, Any]
    terms_snapshot: dict[str, Any]
    intermediates: dict[str, Any]
    mentor: SideResult | None
    referral: SideResult | None
    agent_net: Decimal
    office_net: Decimal
    transaction_fee: Decimal
    steps: tuple[CalculationStep, ...]
    explanation: tuple[str, ...]

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "ruleVersion": self.rule_version,
            "currency": self.currency,
            "input": self.input_snapshot,
            "terms": self.terms_snapshot,
            "intermediates": self.intermediates,
            "mentor": self.mentor.to_snapshot() if self.mentor else None,
            "referral": self.referral.to_snapshot() if self.referral else None,
            "agentNet": _dec(self.agent_net),
            "officeNet": _dec(self.office_net),
            "transactionFee": _dec(self.transaction_fee),
            "steps": [step.to_snapshot() for step in self.steps],
            "explanation": list(self.explanation),
        }

    def fingerprint_payload(self) -> dict[str, Any]:
        """Stable subset used for idempotent persistence lookups."""
        return {
            "ruleVersion": self.rule_version,
            "currency": self.currency,
            "input": self.input_snapshot,
            "terms": self.terms_snapshot,
        }


def _dec(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def result_as_dict(result: CalculationResult) -> dict[str, Any]:
    """Full structural dump (tests / debugging)."""
    return asdict(result)
