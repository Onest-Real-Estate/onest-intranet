"""Feedback vocabulary and its lifecycle.

Code-owned and closed, for the same reason the task module's is: a category or
status appears in URLs, audit payloads, and notification bodies, so the stable
machine code is stored and the label is presentation only.

The lifecycle is deliberately *shorter* than the operational task one. A
support ticket is a conversation with a person who is waiting: New → Triaged →
In progress → (Needs info) → Resolved → Closed. Anything more granular would
be staff-internal process leaking into a queue the submitter can also see.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


class FeedbackCategory:
    BUG = "bug"
    IDEA = "feature_idea"
    CONTENT = "content_correction"
    ACCESS = "access_issue"
    HELP = "general_help"


CATEGORY_LABELS: dict[str, str] = {
    FeedbackCategory.BUG: _("Something is broken"),
    FeedbackCategory.IDEA: _("Idea or improvement"),
    FeedbackCategory.CONTENT: _("Something is wrong or out of date"),
    FeedbackCategory.ACCESS: _("I cannot get to something"),
    FeedbackCategory.HELP: _("I need help"),
}

CATEGORY_CHOICES = tuple(CATEGORY_LABELS.items())
CATEGORY_CODES = frozenset(CATEGORY_LABELS)


class FeedbackUrgency:
    """What the *submitter* says. Never a permission, and never the queue order
    on its own — a triager sets priority separately, because "urgent to me" and
    "urgent to the brokerage" are different facts and conflating them teaches
    people to always pick the top one."""

    BLOCKING = "blocking"
    SLOWING = "slowing"
    MINOR = "minor"


URGENCY_LABELS: dict[str, str] = {
    FeedbackUrgency.BLOCKING: _("I cannot work until this is fixed"),
    FeedbackUrgency.SLOWING: _("It is slowing me down"),
    FeedbackUrgency.MINOR: _("Minor — whenever you get to it"),
}

URGENCY_CHOICES = tuple(URGENCY_LABELS.items())
URGENCY_CODES = frozenset(URGENCY_LABELS)


class FeedbackPriority:
    """Staff-set queue order. Mirrors the task and action-item ramps."""

    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


PRIORITY_LABELS: dict[int, str] = {
    FeedbackPriority.CRITICAL: _("Critical"),
    FeedbackPriority.HIGH: _("High"),
    FeedbackPriority.NORMAL: _("Normal"),
    FeedbackPriority.LOW: _("Low"),
}

PRIORITY_CHOICES = tuple(PRIORITY_LABELS.items())
PRIORITY_CODES = frozenset(PRIORITY_LABELS)
PRIORITY_KEYS: dict[int, str] = {
    FeedbackPriority.CRITICAL: "critical",
    FeedbackPriority.HIGH: "high",
    FeedbackPriority.NORMAL: "normal",
    FeedbackPriority.LOW: "low",
}
PRIORITY_BY_KEY: dict[str, int] = {v: k for k, v in PRIORITY_KEYS.items()}

#: The submitter's urgency seeds the staff priority so a triager starts from
#: what the person said rather than from a default. They can change it; the
#: original urgency is kept on the row either way.
URGENCY_TO_PRIORITY: dict[str, int] = {
    FeedbackUrgency.BLOCKING: FeedbackPriority.HIGH,
    FeedbackUrgency.SLOWING: FeedbackPriority.NORMAL,
    FeedbackUrgency.MINOR: FeedbackPriority.LOW,
}


class FeedbackStatus:
    NEW = "new"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    NEEDS_INFO = "needs_info"
    RESOLVED = "resolved"
    CLOSED = "closed"


STATUS_LABELS: dict[str, str] = {
    FeedbackStatus.NEW: _("New"),
    FeedbackStatus.TRIAGED: _("Triaged"),
    FeedbackStatus.IN_PROGRESS: _("In progress"),
    FeedbackStatus.NEEDS_INFO: _("Waiting for your reply"),
    FeedbackStatus.RESOLVED: _("Resolved"),
    FeedbackStatus.CLOSED: _("Closed"),
}

STATUS_CHOICES = tuple(STATUS_LABELS.items())
STATUS_CODES = frozenset(STATUS_LABELS)

TERMINAL_STATUSES: frozenset[str] = frozenset({FeedbackStatus.CLOSED})

OPEN_STATUSES: frozenset[str] = frozenset(
    {
        FeedbackStatus.NEW,
        FeedbackStatus.TRIAGED,
        FeedbackStatus.IN_PROGRESS,
        FeedbackStatus.NEEDS_INFO,
    }
)


class FeedbackPermission:
    """Submitting needs no grant — every authenticated person may report a
    problem with the tool they are told to use. Reading somebody *else's*
    ticket, and everything in triage, does."""

    VIEW = "web.view_feedback"
    TRIAGE = "web.triage_feedback"
    ASSIGN = "web.assign_feedback"
    NOTE = "web.note_feedback"


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    label: str
    permissions: tuple[str, ...] = (FeedbackPermission.TRIAGE,)
    #: Needs a message the *submitter* will read. Asking for information
    #: silently is how a ticket sits untouched for a week.
    requires_reply: bool = False
    closes: bool = False
    reopens: bool = False


TRANSITIONS: tuple[Transition, ...] = (
    Transition(FeedbackStatus.NEW, FeedbackStatus.TRIAGED, _("Accept")),
    Transition(FeedbackStatus.NEW, FeedbackStatus.IN_PROGRESS, _("Start work")),
    Transition(
        FeedbackStatus.NEW,
        FeedbackStatus.NEEDS_INFO,
        _("Ask for more detail"),
        requires_reply=True,
    ),
    Transition(FeedbackStatus.TRIAGED, FeedbackStatus.IN_PROGRESS, _("Start work")),
    Transition(
        FeedbackStatus.TRIAGED,
        FeedbackStatus.NEEDS_INFO,
        _("Ask for more detail"),
        requires_reply=True,
    ),
    Transition(FeedbackStatus.TRIAGED, FeedbackStatus.RESOLVED, _("Resolve")),
    Transition(
        FeedbackStatus.IN_PROGRESS,
        FeedbackStatus.NEEDS_INFO,
        _("Ask for more detail"),
        requires_reply=True,
    ),
    Transition(FeedbackStatus.IN_PROGRESS, FeedbackStatus.RESOLVED, _("Resolve")),
    Transition(FeedbackStatus.NEEDS_INFO, FeedbackStatus.IN_PROGRESS, _("Resume")),
    Transition(FeedbackStatus.NEEDS_INFO, FeedbackStatus.RESOLVED, _("Resolve")),
    Transition(FeedbackStatus.RESOLVED, FeedbackStatus.CLOSED, _("Close"), closes=True),
    # Reopening is the escape hatch from "we think this is done". It stays a
    # staff decision: a submitter who disagrees replies, and the reply is what
    # a triager acts on.
    Transition(
        FeedbackStatus.RESOLVED, FeedbackStatus.IN_PROGRESS, _("Reopen"), reopens=True
    ),
    Transition(
        FeedbackStatus.CLOSED, FeedbackStatus.IN_PROGRESS, _("Reopen"), reopens=True
    ),
)

_INDEX: dict[tuple[str, str], Transition] = {
    (t.source, t.target): t for t in TRANSITIONS
}


def find_transition(source: str, target: str) -> Transition | None:
    """Never raises on an unknown code: a stale client naming a retired status
    gets the ordinary "not a legal move" answer rather than a 500."""
    return _INDEX.get((source, target))


def transitions_from(source: str) -> tuple[Transition, ...]:
    return tuple(t for t in TRANSITIONS if t.source == source)


def is_open(status: str) -> bool:
    return status in OPEN_STATUSES
