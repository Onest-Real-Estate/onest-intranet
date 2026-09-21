"""The reviewed Quick Create catalog — what a person may start from anywhere.

One registry, code-owned
------------------------
Every entry lives in :data:`QUICK_ACTIONS` and is a frozen dataclass: a stable
key, a label, an icon name, the permission it needs, the scopes it makes sense
in, the feature that must be live, and a **route name plus arguments** — never a
URL string and never a callable stored anywhere editable.

That last point is the security shape of this module. A destination is a
``route_name`` resolved through Django's own reverse at serialization time, so
an entry cannot name a path that does not exist, cannot be pointed at another
origin, and cannot be edited into an executable by anyone with database access.
Adding an action is a reviewed code change, which is the same bar the
navigation registry and the permission catalog already hold.

Filtered before serialization
-----------------------------
:func:`quick_actions_for` removes everything the actor cannot use — missing
permission, wrong scope, dark feature — *before* the payload is built, so an
unavailable action is absent from the props rather than hidden by CSS. That is
a disclosure control, not a convenience: the set of actions a person can see is
itself a description of what they are allowed to do.

Hiding is still never the enforcement. Every destination keeps its own
``enforce_policy`` entry, so a crafted navigation to an action this registry
would have withheld is refused by the endpoint exactly as if the menu had
offered it. The tests assert both halves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from django.urls import NoReverseMatch, reverse
from django.utils.http import urlencode

from apps.user.services.role_assignments import EffectiveAccess, get_effective_access
from apps.web.navigation import HUB_FEATURES

#: Scope shapes an action can require. ``any`` means the action makes sense
#: however the actor's grant is shaped — it still needs its permission.
Scope = Literal["any", "office", "region", "company", "assigned_record"]

#: Grouping shown as menu sections, in this order.
GROUP_ORDER: tuple[str, ...] = ("Agent", "Administration")


@dataclass(frozen=True)
class QuickAction:
    """One thing a person can start from the global menu.

    ``route_name`` and ``route_args`` are resolved with Django's reverse when
    the payload is built. Storing the *name* rather than a path means a URL
    change cannot leave a dead entry behind: ``pnpm run routes:generate`` and
    this registry move together, and an unknown name is dropped with a warning
    rather than serialized as a broken link.
    """

    key: str
    label: str
    description: str
    group: str
    icon: str
    permission: str
    route_name: str
    route_args: tuple[Any, ...] = ()
    #: Static query parameters appended to the reversed path. Code-owned like
    #: everything else here — this is how an action opens a create *drawer* on
    #: a list page rather than navigating to a standalone form.
    query: tuple[tuple[str, str], ...] = ()
    #: Feature key from ``HUB_FEATURES``. ``""`` means the action has no module
    #: behind it to switch off.
    feature: str = ""
    scopes: tuple[Scope, ...] = ("any",)
    #: Leaves the hub. Disclosed in the menu so a click is never a surprise.
    external: bool = False
    order: int = 100


QUICK_ACTIONS: tuple[QuickAction, ...] = (
    # --- Agent workflows -------------------------------------------------- #
    #
    # Only workflows whose hub section actually exists are registered. New
    # lead, buyer, and seller are named in the specification and are absent on
    # purpose: there is no leads, clients, or listings section in
    # ``HUB_SECTIONS`` yet, and inventing a feature key to hang them on would
    # put an action in the menu with no module behind it. They land in the
    # commit that registers their section — ``test_quick_actions`` fails on any
    # entry naming a feature key that does not exist, which is what keeps this
    # honest rather than a comment nobody rereads.
    QuickAction(
        key="new-transaction",
        label="New transaction",
        description="Open a transaction file.",
        group="Agent",
        icon="file-text",
        permission="web.create_own_transactions",
        route_name="transaction_new",
        feature="agent-transactions",
        order=40,
    ),
    QuickAction(
        key="new-transaction-ops",
        label="New transaction",
        description="Open a transaction file in your scope.",
        group="Administration",
        icon="file-text",
        permission="web.manage_transactions",
        route_name="transaction_new",
        feature="",
        order=35,
    ),
    QuickAction(
        key="reserve-room",
        label="Reserve a room",
        description="Book a room at your office.",
        group="Agent",
        icon="calendar-clock",
        permission="web.view_reservations",
        route_name="coming_soon",
        route_args=("my-reservations",),
        feature="my-reservations",
        scopes=("office", "region", "company"),
        order=50,
    ),
    QuickAction(
        key="reserve-inventory",
        label="Reserve inventory",
        description="Claim signage or marketing stock.",
        group="Agent",
        icon="package",
        permission="web.view_inventory",
        route_name="office_inventory",
        feature="office-inventory",
        scopes=("office", "region", "company"),
        order=60,
    ),
    # --- Administration --------------------------------------------------- #
    QuickAction(
        key="new-user",
        label="New user",
        description="Invite somebody into the brokerage.",
        group="Administration",
        icon="user-round-plus",
        permission="web.add_users",
        route_name="admin_add_user",
        feature="admin-add-user",
        order=10,
    ),
    QuickAction(
        key="new-announcement",
        label="New announcement",
        description="Draft a notice for your offices.",
        group="Administration",
        icon="megaphone",
        permission="web.manage_announcements",
        # The queue page with its create drawer open, not the standalone form:
        # the drawer keeps the list in view and hands off to the workspace once
        # the draft exists. ``?create=1`` is read by the index view.
        route_name="admin_announcements",
        query=(("create", "1"),),
        feature="admin-announcements",
        order=20,
    ),
    QuickAction(
        key="new-contract",
        label="New contract",
        description="Start an agent contract.",
        group="Administration",
        icon="file-signature",
        permission="web.view_agent_contracts",
        route_name="admin_agent_contracts",
        feature="admin-agent-contracts",
        order=30,
    ),
    QuickAction(
        key="new-inventory-item",
        label="New inventory item",
        description="Add stock for offices in your scope.",
        group="Administration",
        icon="package-plus",
        permission="web.view_inventory",
        route_name="admin_inventory",
        feature="admin-inventory",
        scopes=("office", "region", "company"),
        order=40,
    ),
    QuickAction(
        key="new-training",
        label="New training content",
        description="Publish a course or resource.",
        group="Administration",
        icon="graduation-cap",
        permission="web.manage_training",
        route_name="admin_training",
        feature="admin-training",
        order=50,
    ),
    QuickAction(
        key="new-document",
        label="New document",
        description="Share a document with your offices.",
        group="Administration",
        icon="file-plus",
        permission="web.manage_documents",
        route_name="admin_documents",
        feature="admin-documents",
        order=60,
    ),
    QuickAction(
        key="new-office-resource",
        label="New office resource",
        description="Publish an instruction, link, or file.",
        group="Administration",
        icon="folder-plus",
        permission="web.manage_office_resources",
        route_name="admin_office_resources",
        feature="admin-office-resources",
        order=70,
    ),
    QuickAction(
        key="new-room-block",
        label="New room block",
        description="Reserve a block of rooms for an office.",
        group="Administration",
        icon="calendar-range",
        permission="web.view_reservations",
        route_name="admin_reservations",
        feature="admin-reservations",
        scopes=("office", "region", "company"),
        order=80,
    ),
    QuickAction(
        key="new-support-task",
        label="New support task",
        description="Raise an IT or platform request.",
        group="Administration",
        icon="life-buoy",
        permission="web.view_it_support",
        route_name="admin_it_support",
        feature="admin-it-support",
        order=90,
    ),
    QuickAction(
        key="new-quick-access",
        label="New Quick Access link",
        description="Add a launcher to the dashboard.",
        group="Administration",
        icon="app-window",
        permission="web.manage_quick_access",
        route_name="admin_quick_access",
        query=(("create", "1"),),
        feature="admin-quick-access",
        order=100,
    ),
)

QUICK_ACTIONS_BY_KEY: dict[str, QuickAction] = {
    action.key: action for action in QUICK_ACTIONS
}

#: When the resolved set reaches this size the menu offers a search box. Below
#: it, searching a list you can read at a glance is friction, not help.
SEARCH_THRESHOLD = 8


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #


def actor_scopes(access: EffectiveAccess | None) -> frozenset[str]:
    """The scope shapes this actor's grant actually has.

    ``any`` is always present: it is the "no particular scope required" marker,
    not a scope the actor holds. Company-wide implies region and office reach —
    a brokerage administrator can obviously act on one office — so the wider
    grant fills in the narrower shapes rather than being a separate case every
    caller has to remember.
    """
    shapes: set[str] = {"any"}
    if access is None:
        return frozenset(shapes)
    if access.company_wide:
        shapes.update({"company", "region", "office"})
    if access.region_keys:
        shapes.update({"region", "office"})
    if access.office_keys:
        shapes.add("office")
    if access.assigned_record:
        shapes.add("assigned_record")
    return frozenset(shapes)


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def _destination(action: QuickAction) -> str | None:
    """Reverse the route, or ``None`` when the name no longer exists.

    A registry entry naming a route that has been renamed is dropped rather
    than serialized: an action that 404s is worse than an action that is
    absent, and the tests assert every entry reverses so this never fires
    silently in production.
    """
    try:
        path = reverse(action.route_name, args=action.route_args)
    except NoReverseMatch:
        return None
    if action.query:
        return f"{path}?{urlencode(action.query)}"
    return path


def is_available(
    action: QuickAction,
    *,
    permissions: frozenset[str] | set[str],
    scopes: frozenset[str],
    features: dict[str, bool],
) -> bool:
    """Three independent gates, all of which must pass.

    Order is deliberate: permission first, because it is the one that decides
    whether the person is allowed to know the action exists at all.
    """
    if action.permission not in permissions:
        return False
    if action.feature and not features.get(action.feature, False):
        return False
    return bool(set(action.scopes) & scopes)


def quick_actions_for(user, *, access: EffectiveAccess | None = None) -> list[dict]:
    """The actions this person may start, deduplicated and deterministically ordered.

    A multi-role user is the reason this returns a *set* union rather than a
    concatenation: two roles granting the same permission produce one entry,
    because the registry is keyed by action and consulted once, not walked per
    role. The order is ``group``, then the entry's own ``order``, then key — so
    the same person sees the same menu in the same sequence on every render.
    """
    from apps.web.navigation import hub_feature_states

    if not getattr(user, "is_authenticated", False):
        return []
    resolved = get_effective_access(user) if access is None else access
    permissions = set(resolved.permissions) if resolved else set()
    if getattr(user, "is_superuser", False):
        # A superuser holds every catalogued permission implicitly; the
        # registry still filters on feature and scope.
        permissions |= {action.permission for action in QUICK_ACTIONS}
    scopes = actor_scopes(resolved)
    features = hub_feature_states(user, permissions=permissions)

    available = [
        action
        for action in QUICK_ACTIONS
        if is_available(
            action, permissions=permissions, scopes=scopes, features=features
        )
    ]

    def sort_key(item: QuickAction) -> tuple[int, int, str]:
        group = (
            GROUP_ORDER.index(item.group)
            if item.group in GROUP_ORDER
            else len(GROUP_ORDER)
        )
        return (group, item.order, item.key)

    payload: list[dict] = []
    for action in sorted(available, key=sort_key):
        href = _destination(action)
        if href is None:
            continue
        payload.append(
            {
                "key": action.key,
                "label": action.label,
                "description": action.description,
                "group": action.group,
                "icon": action.icon,
                "href": href,
                "external": action.external,
            }
        )
    return payload


def quick_create_scope(user, access: EffectiveAccess | None) -> dict[str, str]:
    """Which offices these actions apply to, without spending a query.

    This rides on **every** Inertia response, so it is deliberately cheaper than
    ``operations.operations_scope_payload``: that one resolves region and office
    *names* with a database lookup, which is a query added to the hottest page in
    the hub for a line of subtitle text. Everything here comes from the access
    context the shell already resolved, plus ``user.office`` — the same related
    object ``primary_office_payload`` touches on the same instance, so Django's
    field cache answers the second read for free.

    The trade is a less specific label for a regional grant ("your region"
    rather than the region's name). Worth it: the sentence exists so somebody
    holding several hats knows which one is in play, and the level answers that.
    """
    if not getattr(user, "is_authenticated", False):
        return {"level": "none", "label": "No administrative scope"}
    if getattr(user, "is_superuser", False) or (access and access.company_wide):
        return {"level": "brokerage", "label": "the whole brokerage"}
    if access and access.region_keys:
        return {"level": "region", "label": "your region"}
    office = getattr(user, "office", None)
    if office is not None:
        return {"level": "office", "label": office.name}
    return {"level": "none", "label": "your own records"}


def quick_create_payload(user, *, access: EffectiveAccess | None = None) -> dict:
    """The whole shared prop: the actions plus the context the menu shows."""
    resolved = access
    if resolved is None and getattr(user, "is_authenticated", False):
        resolved = get_effective_access(user)
    actions = quick_actions_for(user, access=resolved)
    return {
        "actions": actions,
        # Named so the menu can say *which* offices an action will apply to,
        # rather than leaving the person to guess which hat they are wearing.
        "scope": quick_create_scope(user, resolved),
        "searchable": len(actions) >= SEARCH_THRESHOLD,
    }


# --------------------------------------------------------------------------- #
# Return destinations
# --------------------------------------------------------------------------- #


def safe_return_path(raw: str | None, *, fallback: str = "") -> str:
    """A same-origin path, or the fallback.

    Only a site-relative path survives. ``//host`` is refused because it looks
    relative and is not — it inherits the page's scheme and leaves the origin —
    and anything carrying a scheme or a control character is refused outright.
    Everything a caller might do with the result (a redirect, a "back" link) is
    an open-redirect if this is wrong, so it is deliberately narrow.
    """
    value = (raw or "").strip()
    if not value or not value.startswith("/") or value.startswith("//"):
        return fallback
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return fallback
    if "\\" in value:
        return fallback
    return value


def registered_features() -> frozenset[str]:
    """Feature keys the catalog depends on, for the registry consistency test."""
    return frozenset(action.feature for action in QUICK_ACTIONS if action.feature)


def unknown_feature_keys() -> frozenset[str]:
    return registered_features() - frozenset(HUB_FEATURES)
