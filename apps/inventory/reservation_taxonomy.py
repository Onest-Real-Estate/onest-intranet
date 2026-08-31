"""Inventory reservation vocabulary and capacity policy.

Stable machine codes are stored; labels are presentation only. Capacity effect
and agent-cancel rules live here so availability math and the write service
cannot drift apart.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _


class ReservationStatus:
    """Lifecycle states for an inventory reservation.

    Full office transitions (ready / checkout / return / exception handling)
    are owned by the lifecycle issue. Create and agent cancel use the subset
    documented here.
    """

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
    """Permission family for inventory reservations.

    Agents reserve for themselves without a distinct grant. On-behalf, approve,
    and override use separate codenames enforced in the service layer.
    """

    VIEW = "web.view_reservations"
    RESERVE_ON_BEHALF = "inventory.reserve_on_behalf"
    APPROVE = "inventory.approve_reservations"
    OVERRIDE = "inventory.override_reservations"
