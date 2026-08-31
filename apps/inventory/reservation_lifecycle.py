"""Central inventory reservation lifecycle.

Every status change goes through :func:`transition`. Forms, admin, and API
surfaces must not assign ``status`` directly — the model refuses unguarded writes.

Concurrency uses item-row locks (same order as create) plus ``expected_version``
derived from ``updated_at``. Idempotent retries against an already-at-target row
return without a second audit or transition event.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.service import (
    actor_from_user,
    log_on_commit,
    snapshot_model,
    system_actor,
)
from apps.inventory.availability import can_reserve_quantity
from apps.inventory.models import (
    InventoryItem,
    InventoryReservation,
    ReservationTransitionEvent,
)
from apps.inventory.policy import agent_may_cancel, cancel_cutoff_at
from apps.inventory.reservation_common import (
    AUDIT_FIELDS,
    ActorContext,
    audit_target,
    overlapping_rows,
)
from apps.inventory.reservation_taxonomy import (
    ACTION_LABELS,
    TRANSITIONS,
    CapacityEffect,
    ReservationAction,
    ReservationPermission,
    ReservationStatus,
    Transition,
    consumes_capacity,
    find_transition,
    transitions_from,
)
from apps.inventory.reservations import AvailabilityConflict
from apps.inventory.taxonomy import ItemAvailabilityState, TrackingMode

logger = logging.getLogger(__name__)

_STATUS_WRITE_ALLOWED: ContextVar[bool] = ContextVar(
    "reservation_status_write_allowed", default=False
)

_AUDIT_ACTION: dict[str, str] = {
    ReservationAction.APPROVE.value: "inventory.reservation.approved",
    ReservationAction.DENY.value: "inventory.reservation.denied",
    ReservationAction.MARK_READY.value: "inventory.reservation.ready",
    ReservationAction.CHECK_OUT.value: "inventory.reservation.checked_out",
    ReservationAction.ACCEPT_RETURN.value: "inventory.reservation.returned",
    ReservationAction.COMPLETE.value: "inventory.reservation.completed",
    ReservationAction.CANCEL.value: "inventory.reservation.cancelled",
    ReservationAction.MARK_OVERDUE.value: "inventory.reservation.overdue",
    ReservationAction.MARK_LOST.value: "inventory.reservation.lost",
    ReservationAction.MARK_DAMAGED.value: "inventory.reservation.damaged",
    ReservationAction.REVERT_CHECKOUT.value: "inventory.reservation.reverted_checkout",
    ReservationAction.REVERT_RETURN.value: "inventory.reservation.reverted_return",
}


class StaleReservationVersion(ValidationError):
    """The row moved between the form being rendered and being submitted."""

    def __init__(self):
        super().__init__(
            _(
                "Somebody else updated this reservation while you were working. "
                "Reload and try again."
            )
        )


class TransitionRefused(ValidationError):
    """A lifecycle action that does not apply to the row's current state."""


@contextmanager
def allow_status_write():
    token = _STATUS_WRITE_ALLOWED.set(True)
    try:
        yield
    finally:
        _STATUS_WRITE_ALLOWED.reset(token)


def status_write_allowed() -> bool:
    return bool(_STATUS_WRITE_ALLOWED.get())


def reservation_version(reservation: InventoryReservation) -> str:
    return reservation.updated_at.isoformat(timespec="microseconds")


def _assert_fresh(reservation: InventoryReservation, expected_version: str) -> None:
    if expected_version and reservation_version(reservation) != expected_version:
        raise StaleReservationVersion()


def _lock_pair(
    reservation_id: int, item_id: int
) -> tuple[InventoryItem, InventoryReservation]:
    locked_item = InventoryItem.objects.select_for_update(of=("self",)).get(pk=item_id)
    locked = InventoryReservation.objects.select_for_update(of=("self",)).get(
        pk=reservation_id
    )
    return locked_item, locked


def available_transitions(
    reservation: InventoryReservation, actor: ActorContext, *, system: bool = False
) -> list[Transition]:
    is_owner = reservation.owner_id == getattr(actor.user, "pk", None)
    allowed: list[Transition] = []
    for candidate in transitions_from(reservation.status):
        if candidate.system_only and not system:
            continue
        if candidate.override_only and not actor.holds(ReservationPermission.OVERRIDE):
            continue
        if candidate.by_owner and is_owner:
            if (
                candidate.action == ReservationAction.CANCEL.value
                and not agent_may_cancel(
                    status=reservation.status, starts_at=reservation.starts_at
                )
                and not actor.holds(ReservationPermission.OVERRIDE)
            ):
                continue
            allowed.append(candidate)
            continue
        if actor.holds(*candidate.permissions):
            if candidate.override_only:
                continue
            allowed.append(candidate)
    return allowed


