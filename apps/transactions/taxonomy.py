"""Transaction vocabulary: types, representation, assignments, and lifecycle.

Everything here is code-owned and closed. A status or role code is a contract
that appears in URLs, audit payloads, and saved filters, so the stable machine
code is what is stored and the label is presentation only.

The lifecycle lives here rather than on the model because it is a *policy*
question: which transitions exist, who may make them, and which fields must
be present. :mod:`apps.transactions.lifecycle` is the only writer of
``status``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

from apps.transactions.permissions import (
    MANAGE_TRANSACTIONS,
    TRANSITION_TRANSACTIONS,
    VIEW_TRANSACTIONS,
)

# --------------------------------------------------------------------------- #
# Transaction type — the deal kind
# --------------------------------------------------------------------------- #


class TransactionType:
    BUY = "buy"
    SELL = "sell"
    RENT = "rent"


TYPE_LABELS: dict[str, str] = {
    TransactionType.BUY: _("Buy"),
    TransactionType.SELL: _("Sell"),
    TransactionType.RENT: _("Rent"),
}

TYPE_CHOICES = tuple(TYPE_LABELS.items())
TYPE_CODES = frozenset(TYPE_LABELS)


# --------------------------------------------------------------------------- #
# Representation — agency posture (includes dual)
# --------------------------------------------------------------------------- #


class RepresentationType:
    BUYER = "buyer"
    SELLER = "seller"
    LANDLORD = "landlord"
    TENANT = "tenant"
    DUAL = "dual"


REPRESENTATION_LABELS: dict[str, str] = {
    RepresentationType.BUYER: _("Buyer agency"),
    RepresentationType.SELLER: _("Seller agency"),
    RepresentationType.LANDLORD: _("Landlord agency"),
    RepresentationType.TENANT: _("Tenant agency"),
    RepresentationType.DUAL: _("Dual representation"),
}

REPRESENTATION_CHOICES = tuple(REPRESENTATION_LABELS.items())
REPRESENTATION_CODES = frozenset(REPRESENTATION_LABELS)


# --------------------------------------------------------------------------- #
# Assignment roles — authoritative membership on a deal
# --------------------------------------------------------------------------- #


class AssignmentRole:
    PRIMARY_AGENT = "primary_agent"
    CO_AGENT = "co_agent"
    COORDINATOR = "coordinator"
    COMPLIANCE_REVIEWER = "compliance_reviewer"


ASSIGNMENT_ROLE_LABELS: dict[str, str] = {
    AssignmentRole.PRIMARY_AGENT: _("Primary agent"),
    AssignmentRole.CO_AGENT: _("Co-agent"),
    AssignmentRole.COORDINATOR: _("Coordinator"),
    AssignmentRole.COMPLIANCE_REVIEWER: _("Compliance reviewer"),
}

ASSIGNMENT_ROLE_CHOICES = tuple(ASSIGNMENT_ROLE_LABELS.items())
ASSIGNMENT_ROLE_CODES = frozenset(ASSIGNMENT_ROLE_LABELS)

#: Roles that may hold at most one active assignment per transaction.
SINGLETON_ASSIGNMENT_ROLES: frozenset[str] = frozenset(
    {AssignmentRole.PRIMARY_AGENT, AssignmentRole.COORDINATOR}
)


# --------------------------------------------------------------------------- #
# Status and the lifecycle
# --------------------------------------------------------------------------- #


class TransactionStatus:
    DRAFT = "draft"
    PREPARING = "preparing"
    UNDER_CONTRACT = "under_contract"
    PENDING = "pending"
    COMPLIANCE_REVIEW = "compliance_review"
    READY_TO_CLOSE = "ready_to_close"
    CLOSED = "closed"
    ARCHIVED = "archived"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"
    WITHDRAWN = "withdrawn"
    TERMINATED = "terminated"


STATUS_LABELS: dict[str, str] = {
    TransactionStatus.DRAFT: _("Draft"),
    TransactionStatus.PREPARING: _("Preparing"),
    TransactionStatus.UNDER_CONTRACT: _("Under contract"),
    TransactionStatus.PENDING: _("Pending"),
    TransactionStatus.COMPLIANCE_REVIEW: _("Compliance review"),
    TransactionStatus.READY_TO_CLOSE: _("Ready to close"),
    TransactionStatus.CLOSED: _("Closed"),
    TransactionStatus.ARCHIVED: _("Archived"),
    TransactionStatus.ON_HOLD: _("On hold"),
    TransactionStatus.CANCELLED: _("Cancelled"),
    TransactionStatus.WITHDRAWN: _("Withdrawn"),
    TransactionStatus.TERMINATED: _("Terminated"),
}

STATUS_CHOICES = tuple(STATUS_LABELS.items())
STATUS_CODES = frozenset(STATUS_LABELS)

#: Terminal outcomes. Soft-archive is post-closed retention, not a failure.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        TransactionStatus.CLOSED,
        TransactionStatus.ARCHIVED,
        TransactionStatus.CANCELLED,
        TransactionStatus.WITHDRAWN,
        TransactionStatus.TERMINATED,
    }
)

#: Live pipeline (excludes On Hold and terminals).
PIPELINE_STATUSES: frozenset[str] = frozenset(
    {
        TransactionStatus.DRAFT,
        TransactionStatus.PREPARING,
        TransactionStatus.UNDER_CONTRACT,
        TransactionStatus.PENDING,
        TransactionStatus.COMPLIANCE_REVIEW,
        TransactionStatus.READY_TO_CLOSE,
    }
)

#: Statuses that may enter On Hold, and that On Hold may resume into.
HOLDABLE_STATUSES: frozenset[str] = frozenset(
    {
        TransactionStatus.PREPARING,
        TransactionStatus.UNDER_CONTRACT,
        TransactionStatus.PENDING,
        TransactionStatus.COMPLIANCE_REVIEW,
        TransactionStatus.READY_TO_CLOSE,
    }
)

#: Happy-path order for documentation and progressive required fields.
HAPPY_PATH: tuple[str, ...] = (
    TransactionStatus.DRAFT,
    TransactionStatus.PREPARING,
    TransactionStatus.UNDER_CONTRACT,
    TransactionStatus.PENDING,
    TransactionStatus.COMPLIANCE_REVIEW,
    TransactionStatus.READY_TO_CLOSE,
    TransactionStatus.CLOSED,
    TransactionStatus.ARCHIVED,
)


class TransactionPermission:
    """Permission family this module authorizes against."""

    VIEW = VIEW_TRANSACTIONS
    MANAGE = MANAGE_TRANSACTIONS
    TRANSITION = TRANSITION_TRANSACTIONS


#: Fields that must be non-empty before entering the named status.
#: Checked on the *target* of a transition. Draft create is lighter.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    TransactionStatus.DRAFT: ("transaction_type", "representation_type", "office"),
    TransactionStatus.PREPARING: (
        "transaction_type",
        "representation_type",
        "office",
        "primary_agent",
    ),
    TransactionStatus.UNDER_CONTRACT: (
        "transaction_type",
        "representation_type",
        "office",
        "primary_agent",
        "property_snapshot",
        "contract_price",
        "acceptance_date",
    ),
    TransactionStatus.PENDING: (
        "transaction_type",
        "representation_type",
        "office",
        "primary_agent",
        "property_snapshot",
        "contract_price",
        "acceptance_date",
    ),
    TransactionStatus.COMPLIANCE_REVIEW: (
        "transaction_type",
        "representation_type",
        "office",
        "primary_agent",
        "property_snapshot",
        "contract_price",
        "acceptance_date",
    ),
    TransactionStatus.READY_TO_CLOSE: (
        "transaction_type",
        "representation_type",
        "office",
        "primary_agent",
        "property_snapshot",
        "contract_price",
        "acceptance_date",
        "closing_date",
    ),
    TransactionStatus.CLOSED: (
        "transaction_type",
        "representation_type",
        "office",
        "primary_agent",
        "property_snapshot",
        "contract_price",
        "acceptance_date",
        "closing_date",
        "compliance_approved_at",
    ),
    TransactionStatus.ARCHIVED: (
        "transaction_type",
        "representation_type",
        "office",
        "closed_at",
    ),
}


@dataclass(frozen=True)
class Transition:
    """One legal move, and who may make it.

    ``permissions`` is an OR: holding any one is enough. ``by_assignee`` lets
    the active primary agent or coordinator move without the transition grant
    for the documented assignee-safe moves.
    """

    source: str
    target: str
    label: str
    permissions: tuple[str, ...] = (TRANSITION_TRANSACTIONS, MANAGE_TRANSACTIONS)
    by_assignee: bool = False
    requires_note: bool = False
    #: Entering On Hold — stamps ``held_from_status``.
    holds: bool = False
    #: Resuming from On Hold — target must equal ``held_from_status``.
    resumes: bool = False
    #: Stamps ``compliance_approved_at`` when entering Ready to Close.
    approves_compliance: bool = False
    #: Terminal failure/outcome stamps (cancelled / withdrawn / terminated).
    cancels: bool = False
    withdraws: bool = False
    terminates: bool = False
    closes: bool = False
    archives: bool = False


def _happy_path_transitions() -> tuple[Transition, ...]:
    steps = (
        (TransactionStatus.DRAFT, TransactionStatus.PREPARING, _("Start preparing")),
        (
            TransactionStatus.PREPARING,
            TransactionStatus.UNDER_CONTRACT,
            _("Mark under contract"),
        ),
        (
            TransactionStatus.UNDER_CONTRACT,
            TransactionStatus.PENDING,
            _("Mark pending"),
        ),
        (
            TransactionStatus.PENDING,
            TransactionStatus.COMPLIANCE_REVIEW,
            _("Submit for compliance"),
        ),
        (
            TransactionStatus.COMPLIANCE_REVIEW,
            TransactionStatus.READY_TO_CLOSE,
            _("Approve for closing"),
        ),
        (
            TransactionStatus.READY_TO_CLOSE,
            TransactionStatus.CLOSED,
            _("Close"),
        ),
        (
            TransactionStatus.CLOSED,
            TransactionStatus.ARCHIVED,
            _("Archive"),
        ),
    )
    out: list[Transition] = []
    for source, target, label in steps:
        out.append(
            Transition(
                source,
                target,
                label,
                by_assignee=target
                not in {
                    TransactionStatus.READY_TO_CLOSE,
                    TransactionStatus.CLOSED,
                    TransactionStatus.ARCHIVED,
                },
                approves_compliance=target == TransactionStatus.READY_TO_CLOSE,
                closes=target == TransactionStatus.CLOSED,
                archives=target == TransactionStatus.ARCHIVED,
            )
        )
    return tuple(out)


def _hold_transitions() -> tuple[Transition, ...]:
    out: list[Transition] = []
    for status in sorted(HOLDABLE_STATUSES):
        out.append(
            Transition(
                status,
                TransactionStatus.ON_HOLD,
                _("Place on hold"),
                by_assignee=True,
                requires_note=True,
                holds=True,
            )
        )
        out.append(
            Transition(
                TransactionStatus.ON_HOLD,
                status,
                _("Resume"),
                by_assignee=True,
                resumes=True,
            )
        )
    return tuple(out)


def _side_path_transitions() -> tuple[Transition, ...]:
    return (
        Transition(
            TransactionStatus.DRAFT,
            TransactionStatus.CANCELLED,
            _("Cancel"),
            requires_note=True,
            cancels=True,
        ),
        Transition(
            TransactionStatus.PREPARING,
            TransactionStatus.CANCELLED,
            _("Cancel"),
            by_assignee=True,
            requires_note=True,
            cancels=True,
        ),
        Transition(
            TransactionStatus.UNDER_CONTRACT,
            TransactionStatus.WITHDRAWN,
            _("Withdraw"),
            by_assignee=True,
            requires_note=True,
            withdraws=True,
        ),
        Transition(
            TransactionStatus.PENDING,
            TransactionStatus.WITHDRAWN,
            _("Withdraw"),
            by_assignee=True,
            requires_note=True,
            withdraws=True,
        ),
        Transition(
            TransactionStatus.UNDER_CONTRACT,
            TransactionStatus.TERMINATED,
            _("Terminate"),
            requires_note=True,
            terminates=True,
        ),
        Transition(
            TransactionStatus.PENDING,
            TransactionStatus.TERMINATED,
            _("Terminate"),
            requires_note=True,
            terminates=True,
        ),
        Transition(
            TransactionStatus.COMPLIANCE_REVIEW,
            TransactionStatus.TERMINATED,
            _("Terminate"),
            requires_note=True,
            terminates=True,
        ),
        Transition(
            TransactionStatus.READY_TO_CLOSE,
            TransactionStatus.TERMINATED,
            _("Terminate"),
            requires_note=True,
            terminates=True,
        ),
    )


TRANSITIONS: tuple[Transition, ...] = (
    *_happy_path_transitions(),
    *_hold_transitions(),
    *_side_path_transitions(),
)

_TRANSITION_INDEX: dict[tuple[str, str], Transition] = {
    (transition.source, transition.target): transition for transition in TRANSITIONS
}


def find_transition(source: str, target: str) -> Transition | None:
    """The legal move from ``source`` to ``target``, or ``None``."""
    return _TRANSITION_INDEX.get((source, target))


def transitions_from(source: str) -> tuple[Transition, ...]:
    return tuple(t for t in TRANSITIONS if t.source == source)


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_pipeline(status: str) -> bool:
    return status in PIPELINE_STATUSES


#: Timestamp field stamped when entering each status (first time).
STATUS_ENTERED_AT: dict[str, str] = {
    TransactionStatus.PREPARING: "preparing_at",
    TransactionStatus.UNDER_CONTRACT: "under_contract_at",
    TransactionStatus.PENDING: "pending_at",
    TransactionStatus.COMPLIANCE_REVIEW: "compliance_review_at",
    TransactionStatus.READY_TO_CLOSE: "ready_to_close_at",
    TransactionStatus.CLOSED: "closed_at",
    TransactionStatus.ARCHIVED: "archived_at",
    TransactionStatus.ON_HOLD: "on_hold_at",
    TransactionStatus.CANCELLED: "cancelled_at",
    TransactionStatus.WITHDRAWN: "withdrawn_at",
    TransactionStatus.TERMINATED: "terminated_at",
}

__all__ = [
    "ASSIGNMENT_ROLE_CHOICES",
    "ASSIGNMENT_ROLE_CODES",
    "ASSIGNMENT_ROLE_LABELS",
    "AssignmentRole",
    "HAPPY_PATH",
    "HOLDABLE_STATUSES",
    "PIPELINE_STATUSES",
    "REPRESENTATION_CHOICES",
    "REPRESENTATION_CODES",
    "REPRESENTATION_LABELS",
    "REQUIRED_FIELDS",
    "RepresentationType",
    "SINGLETON_ASSIGNMENT_ROLES",
    "STATUS_CHOICES",
    "STATUS_CODES",
    "STATUS_ENTERED_AT",
    "STATUS_LABELS",
    "TERMINAL_STATUSES",
    "TRANSITIONS",
    "TYPE_CHOICES",
    "TYPE_CODES",
    "TYPE_LABELS",
    "TransactionPermission",
    "TransactionStatus",
    "TransactionType",
    "Transition",
    "find_transition",
    "is_pipeline",
    "is_terminal",
    "transitions_from",
]
