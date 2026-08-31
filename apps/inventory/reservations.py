"""Agent inventory reservation writes: preview, create, cancel.

Create locks the inventory item row, recalculates overlapping capacity, and
inserts exactly one reservation. Availability previews are never trusted at
write time. Side effects (audit) run after commit.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _

from apps.audit.service import actor_from_user, log_on_commit
from apps.inventory.availability import (
    DateTimeInterval,
    available_quantity_for_range,
    can_reserve_quantity,
)
from apps.inventory.browser import parse_availability_interval
from apps.inventory.models import (
    InventoryItem,
    InventoryReservation,
    ReservationTransitionEvent,
)
from apps.inventory.policy import (
    agent_may_cancel,
    initial_status,
    terms_summary,
    validate_horizon_and_duration,
    validate_office_open_days,
)
from apps.inventory.queries import item_for_agent
from apps.inventory.reservation_common import (
    AUDIT_FIELDS,
    ActorContext,
    audit_target,
    committed_quantity_for_item,
    overlapping_rows,
)
from apps.inventory.reservation_taxonomy import (
    CAPACITY_CONSUMING_STATES,
    ReservationAction,
    ReservationPermission,
)
from apps.inventory.taxonomy import TrackingMode
from apps.user.models import User

# Re-export for callers that imported from this module.
__all__ = [
    "AUDIT_FIELDS",
    "ActorContext",
    "AvailabilityConflict",
    "CancelNotAllowed",
    "build_preview",
    "cancel_reservation",
    "committed_quantity_for_item",
    "create_reservation",
    "load_capacity_windows",
    "next_reference",
    "overlapping_rows",
]


class AvailabilityConflict(ValidationError):
    """Requested quantity is no longer available for the interval."""


class CancelNotAllowed(ValidationError):
    """Cancel refused by status or cutoff policy."""


def next_reference(pk: int) -> str:
    return f"INV-R-{pk:06d}"


def load_capacity_windows(
    item_ids: list[int],
) -> tuple[InventoryReservation, ...]:
    if not item_ids:
        return ()
    return tuple(
        InventoryReservation.objects.filter(
            item_id__in=item_ids,
            status__in=sorted(CAPACITY_CONSUMING_STATES),
        ).only("pk", "item_id", "quantity", "starts_at", "ends_at")
    )


def parse_reservation_dates(
    pickup: str, return_date: str
) -> tuple[date | None, date | None, DateTimeInterval | None, list[str]]:
    interval, errors = parse_availability_interval(pickup, return_date)
    if errors or interval is None:
        return None, None, None, errors
    start_day = parse_date(pickup)
    end_day = parse_date(return_date)
    assert start_day is not None and end_day is not None
    errors.extend(validate_horizon_and_duration(start_day, end_day))
    return start_day, end_day, interval, errors


def _resolve_agent_item(actor: User, item_public_id: UUID | str) -> InventoryItem:
    try:
        public_id = (
            item_public_id
            if isinstance(item_public_id, UUID)
            else UUID(str(item_public_id))
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            {"item": [str(_("Choose a valid inventory item."))]}
        ) from exc
    item = item_for_agent(actor, public_id=public_id)
    if item is None:
        raise ValidationError(
            {"item": [str(_("That item is not available to reserve."))]}
        )
    return item


def build_preview(
    *,
    actor: User,
    item_public_id: str,
    pickup: str,
    return_date: str,
    quantity: int,
    purpose: str = "",
) -> dict[str, Any]:
    """Authoritative availability and terms for the reservation form."""
    errors: dict[str, list[str]] = {}
    form_errors: list[str] = []

    if quantity < 1:
        errors["quantity"] = [str(_("Quantity must be at least one."))]

    try:
        item = _resolve_agent_item(actor, item_public_id)
    except ValidationError as exc:
        message_dict = getattr(exc, "message_dict", None)
        if message_dict:
            for key, messages in message_dict.items():
                errors.setdefault(key, []).extend(str(m) for m in messages)
        else:
            form_errors.extend(str(m) for m in exc.messages)
        return {
            "ok": False,
            "errors": {"fields": errors, "form": form_errors},
            "summary": None,
        }

    start_day, end_day, interval, date_errors = parse_reservation_dates(
        pickup, return_date
    )
    if date_errors:
        errors["pickup"] = date_errors
    if interval is None or start_day is None or end_day is None:
        return {
            "ok": False,
            "errors": {"fields": errors, "form": form_errors},
            "summary": None,
        }

    office = item.owner_office
    open_errors = validate_office_open_days(
        getattr(office, "office_hours", None) or [],
        start_day,
        end_day,
    )
    if open_errors:
        errors.setdefault("pickup", []).extend(open_errors)

    if item.tracking_mode == TrackingMode.SERIALIZED and quantity != 1:
        errors["quantity"] = [
            str(_("Serialized items must be reserved as quantity 1."))
        ]

    windows = load_capacity_windows([item.pk])
    available = available_quantity_for_range(item, interval, reservations=windows)
    can_reserve = not errors and can_reserve_quantity(
        item, interval, quantity, reservations=windows
    )
    if not can_reserve and "quantity" not in errors and "pickup" not in errors:
        form_errors.append(str(_("Not enough quantity is available for those dates.")))

    purpose_clean = (purpose or "").strip()[:240]
    status = initial_status(requires_approval=item.requires_approval)
    from apps.inventory.reservation_taxonomy import STATUS_LABELS

    summary = {
        "item": {
            "publicId": str(item.public_id),
            "name": item.name,
            "trackingMode": item.tracking_mode,
            "requiresApproval": item.requires_approval,
            "totalQuantity": item.effective_quantity,
            "storageLocation": item.storage_location,
            "notes": item.notes,
        },
        "office": {"id": office.pk, "name": office.name},
        "pickup": start_day.isoformat(),
        "return": end_day.isoformat(),
        "startsAt": interval.start.isoformat(),
        "endsAt": interval.end.isoformat(),
        "quantity": quantity,
        "purpose": purpose_clean,
        "availableQuantity": available,
        "isAvailable": can_reserve and not errors and not form_errors,
        "status": status,
        "statusLabel": str(STATUS_LABELS.get(status, status)),
        "terms": terms_summary(requires_approval=item.requires_approval),
        "instructions": {
            "storageLocation": item.storage_location,
            "notes": item.notes,
        },
    }
    return {
        "ok": summary["isAvailable"],
        "errors": {"fields": errors, "form": form_errors},
        "summary": summary,
    }


@transaction.atomic
def create_reservation(
    *,
    actor: ActorContext,
    item_public_id: str,
    pickup: str,
    return_date: str,
    quantity: int,
    purpose: str,
    submission_key: str,
    owner: User | None = None,
) -> tuple[InventoryReservation, bool]:
    from apps.inventory.reservation_lifecycle import allow_status_write

    key = (submission_key or "").strip()
    if not key or len(key) > 64:
        raise ValidationError(
            {"submission_key": [str(_("A valid submission key is required."))]}
        )

    existing = InventoryReservation.objects.filter(submission_key=key).first()
    if existing is not None:
        return existing, False

    subject = owner or actor.user
    if subject.pk != actor.user.pk and not actor.holds(
        ReservationPermission.RESERVE_ON_BEHALF
    ):
        raise PermissionDenied(
            "You do not have permission to reserve inventory for another user."
        )

    catalog_user = subject if subject.pk == actor.user.pk else actor.user
    item = _resolve_agent_item(catalog_user, item_public_id)

    if quantity < 1:
        raise ValidationError({"quantity": [str(_("Quantity must be at least one."))]})
    if item.tracking_mode == TrackingMode.SERIALIZED and quantity != 1:
        raise ValidationError(
            {"quantity": [str(_("Serialized items must be reserved as quantity 1."))]}
        )

    start_day, end_day, interval, date_errors = parse_reservation_dates(
        pickup, return_date
    )
    if date_errors or interval is None or start_day is None or end_day is None:
        raise ValidationError({"pickup": date_errors or [str(_("Invalid dates."))]})

    office = item.owner_office
    open_errors = validate_office_open_days(
        getattr(office, "office_hours", None) or [],
        start_day,
        end_day,
    )
    if open_errors:
        raise ValidationError({"pickup": open_errors})

    locked_item = InventoryItem.objects.select_for_update(of=("self",)).get(pk=item.pk)
    if not locked_item.is_reservable:
        raise AvailabilityConflict(
            {"form": [str(_("That item is not available to reserve right now."))]}
        )

    overlapping = overlapping_rows(locked_item.pk, interval)
    if not can_reserve_quantity(
        locked_item, interval, quantity, reservations=tuple(overlapping)
    ):
        raise AvailabilityConflict(
            {
                "form": [
                    str(
                        _(
                            "Not enough quantity is available for those dates. "
                            "Choose another range and try again."
                        )
                    )
                ]
            }
        )

    status = initial_status(requires_approval=locked_item.requires_approval)
    purpose_clean = (purpose or "").strip()[:240]
    instructions = (locked_item.notes or "").strip()
    storage = (locked_item.storage_location or "").strip()

    reservation = InventoryReservation(
        item=locked_item,
        owner=subject,
        office_id=locked_item.owner_office_id,
        office_name=office.name,
        item_name=locked_item.name,
        starts_at=interval.start,
        ends_at=interval.end,
        quantity=quantity,
        purpose=purpose_clean,
        status=status,
        instructions_snapshot=instructions,
        storage_location_snapshot=storage,
        submission_key=key,
        created_by=actor.user,
    )
    try:
        with allow_status_write(), transaction.atomic():
            reservation.save()
            if not reservation.reference:
                reservation.reference = next_reference(reservation.pk)
                reservation.save(update_fields=["reference", "updated_at"])
    except IntegrityError:
        existing = InventoryReservation.objects.filter(submission_key=key).first()
        if existing is not None:
            return existing, False
        raise

    ReservationTransitionEvent.objects.create(
        reservation=reservation,
        action="create",
        from_status="",
        to_status=reservation.status,
        actor=actor.user,
        metadata={"submission_key": key},
        idempotency_key=f"create:{key}",
    )

    log_on_commit(
        "inventory.reservation.created",
        actor=actor_from_user(actor.user),
        target=audit_target(reservation),
        metadata={
            "reservation_public_id": str(reservation.public_id),
            "item_public_id": str(locked_item.public_id),
            "status": reservation.status,
            "quantity": reservation.quantity,
            "starts_at": reservation.starts_at.isoformat(),
            "ends_at": reservation.ends_at.isoformat(),
            "owner_id": reservation.owner_id,
            "requires_approval": locked_item.requires_approval,
        },
    )
    return reservation, True


@transaction.atomic
def cancel_reservation(
    *,
    actor: ActorContext,
    reservation: InventoryReservation,
    reason: str = "",
    expected_version: str = "",
    expected_status: str | None = None,
) -> InventoryReservation:
    from apps.inventory.reservation_lifecycle import transition as lifecycle_transition

    override = actor.holds(ReservationPermission.OVERRIDE) and (
        reservation.owner_id != actor.user.pk
        or not agent_may_cancel(
            status=reservation.status, starts_at=reservation.starts_at
        )
    )
    try:
        return lifecycle_transition(
            actor=actor,
            reservation=reservation,
            action=ReservationAction.CANCEL.value,
            expected_version=expected_version,
            expected_status=expected_status,
            reason=reason,
            override=override,
            idempotency_key=(
                f"cancel:{reservation.pk}:"
                f"{expected_version or reservation.updated_at.isoformat()}"
            ),
        )
    except ValidationError as exc:
        message_dict = getattr(exc, "message_dict", None)
        if message_dict and message_dict.get("form"):
            raise CancelNotAllowed(message_dict) from exc
        raise
