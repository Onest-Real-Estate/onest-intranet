"""Small, safe shared-prop helpers for the authenticated application shell."""

from __future__ import annotations

import hashlib
import json
from typing import TypedDict
from urllib.parse import urlsplit

from django.conf import settings

from apps.user.services.role_assignments import EffectiveAccess


class HelpConfiguration(TypedDict):
    url: str | None


def help_configuration() -> HelpConfiguration:
    """Return only a configured HTTPS help destination.

    The browser never supplies or modifies this value. Invalid, relative, and
    credential-bearing URLs fail closed so the header can expose a disabled
    help entry point without rendering an unsafe external link.
    """

    value = str(getattr(settings, "HUB_HELP_URL", "")).strip()
    if not value:
        return {"url": None}
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return {"url": None}
    return {"url": value}


def authorization_version(access: EffectiveAccess) -> str:
    """Opaque version for detecting changes to the effective access context."""

    payload = {
        "companyWide": access.company_wide,
        "officeKeys": sorted(access.office_keys),
        "permissions": sorted(access.permissions),
        "regionKeys": sorted(access.region_keys),
        "roles": list(access.role_keys),
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]
