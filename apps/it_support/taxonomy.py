"""IT support vocabulary and its lifecycle.

Code-owned and closed, for the same reason the feedback and task modules' are:
a category or status appears in URLs, audit payloads, and notification bodies,
so the stable machine code is what is stored and the label is presentation
only. A wording change must never become a data migration.

**Why this is not the feedback module.** Feedback is about the *product* — a
bug, an idea, something out of date. IT support is about the *equipment and
accounts somebody needs to work today*: a printer, a Wi-Fi drop, a locked
account. They have different categories, different audiences, and different
readers: the `view_it_support` grant is held by IT staff, and folding these
tickets into the feedback inbox would hand every feedback triager a view of
them. The operations registry reserved this module its own destination,
permission, and scope rule before it was built; this is that module.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

# --------------------------------------------------------------------------- #
# Categories — what kind of problem this is
# --------------------------------------------------------------------------- #


class SupportCategory:
    ACCOUNT = "login_account"
    MICROSOFT = "microsoft_365"
    INTRANET = "intranet"
    DEVICE = "computer_device"
    PRINTER = "printer"
    NETWORK = "network_wifi"
    SOFTWARE = "software"
    ACCESS = "permissions_access"
    #: New-agent provisioning: the accounts and apps somebody needs on day one.
    #: The *checklist* lives on ``user.OnboardingToolSetup`` and is worked from
    #: the New Agent List — this category is the request that asks IT to do it,
    #: not a second copy of the progress. See ``docs/it-support.md``.
    ONBOARDING = "agent_onboarding"
    OTHER = "other"


CATEGORY_LABELS: dict[str, str] = {
    SupportCategory.ACCOUNT: _("Login / Account"),
    SupportCategory.MICROSOFT: _("Microsoft 365 / Email"),
    SupportCategory.INTRANET: _("Intranet"),
    SupportCategory.DEVICE: _("Computer / Device"),
    SupportCategory.PRINTER: _("Printer"),
    SupportCategory.NETWORK: _("Network / Wi-Fi"),
    SupportCategory.SOFTWARE: _("Software"),
    SupportCategory.ACCESS: _("Permissions / Access"),
    SupportCategory.ONBOARDING: _("New agent setup"),
    SupportCategory.OTHER: _("Other"),
}

CATEGORY_CHOICES = tuple(CATEGORY_LABELS.items())
CATEGORY_CODES = frozenset(CATEGORY_LABELS)


# --------------------------------------------------------------------------- #
# Priority — staff-set queue order
# --------------------------------------------------------------------------- #


class SupportPriority:
    """Lower sorts first. Mirrors the feedback, task, and action-item ramps so
    a ticket and anything derived from it cannot disagree about urgency."""

    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


PRIORITY_LABELS: dict[int, str] = {
    SupportPriority.URGENT: _("Urgent"),
    SupportPriority.HIGH: _("High"),
    SupportPriority.NORMAL: _("Normal"),
    SupportPriority.LOW: _("Low"),
}

PRIORITY_CHOICES = tuple(PRIORITY_LABELS.items())
PRIORITY_CODES = frozenset(PRIORITY_LABELS)

#: Stable string keys for the wire. The client never receives a bare integer it
#: would have to know how to order.
PRIORITY_KEYS: dict[int, str] = {
    SupportPriority.URGENT: "urgent",
    SupportPriority.HIGH: "high",
    SupportPriority.NORMAL: "normal",
    SupportPriority.LOW: "low",
}
PRIORITY_BY_KEY: dict[str, int] = {v: k for k, v in PRIORITY_KEYS.items()}


# --------------------------------------------------------------------------- #
# Preferred contact method — how the submitter wants to be reached
# --------------------------------------------------------------------------- #


class ContactMethod:
    """What the submitter asked for, not a delivery guarantee.

    In-app notification always fires regardless; this records a preference IT
    can honour when they need to reach somebody directly, and a ticket whose
    submitter asked for a phone call should not be answered only in writing.
    """

    HUB = "hub"
    EMAIL = "email"
    PHONE = "phone"
    TEAMS = "teams"


CONTACT_METHOD_LABELS: dict[str, str] = {
    ContactMethod.HUB: _("In the hub"),
    ContactMethod.EMAIL: _("Email"),
    ContactMethod.PHONE: _("Phone call"),
    ContactMethod.TEAMS: _("Microsoft Teams"),
}

CONTACT_METHOD_CHOICES = tuple(CONTACT_METHOD_LABELS.items())
CONTACT_METHOD_CODES = frozenset(CONTACT_METHOD_LABELS)


# --------------------------------------------------------------------------- #
# Status and the lifecycle
# --------------------------------------------------------------------------- #


class SupportStatus:
    NEW = "new"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    RESOLVED = "resolved"
    CLOSED = "closed"


STATUS_LABELS: dict[str, str] = {
    SupportStatus.NEW: _("New"),
    SupportStatus.OPEN: _("Open"),
    SupportStatus.IN_PROGRESS: _("In progress"),
    # Said from the submitter's side: this queue is one they can also read, and
    # "Waiting for user" reads as a status about somebody else.
    SupportStatus.WAITING_USER: _("Waiting for your reply"),
    SupportStatus.RESOLVED: _("Resolved"),
    SupportStatus.CLOSED: _("Closed"),
}

STATUS_CHOICES = tuple(STATUS_LABELS.items())
STATUS_CODES = frozenset(STATUS_LABELS)

#: Terminal. A closed ticket has left the queue; reopening is an explicit move.
TERMINAL_STATUSES: frozenset[str] = frozenset({SupportStatus.CLOSED})

#: Still somebody's problem. Used by the queue's default filter and by every
#: metric that counts live work — one definition, so they cannot drift.
OPEN_STATUSES: frozenset[str] = frozenset(
    {
        SupportStatus.NEW,
        SupportStatus.OPEN,
        SupportStatus.IN_PROGRESS,
        SupportStatus.WAITING_USER,
    }
)

#: Board column order. Resolved is shown because somebody has to close it.
BOARD_STATUSES: tuple[str, ...] = (
    SupportStatus.NEW,
    SupportStatus.OPEN,
    SupportStatus.IN_PROGRESS,
    SupportStatus.WAITING_USER,
    SupportStatus.RESOLVED,
)


class SupportPermission:
    """The permission family this module authorizes against.

    Submitting needs **no grant**: every authenticated person may report that
    the tool they are told to use is broken, and putting a permission in front
    of that means the people most likely to hit an access bug are the ones who
    cannot report it. Reading somebody *else's* ticket, and everything in
    triage, does.
    """

    VIEW = "web.view_it_support"
    TRIAGE = "web.triage_it_support"
    ASSIGN = "web.assign_it_support"
    NOTE = "web.note_it_support"


@dataclass(frozen=True)
class Transition:
    """One legal move, and who may make it.

    ``permissions`` is an OR: holding any one of them is enough.
    """

    source: str
    target: str
    label: str
    permissions: tuple[str, ...] = (SupportPermission.TRIAGE,)
    #: Requires a note. A move that changes what somebody else should expect
    #: may not be silent.
    requires_note: bool = False
    #: The submitter may make this move on their own ticket. Answering a
    #: question IT asked is the one thing the person waiting can do.
    by_submitter: bool = False
    resolves: bool = False
    closes: bool = False
    reopens: bool = False


TRANSITIONS: tuple[Transition, ...] = (
    Transition(SupportStatus.NEW, SupportStatus.OPEN, _("Accept")),
    Transition(SupportStatus.NEW, SupportStatus.IN_PROGRESS, _("Start work")),
    Transition(SupportStatus.OPEN, SupportStatus.IN_PROGRESS, _("Start work")),
    Transition(
        SupportStatus.IN_PROGRESS,
        SupportStatus.WAITING_USER,
        _("Ask the requester"),
        requires_note=True,
    ),
    Transition(
        SupportStatus.OPEN,
        SupportStatus.WAITING_USER,
        _("Ask the requester"),
        requires_note=True,
    ),
    # The submitter's own move: replying to a question puts the ticket back in
    # IT's court without needing anybody's grant.
    Transition(
        SupportStatus.WAITING_USER,
        SupportStatus.IN_PROGRESS,
        _("Resume"),
        by_submitter=True,
    ),
    Transition(
        SupportStatus.IN_PROGRESS,
        SupportStatus.RESOLVED,
        _("Resolve"),
        requires_note=True,
        resolves=True,
    ),
    Transition(
        SupportStatus.OPEN,
        SupportStatus.RESOLVED,
        _("Resolve"),
        requires_note=True,
        resolves=True,
    ),
    Transition(SupportStatus.RESOLVED, SupportStatus.CLOSED, _("Close"), closes=True),
    # Reopen from both ends. A submitter may reopen their own resolved ticket:
    # "it is still broken" is the whole point of telling them it was fixed.
    Transition(
        SupportStatus.RESOLVED,
        SupportStatus.IN_PROGRESS,
        _("Reopen"),
        by_submitter=True,
        reopens=True,
    ),
    Transition(
        SupportStatus.CLOSED, SupportStatus.IN_PROGRESS, _("Reopen"), reopens=True
    ),
)

_TRANSITION_INDEX: dict[tuple[str, str], Transition] = {
    (transition.source, transition.target): transition for transition in TRANSITIONS
}


def find_transition(source: str, target: str) -> Transition | None:
    """The legal move, or ``None``.

    Never raises on unknown codes: a stale client sending a status this build
    retired gets the ordinary "not a legal move" answer, not a 500.
    """
    return _TRANSITION_INDEX.get((source, target))


def transitions_from(source: str) -> tuple[Transition, ...]:
    return tuple(t for t in TRANSITIONS if t.source == source)


def is_open(status: str) -> bool:
    return status in OPEN_STATUSES
