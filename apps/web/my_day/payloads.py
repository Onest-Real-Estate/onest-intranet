"""Serialize an ordered agenda for Inertia (camelCase).

Every time string is formatted **in the reader's timezone**, server-side. The
browser's clock is not consulted: a laptop still on last week's timezone would
otherwise disagree with the day boundaries the buckets were computed from, and
the two halves of the same card would contradict each other.
"""

from __future__ import annotations

from datetime import datetime, tzinfo

from django.utils import formats
from django.utils import timezone as dj_timezone

from apps.web.my_day.contract import (
    PRIORITY_KEYS,
    SOURCE_LABELS,
    STATUS_LABELS,
    AgendaEvent,
    EventStatus,
)
from apps.web.my_day.ordering import Agenda, is_overdue, local_date_of


def _clock(moment: datetime, *, tz: tzinfo) -> str:
    return formats.time_format(dj_timezone.localtime(moment, tz), "g:i a")


def time_label(event: AgendaEvent, *, tz: tzinfo) -> str:
    """What to print in the time column.

    An all-day row says so in words rather than showing a synthesized midnight,
    which reads as a real 12:00 am appointment.
    """
    if event.all_day:
        return "All day"
    start = _clock(event.start_at, tz=tz)
    if event.end_at is None or event.end_at == event.start_at:
        return start
    return f"{start} – {_clock(event.end_at, tz=tz)}"


def day_label(event: AgendaEvent, *, now: datetime, tz: tzinfo) -> str:
    """Which day a row sits on, relative to the reader's today."""
    today = dj_timezone.localtime(now, tz).date()
    day = local_date_of(event, tz=tz)
    delta = (day - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "Yesterday"
    return formats.date_format(day, "D, M j")


def serialize_event(event: AgendaEvent, *, now: datetime, tz: tzinfo) -> dict:
    return {
        "id": event.id,
        "dedupeKey": event.dedupe_key,
        "source": event.source,
        "sourceLabel": SOURCE_LABELS.get(event.source, "Event"),
        "title": event.title,
        # ISO instants travel alongside the rendered labels so a client can
        # group or test without re-deriving the timezone — never so it can
        # reformat them against the browser clock.
        "startAt": event.start_at.isoformat(),
        "endAt": event.end_at.isoformat() if event.end_at else None,
        "allDay": event.all_day,
        "localDate": local_date_of(event, tz=tz).isoformat(),
        "timeLabel": time_label(event, tz=tz),
        "dayLabel": day_label(event, now=now, tz=tz),
        # Whether the day needs saying at all. Decided here because the client
        # has no trustworthy "today" — and because comparing the rendered
        # label against the word "Today" would break the moment it is
        # translated.
        "isToday": (
            local_date_of(event, tz=tz) == dj_timezone.localtime(now, tz).date()
        ),
        "location": event.location,
        "status": event.status,
        # Tentative is said in words; confirmed needs no chip of its own, so it
        # carries an empty label rather than shouting the default state.
        "statusLabel": (
            STATUS_LABELS.get(event.status, "")
            if event.status != EventStatus.CONFIRMED
            else ""
        ),
        "priority": PRIORITY_KEYS[event.priority],
        "overdue": is_overdue(event, now=now, tz=tz),
        "context": event.context,
        "ctaLabel": event.cta_label,
        "ctaHref": event.cta_href,
    }


def serialize_agenda(
    agenda: Agenda,
    *,
    now: datetime,
    tz: tzinfo,
    total: int,
    view_all_href: str,
    view_all_label: str,
) -> dict:
    def rows(events: list[AgendaEvent]) -> list[dict]:
        return [serialize_event(event, now=now, tz=tz) for event in events]

    return {
        "dateLabel": formats.date_format(
            dj_timezone.localtime(now, tz).date(), "l, F j"
        ),
        "timezone": str(tz),
        "overdue": rows(agenda.overdue),
        "today": rows(agenda.today),
        "upcoming": rows(agenda.upcoming),
        #: Uncapped count, so "+3 more" is honest about what was trimmed.
        "total": total,
        "viewAllHref": view_all_href,
        "viewAllLabel": view_all_label,
    }
