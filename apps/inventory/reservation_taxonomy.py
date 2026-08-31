"""Inventory reservation vocabulary, lifecycle policy, and capacity rules.

Stable machine codes are stored; labels are presentation only. ``confirmed`` is
the single post-approval state — there is no separate ``approved`` code. Office
approval is the ``approve`` transition from ``requested`` to ``confirmed``.

Capacity effect and transition rules live here so availability math and the
lifecycle service cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from django.utils.translation import gettext_lazy as _


class ReservationStatus:
    """Lifecycle states for an inventory reservation."""

    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    READY_FOR_PICKUP = "ready_for_pickup"
    CHECKED_OUT = "checked_out"
    RETURNED = "returned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DENIED = "denied"
    OVERDUE = "overdue"
    LOST = "lost"
    DAMAGED = "damaged"


STATUS_LABELS: dict[str, str] = {
    ReservationStatus.REQUESTED: _("Requested — awaiting office approval"),
    ReservationStatus.CONFIRMED: _("Confirmed"),
    ReservationStatus.READY_FOR_PICKUP: _("Ready for pickup"),
    ReservationStatus.CHECKED_OUT: _("Checked out"),
    ReservationStatus.RETURNED: _("Returned"),
    ReservationStatus.COMPLETED: _("Completed"),
    ReservationStatus.CANCELLED: _("Cancelled"),
    ReservationStatus.DENIED: _("Denied"),
    ReservationStatus.OVERDUE: _("Overdue"),
    ReservationStatus.LOST: _("Lost"),
    ReservationStatus.DAMAGED: _("Damaged"),
}

STATUS_CHOICES = tuple(STATUS_LABELS.items())
STATUS_CODES = frozenset(STATUS_LABELS)

#: States that hold capacity for overlapping interval math. Endpoints are
#: half-open ``[starts_at, ends_at)`` — matching :mod:`apps.inventory.availability`.
CAPACITY_CONSUMING_STATES: frozenset[str] = frozenset(
    {
        ReservationStatus.REQUESTED,
        ReservationStatus.CONFIRMED,
        ReservationStatus.READY_FOR_PICKUP,
        ReservationStatus.CHECKED_OUT,
        ReservationStatus.OVERDUE,
    }
)

#: Agent self-service cancel is allowed only from these states, and only before
#: the cancel cutoff in :mod:`apps.inventory.policy`.
AGENT_CANCELABLE_STATES: frozenset[str] = frozenset(
    {
        ReservationStatus.REQUESTED,
        ReservationStatus.CONFIRMED,
        ReservationStatus.READY_FOR_PICKUP,
    }
)

TERMINAL_STATES: frozenset[str] = frozenset(
    {
        ReservationStatus.COMPLETED,
        ReservationStatus.CANCELLED,
        ReservationStatus.DENIED,
        ReservationStatus.LOST,
        ReservationStatus.DAMAGED,
    }
)


class ReservationPermission:
    """Permission family for inventory reservations."""

    VIEW = "web.view_reservations"
    RESERVE_ON_BEHALF = "inventory.reserve_on_behalf"
    APPROVE = "inventory.approve_reservations"
    OVERRIDE = "inventory.override_reservations"


class ReservationAction(StrEnum):
    """Stable lifecycle action codes routed through the transition service."""

    APPROVE = "approve"
    DENY = "deny"
    MARK_READY = "mark_ready"
    CHECK_OUT = "check_out"
    ACCEPT_RETURN = "accept_return"
    COMPLETE = "complete"
    CANCEL = "cancel"
    MARK_OVERDUE = "mark_overdue"
    MARK_LOST = "mark_lost"
    MARK_DAMAGED = "mark_damaged"
    REVERT_CHECKOUT = "revert_checkout"
    REVERT_RETURN = "revert_return"


ACTION_LABELS: dict[str, str] = {
    ReservationAction.APPROVE.value: _("Approve"),
    ReservationAction.DENY.value: _("Deny"),
    ReservationAction.MARK_READY.value: _("Mark ready for pickup"),
    ReservationAction.CHECK_OUT.value: _("Check out"),
    ReservationAction.ACCEPT_RETURN.value: _("Accept return"),
    ReservationAction.COMPLETE.value: _("Complete"),
    ReservationAction.CANCEL.value: _("Cancel"),
    ReservationAction.MARK_OVERDUE.value: _("Mark overdue"),
    ReservationAction.MARK_LOST.value: _("Mark lost"),
    ReservationAction.MARK_DAMAGED.value: _("Mark damaged"),
    ReservationAction.REVERT_CHECKOUT.value: _("Revert return (override)"),
    ReservationAction.REVERT_RETURN.value: _("Revert completion (override)"),
}


class CapacityEffect(StrEnum):
    """Whether a transition changes interval capacity commitment."""

    NONE = "none"
    RELEASE = "release"
    ACQUIRE = "acquire"


@dataclass(frozen=True)
class Transition:
    """One legal reservation lifecycle move."""

    action: str
    sources: frozenset[str]
    target: str
    label: str
    permissions: tuple[str, ...] = (ReservationPermission.APPROVE,)
    by_owner: bool = False
    system_only: bool = False
    override_only: bool = False
    requires_reason: bool = False
    requires_note: bool = False
    capacity_effect: CapacityEffect = CapacityEffect.NONE
    updates_item_state: str = ""


TRANSITIONS: tuple[Transition, ...] = (
    Transition(
        ReservationAction.APPROVE.value,
        frozenset({ReservationStatus.REQUESTED}),
        ReservationStatus.CONFIRMED,
        str(ACTION_LABELS[ReservationAction.APPROVE.value]),
    ),
    Transition(
        ReservationAction.DENY.value,
        frozenset({ReservationStatus.REQUESTED}),
        ReservationStatus.DENIED,
        str(ACTION_LABELS[ReservationAction.DENY.value]),
        requires_reason=True,
        capacity_effect=CapacityEffect.RELEASE,
    ),
    Transition(
        ReservationAction.MARK_READY.value,
        frozenset({ReservationStatus.CONFIRMED}),
        ReservationStatus.READY_FOR_PICKUP,
        str(ACTION_LABELS[ReservationAction.MARK_READY.value]),
    ),
    Transition(
        ReservationAction.CHECK_OUT.value,
        frozenset({ReservationStatus.READY_FOR_PICKUP}),
        ReservationStatus.CHECKED_OUT,
        str(ACTION_LABELS[ReservationAction.CHECK_OUT.value]),
        requires_note=False,
    ),
    Transition(
        ReservationAction.ACCEPT_RETURN.value,
        frozenset({ReservationStatus.CHECKED_OUT, ReservationStatus.OVERDUE}),
        ReservationStatus.RETURNED,
        str(ACTION_LABELS[ReservationAction.ACCEPT_RETURN.value]),
        capacity_effect=CapacityEffect.RELEASE,
    ),
    Transition(
        ReservationAction.COMPLETE.value,
        frozenset({ReservationStatus.RETURNED}),
        ReservationStatus.COMPLETED,
        str(ACTION_LABELS[ReservationAction.COMPLETE.value]),
    ),
    Transition(
        ReservationAction.CANCEL.value,
        AGENT_CANCELABLE_STATES,
        ReservationStatus.CANCELLED,
        str(ACTION_LABELS[ReservationAction.CANCEL.value]),
        permissions=(ReservationPermission.OVERRIDE,),
        by_owner=True,
        capacity_effect=CapacityEffect.RELEASE,
    ),
    Transition(
        ReservationAction.MARK_OVERDUE.value,
        frozenset({ReservationStatus.CHECKED_OUT}),
        ReservationStatus.OVERDUE,
        str(ACTION_LABELS[ReservationAction.MARK_OVERDUE.value]),
        system_only=True,
    ),
    Transition(
        ReservationAction.MARK_LOST.value,
        frozenset({ReservationStatus.CHECKED_OUT, ReservationStatus.OVERDUE}),
        ReservationStatus.LOST,
        str(ACTION_LABELS[ReservationAction.MARK_LOST.value]),
        requires_reason=True,
        capacity_effect=CapacityEffect.RELEASE,
        updates_item_state=ReservationStatus.LOST,
    ),
    Transition(
        ReservationAction.MARK_DAMAGED.value,
        frozenset(
            {
                ReservationStatus.CHECKED_OUT,
                ReservationStatus.OVERDUE,
                ReservationStatus.RETURNED,
            }
        ),
        ReservationStatus.DAMAGED,
        str(ACTION_LABELS[ReservationAction.MARK_DAMAGED.value]),
        requires_reason=True,
        capacity_effect=CapacityEffect.RELEASE,
        updates_item_state=ReservationStatus.DAMAGED,
    ),
    Transition(
        ReservationAction.REVERT_CHECKOUT.value,
        frozenset({ReservationStatus.RETURNED}),
        ReservationStatus.CHECKED_OUT,
        str(ACTION_LABELS[ReservationAction.REVERT_CHECKOUT.value]),
        permissions=(ReservationPermission.OVERRIDE,),
        override_only=True,
        requires_reason=True,
        capacity_effect=CapacityEffect.ACQUIRE,
    ),
    Transition(
        ReservationAction.REVERT_RETURN.value,
        frozenset({ReservationStatus.COMPLETED}),
        ReservationStatus.RETURNED,
        str(ACTION_LABELS[ReservationAction.REVERT_RETURN.value]),
        permissions=(ReservationPermission.OVERRIDE,),
        override_only=True,
        requires_reason=True,
    ),
)

_ACTION_INDEX: dict[tuple[str, str], Transition] = {
    (transition.action, source): transition
    for transition in TRANSITIONS
    for source in transition.sources
}


def find_transition(*, source: str, action: str) -> Transition | None:
    return _ACTION_INDEX.get((action, source))


def transitions_from(source: str) -> tuple[Transition, ...]:
    return tuple(t for t in TRANSITIONS if source in t.sources)


def consumes_capacity(status: str) -> bool:
    return status in CAPACITY_CONSUMING_STATES


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATES
