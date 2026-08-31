"""Agent-facing office inventory browser.

Scope is always the signed-in user's primary office — never a client-supplied
office id. Field projection deliberately omits replacement value, internal
notes, serial numbers, and other agents' reservation identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _

from apps.inventory.availability import (
    DateTimeInterval,
    available_quantity_for_range,
    can_reserve_quantity,
)
from apps.inventory.models import InventoryItem
from apps.inventory.queries import agent_inventory, item_for_agent
from apps.inventory.taxonomy import (
    CATEGORY_CHOICES,
    CATEGORY_CODES,
    CATEGORY_LABELS,
    CONDITION_CHOICES,
    CONDITION_CODES,
    CONDITION_LABELS,
    TRACKING_LABELS,
    InventoryPermission,
)
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission
from apps.web.contracts import list_response

PAGE_SIZE = 24
VIEW_MODES = frozenset({"grid", "list"})


@dataclass(frozen=True)
class AgentInventoryFilters:
    q: str = ""
    category: str = ""
    condition: str = ""
    pickup: str = ""
    return_date: str = ""
    quantity: int = 1
    view: str = "grid"
    available_only: bool = False

    def as_payload(self) -> dict[str, str]:
        return {
            "q": self.q,
            "category": self.category,
            "condition": self.condition,
            "pickup": self.pickup,
            "return": self.return_date,
            "quantity": str(self.quantity),
            "view": self.view,
            "available_only": "1" if self.available_only else "",
        }


def can_view_sensitive(actor: User) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    return has_effective_permission(actor, InventoryPermission.VIEW_SENSITIVE)


def parse_agent_filters(params) -> AgentInventoryFilters:
    category = (params.get("category") or "").strip()
    if category not in CATEGORY_CODES:
        category = ""
    condition = (params.get("condition") or "").strip()
    if condition not in CONDITION_CODES:
        condition = ""
    view = (params.get("view") or "").strip()
    if view not in VIEW_MODES:
        view = "grid"
    try:
        quantity = max(1, int(params.get("quantity") or "1"))
    except (TypeError, ValueError):
        quantity = 1
    available_only = (params.get("available_only") or "").lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    return AgentInventoryFilters(
        q=(params.get("q") or "").strip()[:120],
        category=category,
        condition=condition,
        pickup=(params.get("pickup") or "").strip()[:32],
        return_date=(params.get("return") or "").strip()[:32],
        quantity=quantity,
        view=view,
        available_only=available_only,
    )


def parse_availability_interval(
    pickup: str, return_date: str
) -> tuple[DateTimeInterval | None, list[str]]:
    """Convert calendar dates into an aware interval.

    Pickup is the start of that local day; return is exclusive midnight of the
    following day so a same-day range still has positive duration.
    """
    errors: list[str] = []
    if not pickup and not return_date:
        return None, errors
    if not pickup or not return_date:
        errors.append(str(_("Choose both a pickup date and a return date.")))
        return None, errors

    start_day = parse_date(pickup)
    end_day = parse_date(return_date)
    if start_day is None or end_day is None:
        errors.append(str(_("Enter valid pickup and return dates.")))
        return None, errors
    if end_day < start_day:
        errors.append(str(_("Return date must be on or after the pickup date.")))
        return None, errors

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_day, time.min), tz)
    end = timezone.make_aware(
        datetime.combine(end_day + timedelta(days=1), time.min), tz
    )
    try:
        return DateTimeInterval(start=start, end=end), errors
    except ValueError:
        errors.append(str(_("Return date must be on or after the pickup date.")))
        return None, errors


def reservation_windows_for_items(_item_ids: list[int]) -> tuple:
    """Committed reservation windows for availability math.

    Returns an empty tuple until the reservation model (#62) lands. Callers
    always go through this helper so interval math stays one plug-in point.
    """
    return ()


def _apply_agent_catalog_filters(
    queryset,
    filters: AgentInventoryFilters,
    *,
    include_asset_id: bool,
):
    from django.db.models import Q

    qs = queryset
    if filters.category:
        qs = qs.filter(category=filters.category)
    if filters.condition:
        qs = qs.filter(condition=filters.condition)
    if filters.q:
        term = filters.q
        match = Q(name__icontains=term)
        if include_asset_id:
            match |= Q(asset_id__icontains=term)
        qs = qs.filter(match)
    return qs.order_by("name", "pk")


def _photo_href(item: InventoryItem) -> str | None:
    if not item.photo or not item.photo_is_public:
        return None
    return reverse("office_inventory_photo", args=[item.public_id])


def _availability_payload(
    item: InventoryItem,
    interval: DateTimeInterval | None,
    *,
    quantity: int,
    reservations: tuple = (),
) -> dict[str, Any] | None:
    if interval is None:
        return None
    available = available_quantity_for_range(item, interval, reservations=reservations)
    can_reserve = can_reserve_quantity(
        item, interval, quantity, reservations=reservations
    )
    if can_reserve:
        reason = ""
        reason_label = ""
    elif available < 1:
        reason = "unavailable_range"
        reason_label = str(_("Not available for the selected dates."))
    else:
        reason = "insufficient_quantity"
        reason_label = str(_("Not enough quantity available for the selected dates."))
    return {
        "start": interval.start.isoformat(),
        "end": interval.end.isoformat(),
        "requestedQuantity": quantity,
        "availableQuantity": available,
        "totalQuantity": item.effective_quantity,
        "isAvailable": can_reserve,
        "reason": reason,
        "reasonLabel": reason_label,
    }


def _reserve_href(
    item: InventoryItem,
    *,
    pickup: str,
    return_date: str,
    quantity: int,
) -> str:
    """Carry item/date context into the reservation workflow placeholder.

    The reservation create surface (#62) revalidates every value; this href is
    navigation context only.
    """
    params = {"item": str(item.public_id), "quantity": str(quantity)}
    if pickup:
        params["pickup"] = pickup
    if return_date:
        params["return"] = return_date
    base = reverse("coming_soon", args=["my-reservations"])
    return f"{base}?{urlencode(params)}"


def serialize_agent_item(
    item: InventoryItem,
    *,
    include_sensitive: bool,
    availability: dict[str, Any] | None = None,
    include_guidance: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "publicId": str(item.public_id),
        "name": item.name,
        "category": item.category,
        "categoryLabel": str(CATEGORY_LABELS.get(item.category, item.category)),
        "trackingMode": item.tracking_mode,
        "trackingModeLabel": str(
            TRACKING_LABELS.get(item.tracking_mode, item.tracking_mode)
        ),
        "totalQuantity": item.effective_quantity,
        "condition": item.condition,
        "conditionLabel": str(CONDITION_LABELS.get(item.condition, item.condition)),
        "ownerOffice": {
            "id": item.owner_office.pk,
            "name": item.owner_office.name,
        },
        "hasPhoto": bool(item.photo and item.photo_is_public),
        "photoHref": _photo_href(item),
        "detailHref": reverse("office_inventory_item", args=[item.public_id]),
        "availability": availability,
        "myReservation": None,
    }
    if include_guidance:
        payload["storageLocation"] = item.storage_location
        payload["notes"] = item.notes
    if include_sensitive and item.asset_id:
        payload["assetId"] = item.asset_id
    return payload


def _empty_state(
    *,
    kind: str,
    title: str,
    description: str,
) -> dict[str, str]:
    return {"kind": kind, "title": title, "description": description}


def build_agent_inventory_page(
    actor: User,
    *,
    filters: AgentInventoryFilters,
    page: int = 1,
) -> dict[str, Any]:
    include_sensitive = can_view_sensitive(actor)
    office = getattr(actor, "office", None)
    interval, date_errors = parse_availability_interval(
        filters.pickup, filters.return_date
    )

    base: dict[str, Any] = {
        "office": (
            {"id": office.pk, "name": office.name}
            if office is not None and office.is_active
            else None
        ),
        "filterOptions": {
            "categories": [
                {"value": value, "label": str(label)}
                for value, label in CATEGORY_CHOICES
            ],
            "conditions": [
                {"value": value, "label": str(label)}
                for value, label in CONDITION_CHOICES
            ],
        },
        "capabilities": {"canViewSensitive": include_sensitive},
        "dateErrors": date_errors,
        "serviceError": None,
    }

    if office is None or not office.is_active:
        return {
            **base,
            "items": list_response(
                [],
                page=1,
                page_size=PAGE_SIZE,
                total_items=0,
                filters=filters.as_payload(),
            ),
            "empty": _empty_state(
                kind="no-office",
                title=str(_("No office assigned")),
                description=str(
                    _(
                        "Your profile does not have a primary office yet. "
                        "Update your profile or contact your branch administrator."
                    )
                ),
            ),
        }

    if not office.is_assignable:
        return {
            **base,
            "items": list_response(
                [],
                page=1,
                page_size=PAGE_SIZE,
                total_items=0,
                filters=filters.as_payload(),
            ),
            "empty": _empty_state(
                kind="no-office",
                title=str(_("Office cannot hold inventory")),
                description=str(
                    _(
                        "Your assigned office is not set up for reservable inventory. "
                        "Contact your branch administrator."
                    )
                ),
            ),
        }

    catalog = agent_inventory(actor)
    scoped = _apply_agent_catalog_filters(
        catalog,
        filters,
        include_asset_id=include_sensitive,
    )
    catalog_exists = catalog.exists()
    must_scan = filters.available_only and interval is not None
    page = max(1, page)

    if must_scan:
        filtered_rows = list(scoped)
        reservations = reservation_windows_for_items(
            [item.pk for item in filtered_rows]
        )
        rows_with_availability: list[tuple[InventoryItem, dict[str, Any] | None]] = []
        for item in filtered_rows:
            availability = _availability_payload(
                item,
                interval,
                quantity=filters.quantity,
                reservations=reservations,
            )
            if availability is None or not availability["isAvailable"]:
                continue
            rows_with_availability.append((item, availability))
        total = len(rows_with_availability)
        start = (page - 1) * PAGE_SIZE
        page_slice = rows_with_availability[start : start + PAGE_SIZE]
    else:
        total = scoped.count()
        start = (page - 1) * PAGE_SIZE
        page_rows = list(scoped[start : start + PAGE_SIZE])
        reservations = reservation_windows_for_items([item.pk for item in page_rows])
        page_slice = [
            (
                item,
                _availability_payload(
                    item,
                    interval,
                    quantity=filters.quantity,
                    reservations=reservations,
                ),
            )
            for item in page_rows
        ]

    items = [
        serialize_agent_item(
            item,
            include_sensitive=include_sensitive,
            availability=availability,
            include_guidance=True,
        )
        for item, availability in page_slice
    ]
    for row, (item, _availability) in zip(items, page_slice, strict=True):
        row["reserveHref"] = _reserve_href(
            item,
            pickup=filters.pickup,
            return_date=filters.return_date,
            quantity=filters.quantity,
        )

    filtered = bool(
        filters.q
        or filters.category
        or filters.condition
        or filters.available_only
        or (filters.pickup and filters.return_date)
    )
    if total:
        empty = None
    elif not catalog_exists:
        empty = _empty_state(
            kind="no-items",
            title=str(_("No inventory yet")),
            description=str(
                _(
                    "Your office has no reservable items yet. "
                    "Ask your branch administrator when stock is ready."
                )
            ),
        )
    elif filters.available_only and interval is not None:
        empty = _empty_state(
            kind="unavailable-range",
            title=str(_("Nothing available for those dates")),
            description=str(
                _(
                    "No items have enough open capacity for the selected pickup "
                    "and return dates. Try different dates or clear the "
                    "availability filter."
                )
            ),
        )
    elif filtered:
        empty = _empty_state(
            kind="no-results",
            title=str(_("No matching items")),
            description=str(
                _("Nothing matches your search. Try a different term or filter.")
            ),
        )
    else:
        empty = _empty_state(
            kind="no-items",
            title=str(_("No inventory yet")),
            description=str(
                _(
                    "Your office has no reservable items yet. "
                    "Ask your branch administrator when stock is ready."
                )
            ),
        )

    return {
        **base,
        "items": list_response(
            items,
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters.as_payload(),
        ),
        "empty": empty,
    }


def build_agent_item_detail(
    actor: User,
    public_id: UUID | str,
    *,
    filters: AgentInventoryFilters,
) -> dict[str, Any] | None:
    include_sensitive = can_view_sensitive(actor)
    item = item_for_agent(actor, public_id=public_id)
    if item is None:
        return None

    interval, date_errors = parse_availability_interval(
        filters.pickup, filters.return_date
    )
    reservations = reservation_windows_for_items([item.pk])
    availability = _availability_payload(
        item,
        interval,
        quantity=filters.quantity,
        reservations=reservations,
    )
    payload = serialize_agent_item(
        item,
        include_sensitive=include_sensitive,
        availability=availability,
        include_guidance=True,
    )
    payload["reserveHref"] = _reserve_href(
        item,
        pickup=filters.pickup,
        return_date=filters.return_date,
        quantity=filters.quantity,
    )
    office = getattr(actor, "office", None)
    return {
        "item": payload,
        "office": (
            {"id": office.pk, "name": office.name} if office is not None else None
        ),
        "filters": filters.as_payload(),
        "filterOptions": {
            "categories": [
                {"value": value, "label": str(label)}
                for value, label in CATEGORY_CHOICES
            ],
            "conditions": [
                {"value": value, "label": str(label)}
                for value, label in CONDITION_CHOICES
            ],
        },
        "capabilities": {"canViewSensitive": include_sensitive},
        "dateErrors": date_errors,
        "serviceError": None,
    }
