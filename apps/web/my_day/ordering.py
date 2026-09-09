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
        """Trim to ``limit`` rows, giving every non-empty bucket a place.

        Priority still runs overdue → today → upcoming, so a cap drops a distant
        appointment before a missed one. But priority alone is not enough: filling
        greedily from the top lets a long backlog take the entire budget, and a
        card called "My day" that shows six overdue items from last month and
        nothing from today has failed at the one thing it is for.

        So each non-empty bucket is guaranteed one row while the budget allows,
        and only the remainder is distributed in priority order. Nothing is
        hidden silently either way — the header reports "shown of total".
        """
        if limit <= 0 or self.total <= limit:
            return self
        buckets: tuple[tuple[str, list[AgendaEvent]], ...] = (
            ("overdue", self.overdue),
            ("today", self.today),
            ("upcoming", self.upcoming),
        )
        allocation = dict.fromkeys((name for name, _ in buckets), 0)
        remaining = limit

        # A seat each, in priority order, so no bucket disappears entirely.
        for name, rows in buckets:
            if remaining == 0:
                break
            if rows:
                allocation[name] = 1
                remaining -= 1

        # Then the remainder, still overdue-first.
        for name, rows in buckets:
            if remaining == 0:
                break
            extra = min(len(rows) - allocation[name], remaining)
            allocation[name] += extra
            remaining -= extra

        return Agenda(**{name: rows[: allocation[name]] for name, rows in buckets})


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