def _authorize(
    move: Transition,
    *,
    actor: ActorContext,
    reservation: InventoryReservation,
    system: bool,
    override: bool,
) -> None:
    is_owner = reservation.owner_id == getattr(actor.user, "pk", None)
    if move.system_only:
        if not system:
            raise PermissionDenied("This transition may only run as a system action.")
        return
    if move.override_only:
        if not override or not actor.holds(ReservationPermission.OVERRIDE):
            raise PermissionDenied("Override permission is required for this action.")
        return
    if move.by_owner and is_owner:
        if (
            move.action == ReservationAction.CANCEL.value
            and not agent_may_cancel(
                status=reservation.status, starts_at=reservation.starts_at
            )
            and not actor.holds(ReservationPermission.OVERRIDE)
        ):
            cutoff = cancel_cutoff_at(reservation.starts_at)
            raise ValidationError(
                {
                    "form": [
                        str(
                            _(
                                "This reservation can no longer be cancelled online "
                                "(cutoff %(cutoff)s). Contact your office."
                            )
                            % {"cutoff": timezone.localtime(cutoff).isoformat()}
                        )
                    ]
                }
            )
        return
    if not actor.holds(*move.permissions):
        raise PermissionDenied("You do not have permission to perform this action.")


def _validate_notes(
    move: Transition,
    *,
    reason: str,
    notes: str,
    override: bool,
) -> None:
    if move.requires_reason and not (reason or "").strip():
        raise ValidationError({"reason": [_("A reason is required for this action.")]})
    if override and not (reason or "").strip():
        raise ValidationError(
            {"reason": [_("Override actions require a non-empty reason.")]}
        )
    if move.action == ReservationAction.CHECK_OUT.value and not notes.strip():
        pass  # checkout notes optional
    if move.action == ReservationAction.ACCEPT_RETURN.value and not notes.strip():
        pass  # condition notes optional


def _effective_capacity_effect(move: Transition, from_status: str) -> CapacityEffect:
    if move.capacity_effect == CapacityEffect.RELEASE and not consumes_capacity(
        from_status
    ):
        return CapacityEffect.NONE
    return move.capacity_effect


def _apply_capacity(
    move: Transition,
    *,
    from_status: str,
    locked_item: InventoryItem,
    locked: InventoryReservation,
) -> None:
    effect = _effective_capacity_effect(move, from_status)
    if effect == CapacityEffect.NONE:
        return
    if effect == CapacityEffect.RELEASE:
        return
    if effect == CapacityEffect.ACQUIRE:
        from apps.inventory.availability import DateTimeInterval

        interval = DateTimeInterval(start=locked.starts_at, end=locked.ends_at)
        overlapping = overlapping_rows(locked_item.pk, interval)
        excluding = [row for row in overlapping if row.pk != locked.pk]
        if not can_reserve_quantity(
            locked_item,
            interval,
            locked.quantity,
            reservations=tuple(excluding),
        ):
            raise AvailabilityConflict(
                {
                    "form": [
                        str(
                            _(
                                "Not enough quantity is available to restore "
                                "this checkout hold."
                            )
                        )
                    ]
                }
            )


def _sync_item_state(
    locked_item: InventoryItem,
    *,
    reservation_state: str,
) -> None:
    if locked_item.tracking_mode != TrackingMode.SERIALIZED:
        return
    if reservation_state == ReservationStatus.LOST:
        locked_item.availability_state = ItemAvailabilityState.LOST
    elif reservation_state == ReservationStatus.DAMAGED:
        locked_item.availability_state = ItemAvailabilityState.DAMAGED
    else:
        return
    locked_item.full_clean()
    locked_item.save(update_fields=["availability_state", "updated_at"])


