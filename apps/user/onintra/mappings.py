"""Legacy onintra identifiers mapped onto Hub offices, roles, and taxonomy."""

from __future__ import annotations

import json
import re
from typing import Any

from apps.announcements.taxonomy import (
    PRIORITY_IMPORTANT,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
)
from apps.user.roles import (
    ACCOUNTANT,
    BRANCH_ADMIN,
    BRANCH_MANAGER,
    BROKER_ADMIN,
    COMPLIANCE,
    IT_SUPPORT,
    MARKETING_TEAM,
    PRINCIPAL_BROKER,
    REALTOR,
    REGIONAL_ADMIN,
    REGIONAL_MANAGER,
    REGIONAL_TRANSACTION_COORDINATOR,
    SYSTEM_ADMIN,
    TRANSACTION_COORDINATOR,
    ScopeType,
)

HEAD_OFFICE_SLUG = "onest-head-office"

LEGACY_BRANCH_TO_REGION_ID: dict[int, int] = {
    1: 1,
    2: 1,
    3: 1,
    4: 2,
    5: 2,
    6: 2,
    7: 3,
    8: 3,
    9: 3,
    10: 3,
    11: 2,
}

LEGACY_BRANCH_TO_OFFICE_SLUG: dict[int, str] = {
    1: "harrisburg",
    2: "philadelphia",
    3: "pittsburgh",
    4: "fairfax-va",
    5: "maryland",
    6: "district-of-columbia",
    7: "connecticut",
    8: "massachusetts",
    9: "new-hampshire",
    10: "rhode-island",
    11: "charlottesville-va",
}

LEGACY_REGION_TO_ROLE_SCOPE_SLUG: dict[int, str] = {
    1: "region-mid-atlantic",
    2: "region-mid-atlantic",
    3: "region-new-england",
}

LEGACY_REGION_TO_AUDIENCE_OFFICE_SLUG: dict[int, str] = {
    1: "ro-pennsylvania",
    2: "region-mid-atlantic",
    3: "region-new-england",
}

LEGACY_STATE_TO_OFFICE_SLUGS: dict[int, tuple[str, ...]] = {
    1: ("fairfax-va", "charlottesville-va", "ro-virginia"),
    2: ("harrisburg", "philadelphia", "pittsburgh", "ro-pennsylvania"),
    3: ("connecticut",),
    4: ("massachusetts",),
    5: ("new-hampshire",),
    6: ("maryland",),
    7: ("rhode-island",),
    8: (),
    9: (),
    10: ("district-of-columbia",),
}

LEGACY_ROLE_TO_HUB_CODE: dict[int, str] = {
    1: SYSTEM_ADMIN,
    2: PRINCIPAL_BROKER,
    3: BROKER_ADMIN,
    4: TRANSACTION_COORDINATOR,
    5: BRANCH_MANAGER,
    6: BRANCH_ADMIN,
    7: REALTOR,
    8: MARKETING_TEAM,
    9: REGIONAL_MANAGER,
    13: REGIONAL_ADMIN,
    14: REGIONAL_TRANSACTION_COORDINATOR,
    15: ACCOUNTANT,
    16: COMPLIANCE,
    17: IT_SUPPORT,
}

COMPANY_SCOPE_ROLE_IDS = frozenset({1, 2, 3, 8, 15, 16, 17})
REGIONAL_SCOPE_ROLE_IDS = frozenset({9, 13, 14})
OFFICE_SCOPE_ROLE_IDS = frozenset({4, 5, 6, 7})

LEGACY_PRIORITY_TO_HUB: dict[str, str] = {
    "low": PRIORITY_NORMAL,
    "normal": PRIORITY_NORMAL,
    "high": PRIORITY_IMPORTANT,
    "critical": PRIORITY_URGENT,
}

_TAG_CATEGORY_HINTS: tuple[tuple[str, str], ...] = (
    ("training", "training_notice"),
    ("education", "training_notice"),
    ("webinar", "training_notice"),
    ("meeting", "event"),
    ("event", "event"),
    ("mortgage", "market_update"),
    ("market", "market_update"),
    ("mls", "compliance_update"),
    ("compliance", "compliance_update"),
    ("technology", "technology_notice"),
    ("office", "office_notice"),
)

