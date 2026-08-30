"""Agenda source registry and the composer the dashboard provider calls.

Each domain registers a collector returning :class:`AgendaEvent` rows for the
signed-in user. A collector that raises is logged and skipped, so one broken
module cannot blank the whole agenda — the reader still sees every source that
answered, plus an honest note that something is missing.

Modules that do not exist yet are listed here with ``available=False``. They are
never called and cannot invent placeholder rows: an agenda that shows a meeting
nobody scheduled is worse than one that shows nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from django.urls import reverse

from apps.operational_tasks.agenda import collect_task_events
from apps.web.dashboard.envelope import ProviderResult, empty, ready, unavailable
from apps.web.my_day.contract import AgendaEvent, EventSource, EventSourceContext
from apps.web.my_day.ordering import build_agenda
from apps.web.my_day.payloads import serialize_agenda

logger = logging.getLogger(__name__)

EventCollector = Callable[[EventSourceContext], list[AgendaEvent]]

#: How far ahead the agenda reaches. A "my day" widget that answered for the
#: next month would stop being today's shape; a week is enough to show what is
#: coming without turning the card into a calendar.
FORWARD_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class EventSourceDefinition:
    """One calendar feed that can contribute rows."""

    key: str
    collector: EventCollector | None = None
    #: False while the module is registered but not yet connected. The
    #: collector is not called, so nothing can be fabricated on its behalf.
    available: bool = False


def _unbuilt(key: str) -> EventSourceDefinition:
    return EventSourceDefinition(key=key, collector=None, available=False)


EVENT_SOURCE_DEFINITIONS: tuple[EventSourceDefinition, ...] = (
    EventSourceDefinition(
        key=EventSource.TASK, collector=collect_task_events, available=True
    ),
    # Registered, deliberately dark. Each becomes available in the change that
    # ships its module — training sessions and required-training deadlines;
    # client consultations, closings, and internal meetings; room bookings and
    # inventory pickup/return windows (P1-050/P1-052, P1-056/P1-059).
    _unbuilt(EventSource.TRAINING),
    _unbuilt(EventSource.CONSULTATION),
    _unbuilt(EventSource.CLOSING),
    _unbuilt(EventSource.MEETING),
    _unbuilt(EventSource.ROOM_BOOKING),
    _unbuilt(EventSource.INVENTORY),
    # Microsoft calendar stays dark until the integration exists. Listing it
    # here is not a claim that anything synchronizes: an empty agenda must
    # never be read as "Outlook says you are free".
    _unbuilt(EventSource.MICROSOFT_CALENDAR),
)


def _validate_sources() -> None:
    seen: set[str] = set()
    for definition in EVENT_SOURCE_DEFINITIONS:
        if definition.key in seen:
            raise ValueError(f"Duplicate agenda source key: {definition.key}")
        if definition.available and definition.collector is None:
            raise ValueError(
                f"Agenda source {definition.key!r} is available with no collector"
            )
        seen.add(definition.key)


_validate_sources()


def collect_events(context: EventSourceContext) -> tuple[list[AgendaEvent], bool]:
    """Run every available source, isolating failures per source.

    Returns ``(events, partial_failure)``. The exception detail stays in the
    log: naming the source that failed would tell the reader which calendars
    they are subject to, which is more than the widget is entitled to say.
    """
    events: list[AgendaEvent] = []
    partial_failure = False
    for definition in EVENT_SOURCE_DEFINITIONS:
        if not definition.available or definition.collector is None:
            continue
        try:
            events.extend(definition.collector(context))
        except Exception:
            partial_failure = True
            logger.exception(
                "agenda_source_failed source=%s user_id=%s",
                definition.key,
                getattr(context.user, "pk", None),
            )
    return events, partial_failure


def _calendar_destination() -> tuple[str, str]:
    """Where "View full calendar" goes at this phase.

    The unified reservation/calendar page does not exist yet, so this resolves
    to the placeholder that names it honestly. When that page ships this is the
    single line that changes.
    """
    return "View full calendar", reverse(
        "coming_soon", kwargs={"section": "my-reservations"}
    )


def build_day(
    context: EventSourceContext,
    *,
    feed_limit: int = 0,
) -> ProviderResult:
    """Merge every source into the widget payload."""
    collected, partial_failure = collect_events(context)
    agenda = build_agenda(collected, now=context.now, tz=context.timezone)
    label, href = _calendar_destination()

    if agenda.total == 0 and partial_failure:
        # Nothing to show *and* something broke: say so, and let the page offer
        # a retry of this prop alone rather than claiming the day is clear.
        return unavailable(
            "Your agenda could not be loaded just now.",
            retryable=True,
            action_label=label,
            action_href=href,
        )
    if agenda.total == 0:
        return empty(
            "Nothing scheduled",
            "Bookings, deadlines, and appointments for the days ahead appear "
            "here as they are made.",
            action_label=label,
            action_href=href,
        )

    shown = agenda.capped(feed_limit) if feed_limit else agenda
    payload = serialize_agenda(
        shown,
        now=context.now,
        tz=context.timezone,
        total=agenda.total,
        view_all_href=href,
        view_all_label=label,
    )
    meta: dict = {}
    if partial_failure:
        # Opaque on purpose, and shown alongside the rows that did load: a
        # reader who is told "some sources are unavailable" knows not to treat
        # the list as complete.
        meta["partialFailure"] = True
    if shown.total < agenda.total:
        meta["truncated"] = True
    return ready(payload, **meta)


def day_for_user(
    user,
    access,
    *,
    now: datetime,
    tz: tzinfo,
    window_start: datetime,
    window_end: datetime | None = None,
    feed_limit: int = 0,
) -> ProviderResult:
    return build_day(
        EventSourceContext(
            user=user,
            access=access,
            now=now,
            window_start=window_start,
            window_end=window_end or (window_start + FORWARD_WINDOW),
            timezone=tz,
        ),
        feed_limit=feed_limit,
    )
