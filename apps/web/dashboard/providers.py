"""Widget providers.

One function per widget. Each takes a :class:`DashboardContext` — never a
client-supplied office or owner identifier — and returns a
:class:`~apps.web.dashboard.envelope.ProviderResult`.

Most modules this dashboard reports on do not exist yet. Those providers return
``unavailable`` and point at the hub section where the feature will live. That
is the whole point of this layer: the page is honest about what it does not
know, and it becomes useful one provider at a time as remaining domain modules
ship, with no change to the view or the page. Live today: performance metrics
(``web.metrics``), Quick Access, and Action Items (``web.action_items``, with
profile-backed sources and slots for contract/transaction/CRM modules), and
My Day (``web.my_day``, aggregating every registered calendar source).
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


def quick_access(context: DashboardContext) -> ProviderResult:
    """Launchers this reader may open, resolved from configuration.

    The panel used to be a tuple in this module, so retiring a vendor took a
    deploy. It is administered data now (``P1-025``): the audience rules live
    in :mod:`apps.web.quick_access.resolution`, and this provider only asks
    that module what the signed-in user may see. The office comes from the
    user record — never from a query parameter.

    A link whose internal destination has since left the allowlist resolves to
    an empty href and is dropped rather than rendered as a dead tile.

    The payload is bounded by the registry's ``feed_limit``, which the
    composer enforces and flags as ``meta.truncated``. The panel shows fewer
    still and offers "View all"; the registry cap is the outer bound on what an
    over-broad company-wide audience can push down the wire, not the product
    rule.
    """
    from apps.web.quick_access.catalog import DEFAULT_ICON, ICON_KEYS
    from apps.web.quick_access.resolution import visible_links_for

    queryset = visible_links_for(context.user, access=context.access, at=context.now)
    tools = []
    # Stop after one *safe* row past the cap. Counting database rows before
    # validating them lets one corrupt row hide a later approved launcher and
    # suppresses the composer's ``truncated`` bit.
    chunk_size = max(context.feed_limit + 1, 25)
    for link in queryset.iterator(chunk_size=chunk_size):
        href = link.href()
        if not href:
            continue
        tools.append(
            {
                "id": link.stable_key,
                "name": link.name,
                "description": link.description,
                "href": href,
                "icon": link.icon if link.icon in ICON_KEYS else DEFAULT_ICON,
                "external": link.is_external,
                "sso": link.sso_capability,
                "health": link.integration_health,
                "setup": link.setup_behavior,
            }
        )
        if context.feed_limit and len(tools) > context.feed_limit:
            break
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
    """The reader's own news band, straight from the announcement audience.

    Deliberately no scoping of its own: it calls the same
    ``apps.announcements.audience`` predicate the feed and the detail page use,
    so the band can never surface a story the feed would have withheld. The
    ordering is the feed's documented one — priority, then recency — so the
    featured slot is the most important thing addressed to this reader.
    """
    from apps.announcements.audience import visible_announcements
    from apps.announcements.services import order_for_feed

    limit = max(1, context.feed_limit or 5)
    rows = list(
        order_for_feed(visible_announcements(context.user, at=context.now))[:limit]
    )
    if not rows:
        return empty(
            "No announcements for you yet",
            "News addressed to you, your office, or the brokerage appears here.",
            action_label="Open announcements",
            action_href=reverse("announcements"),
        )
    # Hero artwork for the whole band in one query rather than one per card:
    # the band is five rows on every dashboard render, so a per-row lookup here
    # is a per-row cost on the hottest page in the hub.
    from apps.announcements.media_service import media_url
    from apps.announcements.models import AnnouncementMedia

    heroes = {
        media.announcement_id: media
        for media in AnnouncementMedia.objects.readable()
        .hero()
        .filter(announcement_id__in=[row.pk for row in rows])
    }
    cards = []
    for row in rows:
        hero = heroes.get(row.pk)
        cards.append(
            {
                "id": row.pk,
                "tag": row.category.label if row.category else "Announcement",
                "title": row.title,
                "excerpt": row.summary,
                "href": reverse("announcement_detail", args=[row.pk]),
                # A view path, not a durable link: it re-runs the announcement's
                # audience check on every request, so the band cannot hand out
                # artwork that outlives the reader's place in the audience. The
                # ``card`` derivative degrades to the original when processing
                # has not produced one, so a just-uploaded hero still renders.
                "imageUrl": media_url(hero, variant="card") if hero else None,
            }
        )
    return ready({"featured": cards[0], "items": cards[1:]})


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
        action_href=reverse("training_learning"),
    )


def my_day(context: DashboardContext) -> ProviderResult:
    """Every time-bound obligation this reader has, in one chronology.

    Sources live in ``apps.web.my_day``; this provider only supplies the day
    boundaries and asks the composer for the capped slice. Boundaries come from
    ``timeframes`` rather than being computed here, so the agenda's idea of
    "today" is the same one the greeting and every other provider use.
    """
    from apps.web.dashboard.timeframes import start_of_local_day, user_timezone
    from apps.web.my_day import day_for_user

    return day_for_user(
        context.user,
        context.access,
        now=context.now,
        tz=user_timezone(context.user),
        window_start=start_of_local_day(context.user, at=context.now),
        feed_limit=context.feed_limit,
    )


def action_items(context: DashboardContext) -> ProviderResult:
    """Prioritized queue of work assigned to or actionable by this reader.

    Domain sources live in ``apps.web.action_items``; this provider only asks
    the composer for the capped dashboard slice. Completion is derived from
    each source record — never stored or toggled here.
    """
    from apps.web.action_items import queue_for_user

    return queue_for_user(
        context.user,
        context.access,
        now=context.now,
        feed_limit=context.feed_limit,
    )


def overdue_inventory(context: DashboardContext) -> ProviderResult:
    """Overdue checked-out reservations in the reader's effective scope."""
    from apps.inventory.dashboard import overdue_inventory_queue

    return overdue_inventory_queue(context)


def market(context: DashboardContext) -> ProviderResult:
    return unavailable("No market data feed is connected to the hub yet.")


def quick_documents(context: DashboardContext) -> ProviderResult:
    return unavailable(
        "The document library is not connected to the hub yet.",
        action_label="Go to documents",
        action_href=_section_href("documents-forms"),
    )
