"""Inertia payloads for the agent reservation workflow."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.urls import reverse
from django.utils import timezone

from apps.inventory.browser import can_view_sensitive, serialize_agent_item
from apps.inventory.models import InventoryReservation
from apps.inventory.policy import cancel_cutoff_at, terms_summary
from apps.inventory.queries import item_for_agent
from apps.inventory.reservation_common import ActorContext
from apps.inventory.reservation_lifecycle import (
    reservation_version,
    serialize_available_actions,
    serialize_timeline,
)
from apps.inventory.reservation_taxonomy import ReservationStatus
from apps.inventory.reservations import build_preview
from apps.user.models import User
from apps.web.contracts import empty_validation_errors, list_response


def _return_calendar_day(reservation: InventoryReservation) -> str:
    """Inclusive return calendar day (``ends_at`` is exclusive next-midnight)."""
    local_end = timezone.localtime(reservation.ends_at)
    return (local_end - timedelta(microseconds=1)).date().isoformat()


def reservation_row(
    reservation: InventoryReservation, *, admin: bool = False
) -> dict[str, Any]:
    payload = {
        "publicId": str(reservation.public_id),
        "reference": reservation.reference,
        "itemName": reservation.item_name,
        "itemPublicId": str(reservation.item.public_id),
        "officeName": reservation.office_name,
        "quantity": reservation.quantity,
        "purpose": reservation.purpose,
        "status": reservation.status,
        "statusLabel": reservation.status_label,
        "startsAt": reservation.starts_at.isoformat(),
        "endsAt": reservation.ends_at.isoformat(),
        "pickupLabel": timezone.localtime(reservation.starts_at).date().isoformat(),
        "returnLabel": _return_calendar_day(reservation),
        "detailHref": reverse(
            "admin_reservation_detail" if admin else "inventory_reservation_detail",
            args=[str(reservation.public_id)],
        ),
    }
    if admin:
        owner = reservation.owner
        payload["owner"] = {
            "id": owner.pk,
            "name": owner.get_full_name() or owner.email,
            "email": owner.email,
        }
    return payload


def serialize_reservation_detail(
    reservation: InventoryReservation,
    *,
    viewer: User,
    actor: ActorContext | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    actor_ctx = actor or ActorContext(
        user=viewer, permissions=frozenset(viewer.get_all_permissions())
    )
    can_cancel = any(
        action["action"] == "cancel"
        for action in serialize_available_actions(reservation, actor_ctx)
    )
    cancel_cutoff = None
    if reservation.owner_id == viewer.pk:
        cancel_cutoff = cancel_cutoff_at(reservation.starts_at).isoformat()

    return {
        "publicId": str(reservation.public_id),
        "reference": reservation.reference,
        "itemName": reservation.item_name,
        "itemPublicId": str(reservation.item.public_id),
        "office": {
            "id": reservation.office_id,
            "name": reservation.office_name,
        },
        "owner": {
            "id": reservation.owner_id,
            "name": reservation.owner.get_full_name() or reservation.owner.email,
            "email": reservation.owner.email,
        }
        if admin
        else None,
        "quantity": reservation.quantity,
        "purpose": reservation.purpose,
        "status": reservation.status,
        "statusLabel": reservation.status_label,
        "expectedVersion": reservation_version(reservation),
        "startsAt": reservation.starts_at.isoformat(),
        "endsAt": reservation.ends_at.isoformat(),
        "pickupLabel": timezone.localtime(reservation.starts_at).date().isoformat(),
        "returnLabel": _return_calendar_day(reservation),
        "instructions": {
            "storageLocation": reservation.storage_location_snapshot,
            "notes": reservation.instructions_snapshot,
        },
        "terms": terms_summary(
            requires_approval=(
                reservation.status == ReservationStatus.REQUESTED
                or reservation.item.requires_approval
            )
        ),
        "canCancel": can_cancel,
        "cancelCutoffAt": cancel_cutoff,
        "cancelledAt": (
            reservation.cancelled_at.isoformat() if reservation.cancelled_at else None
        ),
        "checkedOutAt": (
            reservation.checked_out_at.isoformat()
            if reservation.checked_out_at
            else None
        ),
        "returnedAt": (
            reservation.returned_at.isoformat() if reservation.returned_at else None
        ),
        "completedAt": (
            reservation.completed_at.isoformat() if reservation.completed_at else None
        ),
        "checkoutQuantity": reservation.checkout_quantity,
        "returnQuantity": reservation.return_quantity,
        "returnConditionNotes": reservation.return_condition_notes,
        "createdAt": reservation.created_at.isoformat(),
        "timeline": serialize_timeline(reservation),
        "actions": serialize_available_actions(reservation, actor_ctx),
        "itemHref": reverse(
            "office_inventory_item", args=[str(reservation.item.public_id)]
        ),
        "myReservationsHref": reverse("inventory_reservations_mine"),
        "dashboardHref": reverse("dashboard"),
        "adminHref": reverse("admin_reservations") if admin else None,
    }


def build_new_reservation_page(
    actor: User,
    *,
    params,
    errors: dict[str, Any] | None = None,
    review: bool = False,
) -> dict[str, Any]:
    item_id = (params.get("item") or "").strip()
    pickup = (params.get("pickup") or "").strip()[:32]
    return_date = (params.get("return") or "").strip()[:32]
    purpose = (params.get("purpose") or "").strip()[:240]
    try:
        quantity = max(1, int(params.get("quantity") or "1"))
    except (TypeError, ValueError):
        quantity = 1

    item_payload = None
    if item_id:
        try:
            public_id = UUID(item_id)
        except ValueError:
            public_id = None
        if public_id is not None:
            item = item_for_agent(actor, public_id=public_id)
            if item is not None:
                item_payload = serialize_agent_item(
                    item,
                    include_sensitive=can_view_sensitive(actor),
                    include_guidance=True,
                )

    summary = None
    preview_errors = empty_validation_errors()
    if review and item_payload is not None:
        preview = build_preview(
            actor=actor,
            item_public_id=item_id,
            pickup=pickup,
            return_date=return_date,
            quantity=quantity,
            purpose=purpose,
        )
        summary = preview["summary"]
        preview_errors = preview["errors"]

    office = getattr(actor, "office", None)
    return {
        "item": item_payload,
        "draft": {
            "item": item_id if item_payload else "",
            "pickup": pickup,
            "return": return_date,
            "quantity": str(quantity),
            "purpose": purpose,
        },
        "review": bool(review and summary is not None),
        "summary": summary,
        "office": (
            {"id": office.pk, "name": office.name} if office is not None else None
        ),
        "links": {
            "inventoryHref": reverse("office_inventory"),
            "myReservationsHref": reverse("inventory_reservations_mine"),
            "dashboardHref": reverse("dashboard"),
        },
        "errors": errors or preview_errors,
    }


def build_mine_page(actor: User, *, page: int = 1) -> dict[str, Any]:
    page_size = 25
    qs = (
        InventoryReservation.objects.for_owner(actor)
        .select_related("item")
        .order_by("-starts_at", "-pk")
    )
    total = qs.count()
    start = max(page - 1, 0) * page_size
    rows = [reservation_row(row) for row in qs[start : start + page_size]]
    return {
        "reservations": list_response(
            rows,
            page=page,
            page_size=page_size,
            total_items=total,
            filters={},
        ),
        "links": {
            "inventoryHref": reverse("office_inventory"),
            "dashboardHref": reverse("dashboard"),
        },
        "errors": empty_validation_errors(),
    }
