"""Widget providers.

One function per widget. Each takes a :class:`DashboardContext` — never a
client-supplied office or owner identifier — and returns a
:class:`~apps.web.dashboard.envelope.ProviderResult`.

Most modules this dashboard reports on do not exist yet. Those providers return
``unavailable`` and point at the hub section where the feature will live. That
is the whole point of this layer: the page is honest about what it does not
know, and it becomes useful one provider at a time as
`P1-022`–`P1-027` land, with no change to the view or the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.urls import reverse

from apps.user.models import User
from apps.user.services.role_assignments import EffectiveAccess
from apps.web.dashboard.envelope import ProviderResult, empty, ready, unavailable
from apps.web.metrics import dashboard_metrics


@dataclass(frozen=True)
class DashboardContext:
    """Everything a provider may read.

    ``access`` is resolved once per request from the role-assignment service and
    shared across providers, so scoping nine widgets costs one access lookup
    rather than nine.
    """

    user: User
    access: EffectiveAccess
    now: datetime
    #: Registry-declared cap for feed-shaped payloads; enforced by the composer.
    feed_limit: int = 0


def _section_href(section: str) -> str:
    return reverse("coming_soon", args=[section])


# --------------------------------------------------------------------------- #
# Live providers
# --------------------------------------------------------------------------- #


def performance(context: DashboardContext) -> ProviderResult:
    """Headline figures, selected and scoped by the metric registry.

    Selection and calculation both live in ``web.metrics``; this provider only
    decides whether the user got any figures at all.
    """
    payload = dashboard_metrics(
        context.user,
        at=context.now,
        access=context.access,
    )
    if not payload["groups"]:
        return empty(
            "No metrics for your role yet",
            "Figures appear here as your role and office scope are set up.",
        )
    return ready(payload)


#: Vendor tools every agent signs into. Reviewed configuration, not sample
#: data: these are the brokerage's actual systems, and the list changes by
#: commit rather than by request. ``enabled`` flips a launcher off without
#: removing the row, so a retired tool leaves an audit trail in the diff.
QUICK_ACCESS_TOOLS: tuple[dict[str, object], ...] = (
    {"id": "lofty", "name": "Lofty", "href": "https://www.lofty.com", "enabled": True},
    {
        "id": "skyslope",
        "name": "SkySlope",
        "href": "https://www.skyslope.com",
        "enabled": True,
    },
    {
        "id": "microsoft365",
        "name": "Microsoft 365",
        "href": "https://www.microsoft365.com",
        "enabled": True,
    },
    {
        "id": "dotloop",
        "name": "Dotloop",
        "href": "https://www.dotloop.com",
        "enabled": True,
    },
)


def quick_access(context: DashboardContext) -> ProviderResult:
    tools = [
        {"id": tool["id"], "name": tool["name"], "href": tool["href"]}
        for tool in QUICK_ACCESS_TOOLS
        if tool["enabled"]
    ]
    if not tools:
        return empty(
            "No tools configured",
            "Ask an administrator to add the systems your office uses.",
        )
    return ready(tools)


# --------------------------------------------------------------------------- #
# Providers awaiting their module
#
# Each states plainly what is missing and, where one exists, links to the hub
# section that will hold it. ``retryable=False``: asking again will not build
# the module, so the page offers a destination instead of a reload button.
# --------------------------------------------------------------------------- #


def announcements(context: DashboardContext) -> ProviderResult:
    return unavailable(
        "Company news is not published through the hub yet.",
        action_label="Browse office info",
        action_href=_section_href("office-info"),
    )


def active_transactions(context: DashboardContext) -> ProviderResult:
    return unavailable(
        "Transactions are not connected to the hub yet.",
        action_label="Go to transactions",
        action_href=_section_href("agent-transactions"),
    )


def training(context: DashboardContext) -> ProviderResult:
    return unavailable(
        "Training progress is not tracked in the hub yet.",
        action_label="Go to training",
        action_href=_section_href("training-learning"),
    )


def my_day(context: DashboardContext) -> ProviderResult:
    return unavailable(
        "Your calendar is not connected to the hub yet.",
        action_label="Go to reservations",
        action_href=_section_href("my-reservations"),
    )


def action_items(context: DashboardContext) -> ProviderResult:
    return unavailable("Tasks are not connected to the hub yet.")


def market(context: DashboardContext) -> ProviderResult:
    return unavailable("No market data feed is connected to the hub yet.")


def quick_documents(context: DashboardContext) -> ProviderResult:
    return unavailable(
        "The document library is not connected to the hub yet.",
        action_label="Go to documents",
        action_href=_section_href("documents-forms"),
    )
