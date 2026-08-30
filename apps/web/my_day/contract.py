"""The agenda-event contract every calendar source speaks.

A source returns :class:`AgendaEvent` rows for the signed-in user. The composer
merges, deduplicates, orders, and buckets them — it owns no calendar of its own
and invents no record. A source that would emit a cancelled, private,
out-of-scope, or not-yet-real event must omit it instead.

Two ideas here are load-bearing and easy to get wrong:

**An all-day event is a date, not an instant.** It has no clock time to convert,
so storing one as midnight-in-some-zone and rendering it back is how "all day
Friday" becomes "Thursday 11pm" for a reader one zone west. ``all_day`` rows
therefore carry ``local_date`` and their ``start_at`` is only ever used as a
sort position within that date.

**Provenance is not authorization.** ``source_record_*`` exists so an operator
can trace a row, and ``cta_href`` points at a destination that re-authorizes the
reader on arrival. Neither is evidence that the reader may see the record — that
decision belongs to the source's own queryset, before the row is ever built.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


class EventSource:
    """Where a row came from. Closed set: it appears in payloads and tests.

    Membership here does not mean the module exists yet — see
    ``registry.EVENT_SOURCE_DEFINITIONS``, where an unbuilt module stays
    ``available=False`` and is never called.
    """

    TASK = "operational_task"
    TRAINING = "training"
    CONSULTATION = "consultation"
    CLOSING = "closing"
    MEETING = "meeting"
    ROOM_BOOKING = "room_booking"
    INVENTORY = "inventory"
    MICROSOFT_CALENDAR = "microsoft_calendar"


EVENT_SOURCES: frozenset[str] = frozenset(
    {
        EventSource.TASK,
        EventSource.TRAINING,
        EventSource.CONSULTATION,
        EventSource.CLOSING,
        EventSource.MEETING,
        EventSource.ROOM_BOOKING,
        EventSource.INVENTORY,
        EventSource.MICROSOFT_CALENDAR,
    }
)

#: Human labels for the source chip. Presentation only — never authorize from
#: one, and never parse one back into a code.
SOURCE_LABELS: dict[str, str] = {
    EventSource.TASK: "Task",
    EventSource.TRAINING: "Training",
    EventSource.CONSULTATION: "Consultation",
    EventSource.CLOSING: "Closing",
    EventSource.MEETING: "Meeting",
    EventSource.ROOM_BOOKING: "Room",
    EventSource.INVENTORY: "Inventory",
    EventSource.MICROSOFT_CALENDAR: "Outlook",
}


class EventStatus:
    """Lifecycle of the underlying obligation.

    ``CANCELLED`` exists so a source can be explicit rather than silent, but it
    never reaches the wire: :func:`AgendaEvent.__post_init__` refuses one. A
    cancelled meeting that still renders is the failure this widget is most
    likely to be blamed for, so the contract makes it unrepresentable rather
    than relying on every source to remember to filter.
    """

    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


EVENT_STATUSES: frozenset[str] = frozenset(
    {EventStatus.CONFIRMED, EventStatus.TENTATIVE, EventStatus.CANCELLED}
)

STATUS_LABELS: dict[str, str] = {
    EventStatus.CONFIRMED: "Confirmed",
    EventStatus.TENTATIVE: "Tentative",
}


class EventVisibility:
    """Who the row may be shown to.

    ``PRIVATE`` is the same shape of refusal as ``CANCELLED``: representable so
    a source can classify honestly, refused by the constructor so it cannot be
    serialized. A private calendar entry belongs to its owner's own calendar,
    not to a hub widget that may be read over their shoulder.
    """

    NORMAL = "normal"
    PRIVATE = "private"


EVENT_VISIBILITIES: frozenset[str] = frozenset(
    {EventVisibility.NORMAL, EventVisibility.PRIVATE}
)


class EventPriority:
    """Lower sorts first, and only ever breaks a tie between equal times.

    Priority must not reorder a chronology: an agenda whose 2pm sits above its
    9am because somebody marked it important is no longer an agenda.
    """

    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


EVENT_PRIORITIES: frozenset[int] = frozenset(
    {
        EventPriority.CRITICAL,
        EventPriority.HIGH,
        EventPriority.NORMAL,
        EventPriority.LOW,
    }
)

PRIORITY_KEYS: dict[int, str] = {
    EventPriority.CRITICAL: "critical",
    EventPriority.HIGH: "high",
    EventPriority.NORMAL: "normal",
    EventPriority.LOW: "low",
}


@dataclass(frozen=True)
class AgendaEvent:
    """One time-bound obligation belonging to the signed-in user.

    ``id`` is stable across requests for the same obligation. ``dedupe_key``
    collapses the same real-world appointment arriving from two sources — the
    hub's own meeting record and its mirror in a synchronized calendar — to one
    row, so enabling an integration does not double somebody's day.
    """

    id: str
    dedupe_key: str
    source: str
    title: str
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    #: The calendar date an all-day row belongs to. Required for one, and
    #: meaningless for a timed row, whose date is read from ``start_at`` in the
    #: reader's own timezone.
    local_date: date | None = None
    location: str = ""
    status: str = EventStatus.CONFIRMED
    visibility: str = EventVisibility.NORMAL
    priority: int = EventPriority.NORMAL
    #: Supporting line — the office, the client, what the obligation is about.
    context: str = ""
    cta_label: str = ""
    #: Server-reversed, and pointing at a destination that authorizes the
    #: reader again. Never a literal path and never a bare record id.
    cta_href: str = ""
    source_module: str = ""
    source_record_type: str = ""
    source_record_id: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.dedupe_key:
            raise ValueError("Agenda events need a stable id and dedupe_key")
        if self.source not in EVENT_SOURCES:
            raise ValueError(f"Unknown agenda source: {self.source!r}")
        if self.status not in EVENT_STATUSES:
            raise ValueError(f"Unknown agenda status: {self.status!r}")
        if self.visibility not in EVENT_VISIBILITIES:
            raise ValueError(f"Unknown agenda visibility: {self.visibility!r}")
        if self.priority not in EVENT_PRIORITIES:
            raise ValueError(f"Unknown agenda priority: {self.priority!r}")
        if self.status == EventStatus.CANCELLED:
            raise ValueError(
                "A cancelled event must be omitted by its source, not emitted: "
                f"{self.id!r}"
            )
        if self.visibility == EventVisibility.PRIVATE:
            raise ValueError(
                "A private event must be omitted by its source, not emitted: "
                f"{self.id!r}"
            )
        if self.start_at.tzinfo is None:
            # A naive datetime has no instant. Accepting one would make the
            # row's position depend on whichever timezone happened to be
            # active when it was rendered.
            raise ValueError(f"Agenda events need an aware start_at: {self.id!r}")
        if self.end_at is not None:
            if self.end_at.tzinfo is None:
                raise ValueError(f"Agenda events need an aware end_at: {self.id!r}")
            if self.end_at < self.start_at:
                raise ValueError(f"Agenda event ends before it starts: {self.id!r}")
        if self.all_day and self.local_date is None:
            raise ValueError(
                f"An all-day event needs the date it belongs to: {self.id!r}"
            )
        if self.cta_href and not self.cta_label:
            raise ValueError(f"A CTA destination needs a label: {self.id!r}")


@dataclass(frozen=True)
class EventSourceContext:
    """Everything a source collector may read.

    The signed-in user, their pre-resolved effective access, the instant the
    page is being built for, and the window to answer within. Never an office,
    owner, or record id from the client — a collector that accepted one would
    make the widget a lookup tool for other people's calendars.
    """

    user: Any  # apps.user.models.User — avoided here to dodge a circular import
    access: Any  # EffectiveAccess
    now: datetime
    #: Inclusive lower bound: the start of the reader's current day. Overdue
    #: work from before it is fetched by its own source rule, not by widening
    #: this window backwards forever.
    window_start: datetime
    #: Exclusive upper bound of the agenda's forward reach.
    window_end: datetime
    timezone: Any  # tzinfo the reader's day boundaries were computed in
