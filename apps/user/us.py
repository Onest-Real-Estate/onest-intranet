"""US-specific profile helpers (states, phone, ZIP)."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Includes DC — Onest serves the District of Columbia.
US_STATE_CHOICES: tuple[tuple[str, str], ...] = (
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DC", "District of Columbia"),
    ("DE", "Delaware"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
)

US_STATE_CODES = {code for code, _ in US_STATE_CHOICES}

# Optional +1, separators, or parentheses. Area/exchange cannot start with 0 or 1.
_US_PHONE_RE = re.compile(
    r"""
    ^
    (?:\+?1[\s.\-]?)?
    \(?(?P<area>[2-9]\d{2})\)?
    [\s.\-]?
    (?P<exchange>[2-9]\d{2})
    [\s.\-]?
    (?P<line>\d{4})
    $
    """,
    re.VERBOSE,
)

_US_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
_NRDS_RE = re.compile(r"^\d{8,9}$")


def normalize_us_phone(value: str) -> str:
    """Return ``(XXX) XXX-XXXX``, or raise ValidationError."""
    raw = (value or "").strip()
    if not raw:
        raise ValidationError(_("Enter a US phone number."), code="required")
    match = _US_PHONE_RE.fullmatch(raw)
    if not match:
        raise ValidationError(
            _("Enter a valid US phone number, e.g. (202) 555-0100."),
            code="invalid",
        )
    return f"({match['area']}) {match['exchange']}-{match['line']}"


def normalize_us_zip(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValidationError(_("Enter a ZIP code."), code="required")
    if not _US_ZIP_RE.fullmatch(raw):
        raise ValidationError(
            _("Enter a 5-digit ZIP code, or ZIP+4 (12345-6789)."),
            code="invalid",
        )
    return raw


def normalize_nrds(value: str) -> str:
    """NRDS IDs are 8–9 digits. Blank is allowed (optional field)."""
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if not _NRDS_RE.fullmatch(digits):
        raise ValidationError(
            _("Enter an 8- or 9-digit NRDS number."),
            code="invalid",
        )
    return digits
