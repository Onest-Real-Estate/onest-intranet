"""The reservation-summary contract every source domain speaks.

A source returns :class:`ReservationSummary` rows **for the signed-in user
only**. The composer merges, orders, and buckets them; it owns no reservation of
its own, invents no record, and writes nothing.

Three ideas here are load-bearing:

**Normalization is presentation, not authority.** ``display_status`` exists so
one page can sort a room booking beside an inventory hold without the reader
learning two vocabularies. The domain's own code and label travel alongside it
in ``source_status`` / ``status_label``, and every write goes back to the source
service. This page must never map a normalized status back into a domain one.

**An inventory window is a date; a room booking is an instant.** A pickup window
has no clock time to convert, so rendering it as midnight-in-some-zone is how
"Friday" becomes "Thursday 11pm" one zone west. Those rows carry ``all_day`` and
``local_date``; their ``starts_at`` is only ever a sort position.

**Provenance is not authorization.** ``source_id`` lets an operator trace a row
and ``detail_href`` points somewhere that re-authorizes the reader on arrival.
Neither is evidence the reader may see the record — that belongs to the source's
own queryset, before the row is built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from django.utils.translation import gettext_lazy as _


class ReservationSource:
    """Where a row came from. Closed set: it appears in payloads and tests."""

    ROOM = "room"
    INVENTORY = "inventory"


RESERVATION_SOURCES: frozenset[str] = frozenset(
    {ReservationSource.ROOM, ReservationSource.INVENTORY}
)

#: Source chip copy. Presentation only — never authorize from one, and never
#: parse one back into a code.
SOURCE_LABELS: dict[str, str] = {
    ReservationSource.ROOM: _("Room"),
    ReservationSource.INVENTORY: _("Equipment"),
}


class DisplayStatus:
    """The normalized vocabulary the unified page sorts and filters on.

    Deliberately coarser than either domain's lifecycle. It answers "what does
    the reader need to do about this", not "what state is the record in" — the
    domain answers that, in ``status_label``.
    """

    AWAITING_APPROVAL = "awaiting_approval"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    OVERDUE = "overdue"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DENIED = "denied"
    NEEDS_ATTENTION = "needs_attention"


DISPLAY_STATUSES: frozenset[str] = frozenset(
    {
        DisplayStatus.AWAITING_APPROVAL,
        DisplayStatus.CONFIRMED,
        DisplayStatus.IN_PROGRESS,
        DisplayStatus.OVERDUE,
        DisplayStatus.COMPLETED,
        DisplayStatus.CANCELLED,
        DisplayStatus.DENIED,
        DisplayStatus.NEEDS_ATTENTION,
    }
)

DISPLAY_STATUS_LABELS: dict[str, str] = {
    DisplayStatus.AWAITING_APPROVAL: _("Awaiting approval"),
    DisplayStatus.CONFIRMED: _("Confirmed"),
    DisplayStatus.IN_PROGRESS: _("In progress"),
    DisplayStatus.OVERDUE: _("Overdue"),
    DisplayStatus.COMPLETED: _("Completed"),
    DisplayStatus.CANCELLED: _("Cancelled"),
    DisplayStatus.DENIED: _("Denied"),
    DisplayStatus.NEEDS_ATTENTION: _("Needs attention"),
}

#: Tone per normalized status, resolved to the design system's chip pairs in the
#: page. Kept here so both the list and the calendar agree.
DISPLAY_STATUS_TONES: dict[str, str] = {
    DisplayStatus.AWAITING_APPROVAL: "warning",
    DisplayStatus.CONFIRMED: "success",
    DisplayStatus.IN_PROGRESS: "info",
    DisplayStatus.OVERDUE: "destructive",
    DisplayStatus.COMPLETED: "neutral",
    DisplayStatus.CANCELLED: "neutral",
    DisplayStatus.DENIED: "destructive",
    DisplayStatus.NEEDS_ATTENTION: "destructive",
}


class ReservationBucket:
    """Which tab a row belongs in. Derived, never stored."""

    UPCOMING = "upcoming"
    PAST = "past"
    CANCELLED = "cancelled"


RESERVATION_BUCKETS: tuple[str, ...] = (
    ReservationBucket.UPCOMING,
    ReservationBucket.PAST,
    ReservationBucket.CANCELLED,
)

#: Statuses that put a row in the Cancelled tab regardless of its time.
CLOSED_STATUSES: frozenset[str] = frozenset(
    {DisplayStatus.CANCELLED, DisplayStatus.DENIED}
)


@dataclass(frozen=True)
class ReservationAction:
    """One permitted action, always pointing at the owning domain's endpoint.

    ``method`` is ``get`` for a destination and ``post`` for a mutation. The
    unified page renders these; it never decides that an action is allowed —
    the source provider does, from the same rules the domain service enforces
    again when the request arrives.
    """

    key: str
    label: str
    href: str
    method: str = "get"
    #: Prompts a confirmation step before the request is sent.
    destructive: bool = False
    #: Domain state the mutation expects, so a stale tab cannot act on a record
    #: that moved on. Passed straight through to the source service.
    expected_status: str = ""


@dataclass(frozen=True)
class ReservationSummary:
    """One reservation, normalized for display and ordering."""

    source: str
    #: ``"<source>:<public id>"`` — traceable, and unique across domains.
    source_id: str
    public_id: str
    reference: str
    title: str
    office_name: str
    #: IANA zone the row's times must be rendered in.
    timezone: str
    starts_at: datetime
    ends_at: datetime
    display_status: str
    #: The domain's own code and label, carried through untranslated.
    source_status: str
    status_label: str
    subtitle: str = ""
    purpose: str = ""
    quantity: int | None = None
    instructions: str = ""
    contact: str = ""
    all_day: bool = False
    local_date: date | None = None
    detail_href: str = ""
    actions: tuple[ReservationAction, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.source not in RESERVATION_SOURCES:
            raise ValueError(f"Unknown reservation source: {self.source}")
        if self.display_status not in DISPLAY_STATUSES:
            raise ValueError(f"Unknown display status: {self.display_status}")
        if self.all_day and self.local_date is None:
            raise ValueError("An all-day reservation must carry its local date.")
        if self.ends_at < self.starts_at:
            raise ValueError("A reservation cannot end before it starts.")


def bucket_for(summary: ReservationSummary, *, now: datetime) -> str:
    """Which tab a row belongs in.

    Cancelled and denied rows leave the time axis entirely: a booking someone
    cancelled last week is not "past business", it is a record of a decision,
    and burying it among completed holds hides the thing the reader is looking
    for.
    """
    if summary.display_status in CLOSED_STATUSES:
        return ReservationBucket.CANCELLED
    if summary.display_status == DisplayStatus.OVERDUE:
        # Overdue is by definition past its return time, but it is the most
        # actionable row the reader has. It stays in Upcoming.
        return ReservationBucket.UPCOMING
    if summary.ends_at > now:
        return ReservationBucket.UPCOMING
    return ReservationBucket.PAST
