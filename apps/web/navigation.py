"""Hub feature availability and primary-office context for the sidebar.

The navigation *structure* — labels, icons, order, grouping — lives in
``frontend/lib/hub-nav.ts``. This module owns the two facts the client must
not invent for itself:

* which hub modules are actually built (``HUB_FEATURES``), and
* which office the signed-in user belongs to (``primary_office_payload``).

Both ride along as Inertia shared props (see ``web.middleware``). Hiding a
link is a courtesy, never a control: every destination is still guarded by its
own ``enforce_policy`` entry in ``web.authorization``.
"""

from __future__ import annotations

from typing import Any, TypedDict

from apps.web.dashboard import HUB_SECTIONS

# Keyed by the same slug as ``HUB_SECTIONS`` and the ``coming_soon`` route, so
# a section has exactly one name across the backend, the URL, and the nav
# registry. Flip an entry to True in the commit that ships its real route.
HUB_FEATURES: dict[str, bool] = dict.fromkeys(HUB_SECTIONS, False)


class PrimaryOffice(TypedDict):
    id: int
    name: str
    regionName: str


def hub_feature_states() -> dict[str, bool]:
    """Explicit availability per hub section — never inferred from the URL."""
    return dict(HUB_FEATURES)


def primary_office_payload(user) -> PrimaryOffice | None:
    """The user's own office, or ``None`` when they have not got one.

    Derived solely from ``user.office``; no office identifier is ever accepted
    from the client. ``None`` covers both the ordinary pre-onboarding case and
    the data error where an onboarded user lost their office, and the sidebar
    renders an explicit "office not set" state for it rather than a dead link.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    office = user.office
    if office is None:
        return None
    return {
        "id": office.id,
        "name": office.name,
        "regionName": office.region_name(),
    }


def navigation_context(user) -> dict[str, Any]:
    return {
        "features": hub_feature_states(),
        "primaryOffice": primary_office_payload(user),
    }
