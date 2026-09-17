"""Governed documents-and-forms vocabulary."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class CategorySeed:
    code: str
    label: str
    description: str
    display_order: int


CATEGORY_SEED: tuple[CategorySeed, ...] = (
    CategorySeed("listing", "Listing", "Listing agreements and listing forms.", 10),
    CategorySeed("buyer", "Buyer", "Buyer representation and offer forms.", 20),
    CategorySeed(
        "seller",
        "Seller",
        "Seller representation and listing-side forms.",
        30,
    ),
    CategorySeed(
        "disclosure",
        "Disclosure",
        "Property, agency, and consumer disclosure forms.",
        40,
    ),
    CategorySeed("addendum", "Addendum", "Addenda and amendment forms.", 50),
    CategorySeed("rental", "Rental", "Lease and rental forms.", 60),
    CategorySeed("office", "Office", "Internal office and administrative forms.", 70),
    CategorySeed("other", "Other", "Forms that do not fit another category.", 80),
)

SYSTEM_CATEGORY_CODES = frozenset(item.code for item in CATEGORY_SEED)

_US_STATE_CODES = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    }
)


def normalize_jurisdiction_codes(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(",", " ").split()]
    else:
        parts = [str(item).strip() for item in raw]
    codes = sorted({part.upper() for part in parts if part})
    bad = [code for code in codes if code not in _US_STATE_CODES]
    if bad:
        raise ValidationError(
            _("Unknown jurisdiction codes: %(codes)s.") % {"codes": ", ".join(bad[:5])}
        )
    return codes
