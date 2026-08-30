"""Merge, deduplicate, and bucket agenda rows deterministically.

The one rule this module exists to enforce: **past-due work never sorts into the
future.** An agenda that quietly files a missed 9am deadline among tomorrow's
appointments has not just mis-ordered a list, it has hidden the only row that
needed action. Overdue rows are therefore a separate bucket, not a sort key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, tzinfo

from django.utils import timezone as dj_timezone

from apps.web.my_day.contract import AgendaEvent


class Bucket:
    OVERDUE = "overdue"
    TODAY = "today"
    UPCOMING = "upcoming"


def local_date_of(event: AgendaEvent, *, tz: tzinfo) -> date:
    """The calendar day this row belongs to, in the reader's timezone.

    An all-day row carries its own date because it never had a clock time to
    convert; converting a synthesized midnight would move "all day Friday" to
    Thursday for any reader west of where it was created.
    """
    if event.all_day and event.local_date is not None:
        return event.local_date
    return dj_timezone.localtime(event.start_at, tz).date()


def is_overdue(event: AgendaEvent, *, now: datetime, tz: tzinfo) -> bool:
    """Past its moment, and therefore not something still ahead today.

    An all-day row is overdue only once its whole date has passed: "all day
    today" is not late at 9am, which a plain ``start_at < now`` comparison
    against a synthesized midnight would claim.
    """
    if event.all_day:
        return local_date_of(event, tz=tz) < dj_timezone.localtime(now, tz).date()
    return (event.end_at or event.start_at) < now


def sort_key(event: AgendaEvent, *, tz: tzinfo) -> tuple:
    """Chronological, with all-day rows leading their own date.

    Priority appears last and only ever separates two rows at the same instant.
    An agenda reordered by importance stops being a chronology, and a reader
    scanning for "what is next" would have to read every row to find it.
    """
    return (
        local_date_of(event, tz=tz),
        0 if event.all_day else 1,
        event.start_at,
        event.priority,
        event.id,
    )


def dedupe(events: list[AgendaEvent]) -> list[AgendaEvent]:
    """Keep the first row per dedupe key, after the caller has sorted.

    This is what stops a synchronized calendar doubling somebody's day: the
    hub's own meeting and its Outlook mirror share a key, so enabling the
    integration adds detail rather than duplicates. Deterministic input order
    makes the survivor stable between requests.
    """
    seen: set[str] = set()
    unique: list[AgendaEvent] = []
    for event in events:
        if event.dedupe_key in seen:
            continue
        seen.add(event.dedupe_key)
        unique.append(event)
    return unique


@dataclass(frozen=True)
class Agenda:
    """The three buckets, each already ordered."""

    overdue: list[AgendaEvent]
    today: list[AgendaEvent]
    upcoming: list[AgendaEvent]

    @property
    def total(self) -> int:
        return len(self.overdue) + len(self.today) + len(self.upcoming)

    def capped(self, limit: int) -> Agenda:
        """Trim to ``limit`` rows across the buckets, overdue first.

        Overdue and today are filled before upcoming, so a cap can drop a
        distant appointment but never a missed one — the opposite would hide
        exactly the row the reader most needs.
        """
        if limit <= 0 or self.total <= limit:
            return self
        remaining = limit
        kept: dict[str, list[AgendaEvent]] = {}
        for name, rows in (
            ("overdue", self.overdue),
            ("today", self.today),
            ("upcoming", self.upcoming),
        ):
            kept[name] = rows[:remaining]
            remaining -= len(kept[name])
        return Agenda(**kept)


def build_agenda(events: list[AgendaEvent], *, now: datetime, tz: tzinfo) -> Agenda:
    """Order once, then split — so every bucket shares one comparison basis."""
    ordered = dedupe(sorted(events, key=lambda event: sort_key(event, tz=tz)))
    today = dj_timezone.localtime(now, tz).date()

    overdue: list[AgendaEvent] = []
    todays: list[AgendaEvent] = []
    upcoming: list[AgendaEvent] = []
    for event in ordered:
        if is_overdue(event, now=now, tz=tz):
            overdue.append(event)
        elif local_date_of(event, tz=tz) == today:
            todays.append(event)
        else:
            upcoming.append(event)
    return Agenda(overdue=overdue, today=todays, upcoming=upcoming)
