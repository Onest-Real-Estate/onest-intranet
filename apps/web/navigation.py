"""Hub feature availability and primary-office context for the sidebar.

The navigation *structure* — labels, icons, order, grouping — lives in
``frontend/lib/hub-nav.ts``. This module owns the two facts the client must
not invent for itself:

* which agent and administrative modules are actually available (``HUB_FEATURES``), and
* which office the signed-in user belongs to (``primary_office_payload``).

Both ride along as Inertia shared props (see ``web.middleware``). Hiding a
link is a courtesy, never a control: every destination is still guarded by its
own ``enforce_policy`` entry in ``web.authorization``.
"""

from __future__ import annotations

from typing import Any, TypedDict, cast

from apps.user.models import User
from apps.user.services.role_assignments import get_effective_permissions
from apps.web.dashboard.sections import HUB_SECTIONS
from apps.web.operations import OPERATIONS_DESTINATIONS, OPERATIONS_FEATURES

# Agent keys match ``HUB_SECTIONS``; administrative keys come from the reviewed
# operations registry. Flip an entry to True only in the commit that ships its
# live destination. Missing entries fail closed; explicit false entries expose
# only the protected Soon route. Availability never changes its permission policy.
HUB_FEATURES: dict[str, bool] = {
    **dict.fromkeys(HUB_SECTIONS, False),
    **OPERATIONS_FEATURES,
}
HUB_FEATURES["announcements"] = True
HUB_FEATURES["office-info"] = True
HUB_FEATURES["office-resources"] = True
HUB_FEATURES["reports"] = True

# Live destinations that are not Coming Soon ops stubs and are not agent
# HUB_SECTIONS. Shared only when the actor holds the matching permission.
STANDALONE_FEATURES: dict[str, str] = {
    "reports": "web.view_reports",
}


class PrimaryOffice(TypedDict):
    id: int
    name: str
    regionName: str


def hub_feature_states(user=None, *, permissions=None) -> dict[str, bool]:
    """Availability filtered so unauthorized administrative keys are not shared."""
    states = {section: HUB_FEATURES[section] for section in HUB_SECTIONS}
    if not getattr(user, "is_authenticated", False):
        return states
    effective_permissions = (
        get_effective_permissions(cast(User, user))
        if permissions is None
        else permissions
    )
    states.update(
        {
            destination.feature: HUB_FEATURES[destination.feature]
            for destination in OPERATIONS_DESTINATIONS
            if destination.permission in effective_permissions
        }
    )
    for feature, permission in STANDALONE_FEATURES.items():
        if not HUB_FEATURES.get(feature):
            continue
        if permission in effective_permissions or getattr(user, "is_superuser", False):
            states[feature] = True
    return states


def primary_office_payload(user) -> PrimaryOffice | None:
    """The user's own office, or ``None`` when they have not got one.

    Derived solely from ``user.office``; no office identifier is ever accepted
    from the client. ``None`` covers both the ordinary pre-onboarding case and
    the data error where an onboarded user lost their office; office-scoped
    navigation then fails closed rather than rendering a dead destination.
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
        "features": hub_feature_states(user),
        "primaryOffice": primary_office_payload(user),
    }
