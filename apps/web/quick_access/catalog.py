"""Reviewed vocabulary for Quick Access links.

Three allowlists live here, and nothing outside them can reach a link record:

* **icons** — a link may only reference a mark the frontend already ships, so
  an administrator cannot point the dashboard at an arbitrary remote image.
* **internal destinations** — an internal link stores a key from this table,
  never a path. The path is produced by ``reverse()`` at render time, so a
  renamed route cannot turn into a broken or hijackable literal.
* **integration metadata** — SSO capability, health, and setup behaviour are
  closed choice sets rather than free text, because the dashboard renders them
  as badges and the onboarding module reads them later.

None of these values are secrets, and none of them may become one: a link
record never stores a credential, token, or tenant identifier. See
``docs/quick-access.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from django.urls import reverse

#: Marks the React launcher can draw. The key is stored; the component lives in
#: ``frontend/lib/quick-access-icons.ts`` and the two are pinned by a test.
QUICK_ACCESS_ICONS: tuple[tuple[str, str], ...] = (
    ("app-window", "Generic application"),
    # Vendors whose real artwork the frontend ships (see `BrandMarks.tsx`).
    # Pinned to that file by a test, so a key here without a mark there fails.
    ("microsoft", "Microsoft"),
    ("lofty", "Lofty"),
    ("skyslope", "SkySlope"),
    ("rpr", "RPR"),
    ("contact", "CRM / contacts"),
    ("shield-check", "Compliance"),
    ("signature", "E-signature"),
    ("file-text", "Documents & forms"),
    ("graduation-cap", "Training"),
    ("calendar", "Scheduling"),
    ("wallet", "Finance"),
    ("building", "Office"),
    ("life-buoy", "Support"),
    ("chart-line", "Reporting"),
)
ICON_KEYS: frozenset[str] = frozenset(key for key, _label in QUICK_ACCESS_ICONS)
DEFAULT_ICON = "app-window"


@dataclass(frozen=True)
class InternalDestination:
    """One allowlisted in-app destination, addressed by key rather than path."""

    key: str
    label: str
    route_name: str
    args: tuple[str, ...] = ()

    def href(self) -> str:
        return reverse(self.route_name, args=self.args)


def _hub_destinations() -> tuple[InternalDestination, ...]:
    # Imported here rather than at module scope: ``web.models`` imports this
    # catalog, and the dashboard package imports ``web.models`` back.
    from apps.web.dashboard.sections import HUB_SECTIONS

    return tuple(
        InternalDestination(
            key=f"hub:{section}",
            label=title,
            route_name="coming_soon",
            args=(section,),
        )
        for section, title in HUB_SECTIONS.items()
    )


@lru_cache(maxsize=1)
def internal_destinations() -> tuple[InternalDestination, ...]:
    """Every allowlisted in-app destination. Fixed at import of the URL conf."""
    return (
        InternalDestination(key="dashboard", label="Dashboard", route_name="dashboard"),
        InternalDestination(key="profile", label="My profile", route_name="profile"),
        *_hub_destinations(),
    )


@lru_cache(maxsize=1)
def internal_destination_by_key() -> dict[str, InternalDestination]:
    return {item.key: item for item in internal_destinations()}


def internal_destination_keys() -> frozenset[str]:
    return frozenset(internal_destination_by_key())


def internal_destination_options() -> list[dict[str, str]]:
    return [
        {"value": item.key, "label": item.label}
        for item in sorted(internal_destinations(), key=lambda item: item.label)
    ]


def icon_options() -> list[dict[str, str]]:
    return [{"value": key, "label": label} for key, label in QUICK_ACCESS_ICONS]