def _stamp_fields(
    locked: InventoryReservation,
    move: Transition,
    *,
    actor_user: Any,
    now,
    reason: str,
    notes: str,
    checkout_quantity: int | None,
    return_quantity: int | None,
) -> list[str]:
    updates = ["status", "updated_at"]
    locked.status = move.target

    if move.action == ReservationAction.APPROVE.value:
        locked.approved_at = now
        locked.approved_by = actor_user
        updates.extend(["approved_at", "approved_by"])
    elif move.action == ReservationAction.DENY.value:
        locked.denied_at = now
        locked.denied_by = actor_user
        locked.deny_reason = reason[:240]
        updates.extend(["denied_at", "denied_by", "deny_reason"])
    elif move.action == ReservationAction.MARK_READY.value:
        locked.ready_at = now
        locked.ready_by = actor_user
        updates.extend(["ready_at", "ready_by"])
    elif move.action == ReservationAction.CHECK_OUT.value:
        locked.checked_out_at = now
        locked.checked_out_by = actor_user
        locked.checkout_quantity = checkout_quantity or locked.quantity
        locked.checkout_notes = notes[:240]
        updates.extend(
            ["checked_out_at", "checked_out_by", "checkout_quantity", "checkout_notes"]
        )
    elif move.action == ReservationAction.ACCEPT_RETURN.value:
        locked.returned_at = now
        locked.returned_by = actor_user
        locked.return_quantity = return_quantity or locked.quantity
        locked.return_condition_notes = notes[:240]
        updates.extend(
            [
                "returned_at",
                "returned_by",
                "return_quantity",
                "return_condition_notes",
            ]
        )
    elif move.action == ReservationAction.COMPLETE.value:
        locked.completed_at = now
        locked.completed_by = actor_user
        updates.extend(["completed_at", "completed_by"])
    elif move.action == ReservationAction.CANCEL.value:
        locked.cancelled_at = now
        locked.cancelled_by = actor_user
        locked.cancel_reason = reason[:240]
        updates.extend(["cancelled_at", "cancelled_by", "cancel_reason"])
    elif move.action == ReservationAction.MARK_OVERDUE.value:
        locked.overdue_at = now
        updates.append("overdue_at")
    elif move.action == ReservationAction.MARK_LOST.value:
        locked.lost_at = now
        locked.lost_by = actor_user
        locked.lost_reason = reason[:240]
        updates.extend(["lost_at", "lost_by", "lost_reason"])
    elif move.action == ReservationAction.MARK_DAMAGED.value:
        locked.damaged_at = now
        locked.damaged_by = actor_user
        locked.damaged_reason = reason[:240]
        updates.extend(["damaged_at", "damaged_by", "damaged_reason"])
    elif move.action == ReservationAction.REVERT_CHECKOUT.value:
        locked.returned_at = None
        locked.returned_by = None
        locked.return_quantity = None
        locked.return_condition_notes = ""
        locked.checked_out_at = now
        locked.checked_out_by = actor_user
        updates.extend(
            [
                "returned_at",
                "returned_by",
                "return_quantity",
                "return_condition_notes",
                "checked_out_at",
                "checked_out_by",
            ]
        )
    elif move.action == ReservationAction.REVERT_RETURN.value:
        locked.completed_at = None
        locked.completed_by = None
        locked.returned_at = now
        locked.returned_by = actor_user
        updates.extend(["completed_at", "completed_by", "returned_at", "returned_by"])

    return updates


def _record_event(
    *,
    reservation: InventoryReservation,
    move: Transition,
    from_status: str,
    actor_user: Any,
    reason: str,
    notes: str,
    metadata: dict[str, Any],
    idempotency_key: str,
) -> ReservationTransitionEvent | None:
    key = (idempotency_key or "").strip()
    if key:
        existing = ReservationTransitionEvent.objects.filter(
            idempotency_key=key
        ).first()
        if existing is not None:
            return existing
    return ReservationTransitionEvent.objects.create(
        reservation=reservation,
        action=move.action,
        from_status=from_status,
        to_status=move.target,
        actor=actor_user,
        reason=reason[:240],
        notes=notes[:240],
        metadata=metadata,
        idempotency_key=key,
    )


