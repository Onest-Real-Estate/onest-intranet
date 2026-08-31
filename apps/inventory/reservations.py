"""Agent inventory reservation writes: preview, create, cancel.

Create locks the inventory item row, recalculates overlapping capacity, and
inserts exactly one reservation. Availability previews are never trusted at
write time. Side effects (audit) run after commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _

from apps.audit.service import (
    AuditTarget,
    actor_from_user,
    log_on_commit,
    snapshot_model,
)
from apps.inventory.availability import (
    DateTimeInterval,
    available_quantity_for_range,
    can_reserve_quantity,
)
from apps.inventory.browser import parse_availability_interval
from apps.inventory.models import InventoryItem, InventoryReservation
from apps.inventory.policy import (
    agent_may_cancel,
    cancel_cutoff_at,
    initial_status,
    terms_summary,
    validate_horizon_and_duration,
    validate_office_open_days,
)
from apps.inventory.queries import item_for_agent
from apps.inventory.reservation_taxonomy import (
    CAPACITY_CONSUMING_STATES,
    ReservationPermission,
    ReservationStatus,
)
from apps.inventory.taxonomy import TrackingMode
from apps.user.models import User

AUDIT_FIELDS = [
    "reference",
    "status",
    "quantity",
    "starts_at",
    "ends_at",
    "office",
    "item",
    "owner",
    "purpose",
]


@dataclass(frozen=True)
class ActorContext:
    user: Any
    permissions: frozenset[str]

    def holds(self, *codenames: str) -> bool:
        if getattr(self.user, "is_superuser", False):
            return True
        return any(code in self.permissions for code in codenames)


class AvailabilityConflict(ValidationError):
    """Requested quantity is no longer available for the interval."""


class CancelNotAllowed(ValidationError):
    """Cancel refused by status or cutoff policy."""


def next_reference(pk: int) -> str:
    return f"INV-R-{pk:06d}"


def _audit_target(reservation: InventoryReservation) -> AuditTarget:
    return AuditTarget(
        target_type=reservation._meta.label_lower,
        target_id=str(reservation.pk),
        target_label=reservation.reference or str(reservation.public_id),
        target_snapshot=snapshot_model(reservation, fields=AUDIT_FIELDS),
    )


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


def committed_quantity_for_item(item: InventoryItem, *, now=None) -> int:
    """Units held by capacity-consuming reservations that have not ended."""
    moment = now or timezone.now()
    total = (
        InventoryReservation.objects.filter(
            item=item,
            status__in=sorted(CAPACITY_CONSUMING_STATES),
            ends_at__gt=moment,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    return int(total)


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
        # Same as a missing catalog row — do not disclose foreign-office existence.
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


def _overlapping_rows(item_id: int, interval: DateTimeInterval):
    return list(
        InventoryReservation.objects.overlapping(
            item_id=item_id,
            starts_at=interval.start,
            ends_at=interval.end,
        ).only("pk", "item_id", "quantity", "starts_at", "ends_at")
    )


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
    """Create one reservation or return the existing row for ``submission_key``.

    Returns ``(reservation, created)``. Concurrent capacity races raise
    :class:`AvailabilityConflict` without naming other reservation owners.
    """
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

    # Agents always reserve within their own primary-office catalog. On-behalf
    # still resolves the item through the subject's office in a later issue;
    # today the catalog gate uses the actor when self-serving.
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

    # Lock the capacity row. Do not select_related owner_office — nullable
    # joins break FOR UPDATE on PostgreSQL.
    locked_item = InventoryItem.objects.select_for_update(of=("self",)).get(pk=item.pk)
    if not locked_item.is_reservable:
        raise AvailabilityConflict(
            {"form": [str(_("That item is not available to reserve right now."))]}
        )

    overlapping = _overlapping_rows(locked_item.pk, interval)
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
        with transaction.atomic():
            reservation.save()
            if not reservation.reference:
                reservation.reference = next_reference(reservation.pk)
                reservation.save(update_fields=["reference", "updated_at"])
    except IntegrityError:
        # Lost the idempotency race — return the winner's row.
        existing = InventoryReservation.objects.filter(submission_key=key).first()
        if existing is not None:
            return existing, False
        raise

    log_on_commit(
        "inventory.reservation.created",
        actor=actor_from_user(actor.user),
        target=_audit_target(reservation),
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
) -> InventoryReservation:
    # Lock the capacity row first (same order as create) to avoid deadlocks.
    InventoryItem.objects.select_for_update(of=("self",)).get(pk=reservation.item_id)
    locked = InventoryReservation.objects.select_for_update(of=("self",)).get(
        pk=reservation.pk
    )
    if locked.owner_id != actor.user.pk and not actor.holds(
        ReservationPermission.OVERRIDE
    ):
        raise PermissionDenied("You do not have permission to cancel this reservation.")

    if locked.status == ReservationStatus.CANCELLED:
        return locked

    if locked.owner_id == actor.user.pk and not agent_may_cancel(
        status=locked.status, starts_at=locked.starts_at
    ):
        cutoff = cancel_cutoff_at(locked.starts_at)
        raise CancelNotAllowed(
            {
                "form": [
                    str(
                        _(
                            "This reservation can no longer be cancelled online "
                            "(cutoff %(cutoff)s). Contact your office for changes."
                        )
                        % {"cutoff": timezone.localtime(cutoff).isoformat()}
                    )
                ]
            }
        )

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    locked.status = ReservationStatus.CANCELLED
    locked.cancelled_at = timezone.now()
    locked.cancelled_by = actor.user
    locked.cancel_reason = (reason or "").strip()[:240]
    locked.full_clean()
    locked.save()

    log_on_commit(
        "inventory.reservation.cancelled",
        actor=actor_from_user(actor.user),
        target=_audit_target(locked),
        metadata={
            "before": before,
            "after": snapshot_model(locked, fields=AUDIT_FIELDS),
            "reservation_public_id": str(locked.public_id),
            "reason": locked.cancel_reason,
        },
    )
    return locked
