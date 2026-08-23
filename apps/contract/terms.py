"""Commission term vocabulary and decimal helpers.

Mentor and referral are modelled as *separate* structured term blocks so a
future calculation service cannot conflate bases, caps, or payees. All money
and percentage values use :class:`~decimal.Decimal` — never binary floats.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

# Percentages: 0.000–100.000 inclusive, three decimal places (basis points of a
# percent). Documented unit: percentage points of the named commercial base.
PERCENT_MAX_DIGITS = 6
PERCENT_DECIMAL_PLACES = 3
PERCENT_MIN = Decimal("0")
PERCENT_MAX = Decimal("100")

# Money: USD major units with cents. Documented currency: USD.
MONEY_MAX_DIGITS = 12
MONEY_DECIMAL_PLACES = 2
MONEY_MIN = Decimal("0")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


class CommissionBasis(models.TextChoices):
    """Stable calculation bases; product/legal may extend the set later."""

    GROSS_COMMISSION = "gross_commission", _("Gross commission income")
    AGENT_SIDE_BEFORE_FEES = "agent_side_before_fees", _("Agent side before fees")
    AGENT_SIDE_AFTER_FEES = "agent_side_after_fees", _("Agent side after fees")
    FIXED_ONLY = "fixed_only", _("Fixed amount only")


def quantize_percent(value: Decimal | str | int | float | None) -> Decimal | None:
    """Normalize a percentage to the stored precision, or ``None`` if empty."""
    if value is None or value == "":
        return None
    try:
        quantized = Decimal(str(value)).quantize(Decimal(10) ** -PERCENT_DECIMAL_PLACES)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(_("Enter a valid percentage.")) from exc
    if quantized < PERCENT_MIN or quantized > PERCENT_MAX:
        raise ValidationError(
            _("Percentage must be between %(min)s and %(max)s.")
            % {"min": PERCENT_MIN, "max": PERCENT_MAX}
        )
    return quantized


def quantize_money(value: Decimal | str | int | float | None) -> Decimal | None:
    """Normalize a USD amount to cents, or ``None`` if empty."""
    if value is None or value == "":
        return None
    try:
        quantized = Decimal(str(value)).quantize(Decimal(10) ** -MONEY_DECIMAL_PLACES)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(_("Enter a valid dollar amount.")) from exc
    if quantized < MONEY_MIN:
        raise ValidationError(_("Amount cannot be negative."))
    return quantized


def percent_field(**kwargs: Any) -> Any:
    """``DecimalField`` for percentage-point terms (unit: %)."""
    return models.DecimalField(
        max_digits=PERCENT_MAX_DIGITS,
        decimal_places=PERCENT_DECIMAL_PLACES,
        null=True,
        blank=True,
        help_text=_("Percentage points (0–100), three decimal places. Unit: percent."),
        **kwargs,
    )


def money_field(**kwargs: Any) -> Any:
    """``DecimalField`` for USD money terms (unit: USD)."""
    return models.DecimalField(
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
        null=True,
        blank=True,
        help_text=_("US dollars with cents. Currency: USD. Nonnegative."),
        **kwargs,
    )
