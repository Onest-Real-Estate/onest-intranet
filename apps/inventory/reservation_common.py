"""Shared reservation helpers used by create/cancel and lifecycle services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.audit.service import AuditTarget, snapshot_model
from apps.inventory.availability import DateTimeInterval
from apps.inventory.capacity import peak_committed_quantity
from apps.inventory.models import InventoryItem, InventoryReservation

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
    "over_allocation_reason",
]


@dataclass(frozen=True)
class ActorContext:
    user: Any
    permissions: frozenset[str]

    def holds(self, *codenames: str) -> bool:
        if getattr(self.user, "is_superuser", False):
            return True
        return any(code in self.permissions for code in codenames)


def audit_target(reservation: InventoryReservation) -> AuditTarget:
    return AuditTarget(
        target_type=reservation._meta.label_lower,
        target_id=str(reservation.pk),
        target_label=reservation.reference or str(reservation.public_id),
        target_snapshot=snapshot_model(reservation, fields=AUDIT_FIELDS),
    )


def overlapping_rows(item_id: int, interval: DateTimeInterval):
    return list(
        InventoryReservation.objects.overlapping(
            item_id=item_id,
            starts_at=interval.start,
            ends_at=interval.end,
        ).only("pk", "item_id", "quantity", "starts_at", "ends_at")
    )


def committed_quantity_for_item(item: InventoryItem, *, now=None) -> int:
    del now  # Kept for API compatibility with earlier callers.
    return peak_committed_quantity(item)
