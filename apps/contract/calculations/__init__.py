"""Public calculation API for the contract domain."""

from apps.contract.calculations.engine import (
    calculate_commission,
    summarize_terms_for_display,
)
from apps.contract.calculations.rules import (
    CURRENT_RULE_VERSION,
    DEFAULT_CURRENCY,
    SUPPORTED_CURRENCIES,
    SUPPORTED_RULE_VERSIONS,
)
from apps.contract.calculations.types import (
    CalculationResult,
    ContractTermsInput,
    SideTerms,
    SplitTerms,
    TransactionInput,
)

__all__ = [
    "CURRENT_RULE_VERSION",
    "DEFAULT_CURRENCY",
    "SUPPORTED_CURRENCIES",
    "SUPPORTED_RULE_VERSIONS",
    "CalculationResult",
    "ContractTermsInput",
    "SideTerms",
    "SplitTerms",
    "TransactionInput",
    "calculate_commission",
    "summarize_terms_for_display",
]