_STATE_ZIP_RE = re.compile(
    r"^(?P<street>.+?)[,\s]+(?P<city>[A-Za-z .'-]+)\s+"
    r"(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)\s*$"
)


def infer_location_id(
    *,
    legacy_role_id: int,
    location_id: int | None,
    realtor_branch_id: int | None,
) -> int | None:
    if location_id is not None:
        return location_id
    if legacy_role_id in OFFICE_SCOPE_ROLE_IDS:
        return realtor_branch_id
    if legacy_role_id in REGIONAL_SCOPE_ROLE_IDS and realtor_branch_id is not None:
        return LEGACY_BRANCH_TO_REGION_ID.get(realtor_branch_id)
    return None


def hub_role_code(legacy_role_id: int | None) -> str | None:
    if legacy_role_id is None:
        return None
    return LEGACY_ROLE_TO_HUB_CODE.get(int(legacy_role_id))


def role_scope(
    legacy_role_id: int,
    location_id: int | None,
) -> tuple[str, str | None]:
    """Return ``(scope_type, office_slug_or_none)`` for a legacy assignment."""
    role_id = int(legacy_role_id)
    if role_id in COMPANY_SCOPE_ROLE_IDS:
        return ScopeType.COMPANY, None
    if location_id is None:
        raise KeyError(f"Legacy role_id={role_id} missing location_id")
    location = int(location_id)
    if role_id in REGIONAL_SCOPE_ROLE_IDS:
        slug = LEGACY_REGION_TO_ROLE_SCOPE_SLUG.get(location)
        if slug is None:
            raise KeyError(f"Unknown legacy region_id={location}")
        return ScopeType.REGION, slug
    if role_id in OFFICE_SCOPE_ROLE_IDS:
        slug = LEGACY_BRANCH_TO_OFFICE_SLUG.get(location)
        if slug is None:
            raise KeyError(f"Unknown legacy branch_id={location}")
        return ScopeType.OFFICE, slug
    raise KeyError(f"Unsupported legacy role_id={role_id}")


def map_priority(raw: str | None) -> str:
    if not raw:
        return PRIORITY_NORMAL
    return LEGACY_PRIORITY_TO_HUB.get(str(raw).strip().lower(), PRIORITY_NORMAL)


def map_tags_to_category(tags_raw: Any) -> str:
    tags = _parse_tags(tags_raw)
    haystack = " ".join(tag.lower() for tag in tags)
    for needle, category_code in _TAG_CATEGORY_HINTS:
        if needle in haystack:
            return category_code
    return "company_announcement"


def split_display_name(full_name: str) -> tuple[str, str, str]:
    cleaned = " ".join(full_name.split())
    if not cleaned:
        return "", "", ""
    parts = cleaned.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name, cleaned


def parse_mailing_address(raw: str | None) -> dict[str, str]:
    if not raw:
        return {
            "street_address": "",
            "city": "",
            "state": "",
            "zip_code": "",
        }
    text = " ".join(str(raw).split())
    match = _STATE_ZIP_RE.match(text)
    if match is None:
        return {
            "street_address": text,
            "city": "",
            "state": "",
            "zip_code": "",
        }
    return {
        "street_address": match.group("street").strip(" ,"),
        "city": match.group("city").strip(),
        "state": match.group("state"),
        "zip_code": match.group("zip"),
    }


def branch_slug(branch_id: int | None) -> str | None:
    if branch_id is None:
        return None
    return LEGACY_BRANCH_TO_OFFICE_SLUG.get(int(branch_id))


def region_slug(region_id: int | None) -> str | None:
    if region_id is None:
        return None
    return LEGACY_REGION_TO_AUDIENCE_OFFICE_SLUG.get(int(region_id))


def state_office_slugs(state_id: int | None) -> tuple[str, ...]:
    if state_id is None:
        return ()
    return LEGACY_STATE_TO_OFFICE_SLUGS.get(int(state_id), ())


def _parse_tags(raw: Any) -> list[str]:
    if raw in (None, "", "[]"):
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    text = str(raw).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return [text]
