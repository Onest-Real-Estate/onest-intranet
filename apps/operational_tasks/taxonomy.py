"""The task vocabulary: categories, sources, priorities, and the lifecycle.

Everything here is code-owned and closed. A category or status is a contract
that appears in URLs, audit payloads, notification bodies, and saved filters,
so the stable machine code is what is stored and the label is presentation
only — a wording change must never become a data migration.

The lifecycle lives here rather than on the model because it is a *policy*
question, not a storage one: which transitions exist, who may make them, and
which of them close the task. :mod:`apps.operational_tasks.services` is the
only caller, and it is the only place a status is allowed to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

# --------------------------------------------------------------------------- #
# Categories — what kind of work this is
# --------------------------------------------------------------------------- #


class TaskCategory:
    ONBOARDING = "onboarding_issue"
    PERMISSION = "permission_request"
    TOOL_SETUP = "tool_setup"
    CONTENT_UPDATE = "content_update"
    OFFICE_SETUP = "office_setup"
    INTEGRATION = "integration_incident"
    BUG = "bug"
    SUPPORT_FOLLOW_UP = "support_follow_up"


CATEGORY_LABELS: dict[str, str] = {
    TaskCategory.ONBOARDING: _("Onboarding issue"),
    TaskCategory.PERMISSION: _("Permission request"),
    TaskCategory.TOOL_SETUP: _("Tool setup"),
    TaskCategory.CONTENT_UPDATE: _("Content update"),
    TaskCategory.OFFICE_SETUP: _("Office setup"),
    TaskCategory.INTEGRATION: _("Integration incident"),
    TaskCategory.BUG: _("Bug"),
    TaskCategory.SUPPORT_FOLLOW_UP: _("Support follow-up"),
}

CATEGORY_CHOICES = tuple(CATEGORY_LABELS.items())
CATEGORY_CODES = frozenset(CATEGORY_LABELS)


# --------------------------------------------------------------------------- #
# Source — where the task came from
# --------------------------------------------------------------------------- #


class TaskSource:
    """Provenance, kept distinct from category.

    ``FEEDBACK`` exists now so conversion never has to migrate historic rows
    when the feedback module ships. A converted task keeps this source and its
    ``source_reference`` forever: losing source identity is the failure mode
    the conversion requirement calls out by name.
    """

    MANUAL = "manual"
    FEEDBACK = "feedback"
    AUTOMATION = "automation"


SOURCE_LABELS: dict[str, str] = {
    TaskSource.MANUAL: _("Created directly"),
    TaskSource.FEEDBACK: _("Converted from feedback"),
    TaskSource.AUTOMATION: _("Raised by automation"),
}

SOURCE_CHOICES = tuple(SOURCE_LABELS.items())
SOURCE_CODES = frozenset(SOURCE_LABELS)


# --------------------------------------------------------------------------- #
# Priority — ordering only; never a permission
# --------------------------------------------------------------------------- #


class TaskPriority:
    """Lower sorts first. Mirrors the dashboard action-item ramp exactly so a
    task and the action item it produces cannot disagree about urgency."""

    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


PRIORITY_LABELS: dict[int, str] = {
    TaskPriority.CRITICAL: _("Critical"),
    TaskPriority.HIGH: _("High"),
    TaskPriority.NORMAL: _("Normal"),
    TaskPriority.LOW: _("Low"),
}

PRIORITY_CHOICES = tuple(PRIORITY_LABELS.items())
PRIORITY_CODES = frozenset(PRIORITY_LABELS)

#: Stable string keys for the wire. The integer is the sort key; the client
#: never receives a bare number it would have to know how to order.
PRIORITY_KEYS: dict[int, str] = {
    TaskPriority.CRITICAL: "critical",
    TaskPriority.HIGH: "high",
    TaskPriority.NORMAL: "normal",
    TaskPriority.LOW: "low",
}
PRIORITY_BY_KEY: dict[str, int] = {v: k for k, v in PRIORITY_KEYS.items()}


# --------------------------------------------------------------------------- #
# Status and the lifecycle
# --------------------------------------------------------------------------- #


class TaskStatus:
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    WAITING = "waiting"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


STATUS_LABELS: dict[str, str] = {
    TaskStatus.OPEN: _("Open"),
    TaskStatus.IN_PROGRESS: _("In progress"),
    TaskStatus.BLOCKED: _("Blocked"),
    TaskStatus.WAITING: _("Waiting on requester"),
    TaskStatus.RESOLVED: _("Resolved"),
    TaskStatus.CLOSED: _("Closed"),
    TaskStatus.CANCELLED: _("Cancelled"),
}

STATUS_CHOICES = tuple(STATUS_LABELS.items())
STATUS_CODES = frozenset(STATUS_LABELS)

#: Terminal states. A task in one of these is not work anybody is doing, so it
#: leaves the board, stops producing action items, and stops counting as
#: overdue however far past its due date it sits.
TERMINAL_STATUSES: frozenset[str] = frozenset({TaskStatus.CLOSED, TaskStatus.CANCELLED})

#: States that still represent live work. Used for the board columns, the
#: overdue calculation, and the action-item collector — one definition, so
#: those three can never drift apart.
ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        TaskStatus.OPEN,
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
    }
)

#: Board column order. Resolved is shown because a reviewer needs to see what
#: is waiting to be closed; the terminal states are not columns.
BOARD_STATUSES: tuple[str, ...] = (
    TaskStatus.OPEN,
    TaskStatus.IN_PROGRESS,
    TaskStatus.BLOCKED,
    TaskStatus.WAITING,
    TaskStatus.RESOLVED,
)


class TaskPermission:
    """The permission family this module authorizes against.

    Deliberately *not* ``web.view_platform_tasks``: that grant is unscoped,
    low risk, and means "read sanitized Celery job status". Reusing it would
    silently widen four existing role bundles into a scoped work-tracking
    module they were never granted.
    """

    VIEW = "web.view_operational_tasks"
    MANAGE = "web.manage_operational_tasks"
    ASSIGN = "web.assign_operational_tasks"
    COMMENT = "web.comment_operational_tasks"


@dataclass(frozen=True)
class Transition:
    """One legal move, and who may make it.

    ``permissions`` is an OR: holding any one of them is enough. ``by_assignee``
    lets the person the work is assigned to move it without holding the
    management grant — an agent asked to confirm a fix can resolve their own
    task, but cannot close somebody else's.
    """

    source: str
    target: str
    label: str
    permissions: tuple[str, ...] = (TaskPermission.MANAGE,)
    by_assignee: bool = False
    #: Requires a note explaining the move. Blocked and cancelled both change
    #: what somebody else should expect, so neither may be silent.
    requires_note: bool = False
    #: Terminal moves stamp ``closed_at``; reopening clears it.
    closes: bool = False
    reopens: bool = False


TRANSITIONS: tuple[Transition, ...] = (
    Transition(TaskStatus.OPEN, TaskStatus.IN_PROGRESS, _("Start"), by_assignee=True),
    Transition(
        TaskStatus.OPEN,
        TaskStatus.CANCELLED,
        _("Cancel"),
        requires_note=True,
        closes=True,
    ),
    Transition(
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        _("Mark blocked"),
        by_assignee=True,
        requires_note=True,
    ),
    Transition(
        TaskStatus.IN_PROGRESS,
        TaskStatus.WAITING,
        _("Wait on requester"),
        by_assignee=True,
        requires_note=True,
    ),
    Transition(
        TaskStatus.IN_PROGRESS, TaskStatus.RESOLVED, _("Resolve"), by_assignee=True
    ),
    # Work that turns out not to be needed is abandoned from wherever it got
    # to. Without this, a task started by mistake could only reach a terminal
    # state by being marked Resolved first — a lie in the audit trail.
    Transition(
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
        _("Cancel"),
        requires_note=True,
        closes=True,
    ),
    Transition(
        TaskStatus.IN_PROGRESS, TaskStatus.OPEN, _("Return to open"), by_assignee=True
    ),
    Transition(
        TaskStatus.BLOCKED, TaskStatus.IN_PROGRESS, _("Unblock"), by_assignee=True
    ),
    Transition(
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        _("Cancel"),
        requires_note=True,
        closes=True,
    ),
    Transition(
        TaskStatus.WAITING, TaskStatus.IN_PROGRESS, _("Resume"), by_assignee=True
    ),
    Transition(
        TaskStatus.WAITING,
        TaskStatus.CANCELLED,
        _("Cancel"),
        requires_note=True,
        closes=True,
    ),
    Transition(TaskStatus.RESOLVED, TaskStatus.CLOSED, _("Close"), closes=True),
    # Reopen is the documented escape hatch from both "we fixed it" and "we
    # decided not to". It needs the management grant in every case: an
    # assignee may finish their own work, but reversing a closure is a
    # supervisor's decision.
    Transition(TaskStatus.RESOLVED, TaskStatus.IN_PROGRESS, _("Reopen"), reopens=True),
    Transition(TaskStatus.CLOSED, TaskStatus.IN_PROGRESS, _("Reopen"), reopens=True),
    Transition(
        TaskStatus.CANCELLED,
        TaskStatus.OPEN,
        _("Reopen"),
        reopens=True,
        requires_note=True,
    ),
)

_TRANSITION_INDEX: dict[tuple[str, str], Transition] = {
    (transition.source, transition.target): transition for transition in TRANSITIONS
}


def find_transition(source: str, target: str) -> Transition | None:
    """The legal move from ``source`` to ``target``, or ``None``.

    Never raises on unknown codes: a stale client sending a status this build
    retired must get the ordinary "not a legal move" answer, not a 500.
    """
    return _TRANSITION_INDEX.get((source, target))


def transitions_from(source: str) -> tuple[Transition, ...]:
    return tuple(t for t in TRANSITIONS if t.source == source)


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_active(status: str) -> bool:
    return status in ACTIVE_STATUSES


@dataclass(frozen=True)
class ResolvedCode:
    """A stored code read back safely.

    ``known`` is false when the row holds a code this build does not recognise
    — a category retired between releases, say. Read paths never raise on one;
    they fall back and let the surface say so in words.
    """

    code: str
    label: str
    known: bool
    requested_code: str = ""
    extra: dict[str, object] = field(default_factory=dict)


def resolve_category(code: str | None) -> ResolvedCode:
    requested = (code or "").strip()
    if requested in CATEGORY_CODES:
        return ResolvedCode(requested, str(CATEGORY_LABELS[requested]), True, requested)
    return ResolvedCode("", _("Uncategorized"), False, requested)


def resolve_status(code: str | None) -> ResolvedCode:
    requested = (code or "").strip()
    if requested in STATUS_CODES:
        return ResolvedCode(requested, str(STATUS_LABELS[requested]), True, requested)
    return ResolvedCode(
        TaskStatus.OPEN, str(STATUS_LABELS[TaskStatus.OPEN]), False, requested
    )


def resolve_priority(value: int | None) -> ResolvedCode:
    if value in PRIORITY_LABELS:
        return ResolvedCode(
            PRIORITY_KEYS[value],
            str(PRIORITY_LABELS[value]),
            True,
            PRIORITY_KEYS[value],
            {"rank": value},
        )
    return ResolvedCode(
        PRIORITY_KEYS[TaskPriority.NORMAL],
        str(PRIORITY_LABELS[TaskPriority.NORMAL]),
        False,
        str(value or ""),
        {"rank": TaskPriority.NORMAL},
    )
