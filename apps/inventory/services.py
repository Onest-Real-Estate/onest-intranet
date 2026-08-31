"""Inventory lifecycle writes: create, update, retire, and transfer.

Every mutation follows the operational-tasks shape: authorize, lock, validate,
write, audit on commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.service import (
    actor_from_user,
    log_on_commit,
    snapshot_model,
    target_from_instance,
)
from apps.inventory.availability import DateTimeInterval, can_reserve_quantity
from apps.inventory.models import InventoryItem, InventoryTransfer
from apps.inventory.queries import office_assignable_for_inventory
from apps.inventory.taxonomy import (
    CATEGORY_CODES,
    CONDITION_CODES,
    TRACKING_CODES,
    InventoryPermission,
    ItemAvailabilityState,
    TrackingMode,
)
from apps.user.models import Office

AUDIT_FIELDS = [
    "name",
    "owner_office",
    "category",
    "tracking_mode",
    "asset_id",
    "total_quantity",
    "condition",
    "availability_state",
    "storage_location",
    "retired_at",
]


@dataclass(frozen=True)
class ActorContext:
    user: Any
    permissions: frozenset[str]

    def holds(self, *codenames: str) -> bool:
        if getattr(self.user, "is_superuser", False):
            return True
        return any(code in self.permissions for code in codenames)


def _require(actor: ActorContext, *codenames: str) -> None:
    if not actor.holds(*codenames):
        raise PermissionDenied("You do not have permission to change inventory.")


def _validate_owner_office(office: Office) -> None:
    if not office_assignable_for_inventory(office):
        raise ValidationError(
            {
                "owner_office": (
                    "Only active, assignable offices may own reservable inventory."
                )
            }
        )


def _snapshot(item: InventoryItem) -> dict:
    return snapshot_model(item, fields=AUDIT_FIELDS)


@transaction.atomic
def create_item(
    *,
    actor: ActorContext,
    owner_office: Office,
    name: str,
    category: str,
    tracking_mode: str,
    condition: str,
    asset_id: str = "",
    serial_number: str = "",
    total_quantity: int = 1,
    availability_state: str = ItemAvailabilityState.AVAILABLE,
    storage_location: str = "",
    notes: str = "",
    internal_notes: str = "",
    replacement_value: Decimal | None = None,
    replacement_currency: str = "USD",
) -> InventoryItem:
    _require(actor, InventoryPermission.MANAGE)
    _validate_owner_office(owner_office)

    if category not in CATEGORY_CODES:
        raise ValidationError({"category": "Unknown category."})
    if condition not in CONDITION_CODES:
        raise ValidationError({"condition": "Unknown condition."})
    if tracking_mode not in TRACKING_CODES:
        raise ValidationError({"tracking_mode": "Unknown tracking mode."})

    now = timezone.now()
    item = InventoryItem(
        owner_office=owner_office,
        name=name.strip(),
        category=category,
        tracking_mode=tracking_mode,
        asset_id=asset_id.strip(),
        serial_number=serial_number.strip(),
        total_quantity=total_quantity,
        condition=condition,
        availability_state=availability_state,
        storage_location=storage_location.strip(),
        notes=notes.strip(),
        internal_notes=internal_notes.strip(),
        replacement_value=replacement_value,
        replacement_currency=replacement_currency,
        activated_at=now
        if availability_state != ItemAvailabilityState.RETIRED
        else None,
        created_by=actor.user,
        updated_by=actor.user,
    )
    item.full_clean()
    item.save()

    log_on_commit(
        "inventory.item.created",
        actor=actor_from_user(actor.user),
        target=target_from_instance(item),
        metadata={"after": _snapshot(item)},
    )
    return item


@transaction.atomic
def update_item(
    *,
    actor: ActorContext,
    item: InventoryItem,
    **fields,
) -> InventoryItem:
    _require(actor, InventoryPermission.MANAGE)
    locked = InventoryItem.objects.select_for_update(of=("self",)).get(pk=item.pk)
    before = _snapshot(locked)

    mutable = {
        "name",
        "category",
        "condition",
        "availability_state",
        "storage_location",
        "notes",
        "internal_notes",
        "replacement_value",
        "replacement_currency",
        "photo_is_public",
    }
    if locked.tracking_mode == TrackingMode.POOLED and "total_quantity" in fields:
        mutable.add("total_quantity")

    for key, value in fields.items():
        if key not in mutable:
            raise ValidationError({key: "This field cannot be changed here."})
        setattr(locked, key, value)

    locked.updated_by = actor.user
    locked.full_clean()
    locked.save()

    log_on_commit(
        "inventory.item.updated",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked),
        metadata={"before": before, "after": _snapshot(locked)},
    )
    return locked


@transaction.atomic
def retire_item(*, actor: ActorContext, item: InventoryItem) -> InventoryItem:
    _require(actor, InventoryPermission.MANAGE)
    locked = InventoryItem.objects.select_for_update(of=("self",)).get(pk=item.pk)
    if locked.is_retired:
        raise ValidationError("This item is already retired.")

    before = _snapshot(locked)
    now = timezone.now()
    locked.availability_state = ItemAvailabilityState.RETIRED
    locked.retired_at = now
    locked.updated_by = actor.user
    locked.full_clean()
    locked.save()

    log_on_commit(
        "inventory.item.retired",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked),
        metadata={"before": before, "after": _snapshot(locked)},
    )
    return locked


class TransferConflict(ValidationError):
    """Destination office cannot accept the item because of future reservations."""


@transaction.atomic
def transfer_item(
    *,
    actor: ActorContext,
    item: InventoryItem,
    to_office: Office,
    reason: str = "",
    future_reservations: tuple = (),
    requested_interval: DateTimeInterval | None = None,
) -> InventoryTransfer:
    """Move inventory between offices with audit trail.

    ``future_reservations`` is supplied by the reservation module once it ships.
    When any overlapping reservation would be incompatible with the destination
    office policy, the transfer is rejected.
    """
    _require(actor, InventoryPermission.MANAGE)
    _validate_owner_office(to_office)

    locked = InventoryItem.objects.select_for_update(of=("self",)).get(pk=item.pk)
    if locked.is_retired:
        raise ValidationError("Retired items cannot be transferred.")
    if locked.owner_office.pk == to_office.pk:
        raise ValidationError("Item is already owned by this office.")

    if (
        requested_interval is not None
        and future_reservations
        and not can_reserve_quantity(
            locked,
            requested_interval,
            locked.effective_quantity,
            reservations=future_reservations,
        )
    ):
        raise TransferConflict(
            "Future reservations are incompatible with this transfer."
        )

    before = _snapshot(locked)
    from_office = locked.owner_office
    locked.owner_office = to_office
    locked.updated_by = actor.user
    locked.full_clean()
    locked.save()

    transfer = InventoryTransfer.objects.create(
        item=locked,
        from_office=from_office,
        to_office=to_office,
        performed_by=actor.user,
        reason=reason.strip(),
    )

    log_on_commit(
        "inventory.item.transferred",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked),
        metadata={
            "before": before,
            "after": _snapshot(locked),
            "transfer_id": str(transfer.public_id),
            "from_office": from_office.stable_key,
            "to_office": to_office.stable_key,
        },
    )
    return transfer
