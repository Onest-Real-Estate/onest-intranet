"""Inventory presentation payloads with field-level permission gates."""

from __future__ import annotations

from apps.inventory.models import InventoryItem
from apps.inventory.taxonomy import (
    CATEGORY_LABELS,
    CONDITION_LABELS,
    TRACKING_LABELS,
    InventoryPermission,
)


def serialize_item(
    item: InventoryItem,
    *,
    permissions: frozenset[str],
    include_retired_fields: bool = True,
) -> dict:
    can_view_sensitive = (
        InventoryPermission.VIEW_SENSITIVE in permissions
        or InventoryPermission.MANAGE in permissions
    )

    payload: dict = {
        "publicId": str(item.public_id),
        "name": item.name,
        "category": item.category,
        "categoryLabel": str(CATEGORY_LABELS.get(item.category, item.category)),
        "trackingMode": item.tracking_mode,
        "trackingModeLabel": str(
            TRACKING_LABELS.get(item.tracking_mode, item.tracking_mode)
        ),
        "totalQuantity": item.total_quantity,
        "effectiveQuantity": item.effective_quantity,
        "condition": item.condition,
        "conditionLabel": str(CONDITION_LABELS.get(item.condition, item.condition)),
        "availabilityState": item.availability_state,
        "availabilityStateLabel": item.availability_state_label,
        "isReservable": item.is_reservable,
        "storageLocation": item.storage_location,
        "notes": item.notes,
        "photoIsPublic": item.photo_is_public,
        "requiresApproval": item.requires_approval,
        "hasPhoto": bool(item.photo),
        "ownerOffice": {
            "id": item.owner_office.pk,
            "stableKey": item.owner_office.stable_key,
            "name": item.owner_office.name,
        },
        "createdAt": item.created_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
    }

    if include_retired_fields:
        payload["retiredAt"] = item.retired_at.isoformat() if item.retired_at else None
        payload["activatedAt"] = (
            item.activated_at.isoformat() if item.activated_at else None
        )

    if can_view_sensitive:
        payload["assetId"] = item.asset_id
        payload["serialNumber"] = item.serial_number
        payload["internalNotes"] = item.internal_notes
        if item.replacement_value is not None:
            payload["replacementValue"] = str(item.replacement_value)
            payload["replacementCurrency"] = item.replacement_currency

    return payload
