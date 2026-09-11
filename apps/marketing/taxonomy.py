"""Governed marketing asset vocabulary."""

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
    CategorySeed("logos", "Logos", "Approved logos and marks.", 10),
    CategorySeed(
        "guidelines",
        "Guidelines",
        "Brand and style guidelines.",
        20,
    ),
    CategorySeed(
        "templates",
        "Templates",
        "Editable and export templates.",
        30,
    ),
    CategorySeed("flyers", "Flyers", "Print and digital flyers.", 40),
    CategorySeed(
        "email_signatures",
        "Email signatures",
        "Approved email signature assets.",
        50,
    ),
    CategorySeed(
        "vendor_guidance",
        "Vendor guidance",
        "Vendor and partner marketing guidance.",
        60,
    ),
    CategorySeed(
        "campaign_assets",
        "Campaign assets",
        "Campaign kits and promotional assets.",
        70,
    ),
)

SYSTEM_CATEGORY_CODES = frozenset(item.code for item in CATEGORY_SEED)

ASSET_TYPE_LOGO = "logo"
ASSET_TYPE_GUIDELINE = "guideline"
ASSET_TYPE_TEMPLATE = "template"
ASSET_TYPE_FLYER = "flyer"
ASSET_TYPE_EMAIL_SIGNATURE = "email_signature"
ASSET_TYPE_VENDOR_GUIDANCE = "vendor_guidance"
ASSET_TYPE_CAMPAIGN = "campaign"

ASSET_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
    (ASSET_TYPE_LOGO, "Logo"),
    (ASSET_TYPE_GUIDELINE, "Guideline"),
    (ASSET_TYPE_TEMPLATE, "Template"),
    (ASSET_TYPE_FLYER, "Flyer"),
    (ASSET_TYPE_EMAIL_SIGNATURE, "Email signature"),
    (ASSET_TYPE_VENDOR_GUIDANCE, "Vendor guidance"),
    (ASSET_TYPE_CAMPAIGN, "Campaign asset"),
)

ASSET_TYPE_CODES = frozenset(code for code, _ in ASSET_TYPE_CHOICES)

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


def require_asset_type(value: str) -> str:
    code = (value or "").strip()
    if code not in ASSET_TYPE_CODES:
        raise ValidationError(_("Unknown asset type."))
    return code


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


def normalize_brand_codes(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(",", " ").split()]
    else:
        parts = [str(item).strip() for item in raw]
    codes: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in part.lower())
        slug = slug.strip("-_")[:40]
        if not slug or slug in seen:
            continue
        seen.add(slug)
        codes.append(slug)
    return sorted(codes)