@transaction.atomic
def transition(
    *,
    actor: ActorContext | None = None,
    reservation: InventoryReservation,
    action: str,
    expected_version: str = "",
    expected_status: str | None = None,
    reason: str = "",
    notes: str = "",
    checkout_quantity: int | None = None,
    return_quantity: int | None = None,
    override: bool = False,
    system: bool = False,
    idempotency_key: str = "",
) -> InventoryReservation:
    """Apply one lifecycle action or explain why it cannot apply."""
    locked_item, locked = _lock_pair(reservation.pk, reservation.item_id)

    if expected_status is not None and locked.status != expected_status:
        raise StaleReservationVersion()

    _assert_fresh(locked, expected_version)

    for candidate in TRANSITIONS:
        if candidate.action == action and candidate.target == locked.status:
            return locked

    move = find_transition(source=locked.status, action=action)
    if move is None:
        raise TransitionRefused(
            {"action": [str(_("That action is not allowed from the current status."))]}
        )

    if locked.status == move.target:
        return locked

    if system:
        actor_user = None
    elif actor is None:
        raise PermissionDenied("An actor is required for this transition.")
    else:
        actor_user = actor.user
        _authorize(
            move, actor=actor, reservation=locked, system=system, override=override
        )
        _validate_notes(move, reason=reason, notes=notes, override=override)

    from_status = locked.status

    if _effective_capacity_effect(move, from_status) != CapacityEffect.NONE:
        _apply_capacity(
            move,
            from_status=from_status,
            locked_item=locked_item,
            locked=locked,
        )

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    now = timezone.now()

    with allow_status_write():
        update_fields = _stamp_fields(
            locked,
            move,
            actor_user=actor_user,
            now=now,
            reason=reason,
            notes=notes,
            checkout_quantity=checkout_quantity,
            return_quantity=return_quantity,
        )
        locked.full_clean()
        locked.save(update_fields=sorted(set(update_fields)))

    if move.updates_item_state:
        _sync_item_state(locked_item, reservation_state=move.updates_item_state)

    event_metadata = {
        "checkout_quantity": locked.checkout_quantity,
        "return_quantity": locked.return_quantity,
        "override": override,
    }
    _record_event(
        reservation=locked,
        move=move,
        from_status=from_status,
        actor_user=actor_user,
        reason=reason,
        notes=notes,
        metadata=event_metadata,
        idempotency_key=idempotency_key,
    )

    audit_actor = system_actor() if system else actor_from_user(actor_user)
    audit_action = _AUDIT_ACTION.get(move.action, "inventory.reservation.transitioned")
    log_on_commit(
        audit_action,
        actor=audit_actor,
        target=audit_target(locked),
        metadata={
            "before": before,
            "after": snapshot_model(locked, fields=AUDIT_FIELDS),
            "action": move.action,
            "from_status": from_status,
            "to_status": move.target,
            "reason": reason[:240],
            "notes": notes[:240],
            "reservation_public_id": str(locked.public_id),
            "override": override,
        },
    )
    return locked


def sync_overdue_reservations(*, now=None) -> int:
    """Mark checked-out reservations past ``ends_at`` as overdue."""
    moment = now or timezone.now()
    candidates = InventoryReservation.objects.filter(
        status=ReservationStatus.CHECKED_OUT,
        ends_at__lte=moment,
    ).only("pk", "item_id", "updated_at")
    count = 0
    for reservation in candidates:
        transition(
            reservation=reservation,
            action=ReservationAction.MARK_OVERDUE.value,
            expected_status=ReservationStatus.CHECKED_OUT,
            system=True,
            idempotency_key=f"overdue:{reservation.pk}:{reservation.updated_at.isoformat()}",
        )
        count += 1
    return count


def serialize_timeline(reservation: InventoryReservation) -> list[dict[str, Any]]:
    """Ordered transition history for Inertia payloads."""
    events = (
        ReservationTransitionEvent.objects.filter(reservation=reservation)
        .select_related("actor")
        .order_by("occurred_at", "pk")
    )
    rows: list[dict[str, Any]] = []
    for event in events:
        actor = event.actor
        rows.append(
            {
                "id": str(event.pk),
                "action": event.action,
                "actionLabel": str(ACTION_LABELS.get(event.action, event.action)),
                "fromStatus": event.from_status,
                "toStatus": event.to_status,
                "reason": event.reason,
                "notes": event.notes,
                "occurredAt": event.occurred_at.isoformat(),
                "actor": (
                    {
                        "id": actor.pk,
                        "name": actor.get_full_name() or actor.email,
                    }
                    if actor is not None
                    else None
                ),
                "metadata": event.metadata or {},
            }
        )
    return rows


def serialize_available_actions(
    reservation: InventoryReservation, actor: ActorContext
) -> list[dict[str, Any]]:
    return [
        {
            "action": move.action,
            "label": move.label,
            "targetStatus": move.target,
            "requiresReason": move.requires_reason or move.override_only,
            "requiresNote": move.requires_note,
            "overrideOnly": move.override_only,
        }
        for move in available_transitions(reservation, actor)
    ]
