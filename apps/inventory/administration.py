"""Scoped inventory administration — list, detail, and write helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _

from apps.inventory.availability import DateTimeInterval, available_quantity_for_range
from apps.inventory.models import InventoryItem, InventoryTransfer
from apps.inventory.payloads import serialize_item
from apps.inventory.taxonomy import (
    CATEGORY_CHOICES,
    CONDITION_CHOICES,
    STATE_LABELS,
    TRACKING_CHOICES,
    InventoryPermission,
)
from apps.user.models import Office, User
from apps.user.services.hierarchy import descendant_queryset
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)
from apps.web.contracts import list_response

PAGE_SIZE = 50

SORT_KEYS: frozenset[str] = frozenset(
    {"name", "category", "tracking", "quantity", "state", "office"}
)

_SORT_FIELDS: dict[str, tuple[str, ...]] = {
    "name": ("name", "pk"),
    "category": ("category", "name", "pk"),
    "tracking": ("tracking_mode", "name", "pk"),
    "quantity": ("total_quantity", "name", "pk"),
    "state": ("availability_state", "name", "pk"),
    "office": ("owner_office__name", "name", "pk"),
}


@dataclass(frozen=True)
class InventoryScope:
    office_ids: frozenset[int]


class StaleItemVersion(Exception):
    """Optimistic concurrency token no longer matches the item row."""


@dataclass(frozen=True)
class AdminInventoryFilters:
    q: str = ""
    category: str = ""
    tracking_mode: str = ""
    condition: str = ""
    state: str = ""
    owner: str = ""
    include_retired: bool = False

    def as_payload(self) -> dict[str, str]:
        payload = {
            "q": self.q,
            "category": self.category,
            "tracking_mode": self.tracking_mode,
            "condition": self.condition,
            "state": self.state,
            "owner": self.owner,
            "include_retired": "true" if self.include_retired else "",
        }
        return payload


def _has_permission(actor: User, codename: str) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    return has_effective_permission(actor, codename)


def inventory_scope(actor: User) -> InventoryScope:
    """Writable assignable offices for this actor."""
    access = get_effective_access(actor)
    assignable = Q(is_active=True, is_assignable=True)
    ids: set[int] = set()
    if getattr(actor, "is_superuser", False) or access.company_wide:
        ids.update(Office.objects.filter(assignable).values_list("pk", flat=True))
        return InventoryScope(office_ids=frozenset(ids))

    if access.region_keys:
        regions = Office.objects.filter(
            kind=Office.Kind.REGION, stable_key__in=access.region_keys
        )
        for region in regions:
            ids.update(
                descendant_queryset(region)
                .filter(assignable)
                .values_list("pk", flat=True)
            )
    if access.office_keys:
        seats = Office.objects.filter(stable_key__in=access.office_keys)
        for seat in seats:
            if seat.is_assignable and seat.is_active:
                ids.add(seat.pk)
            if seat.kind != Office.Kind.BRANCH:
                ids.update(
                    descendant_queryset(seat)
                    .filter(assignable)
                    .values_list("pk", flat=True)
                )
    return InventoryScope(office_ids=frozenset(ids))


def can_view_inventory(actor: User) -> bool:
    return _has_permission(actor, InventoryPermission.VIEW)


def can_manage_inventory(actor: User) -> bool:
    return _has_permission(actor, InventoryPermission.MANAGE)


def can_view_sensitive(actor: User) -> bool:
    return _has_permission(actor, InventoryPermission.VIEW_SENSITIVE)


def actor_permissions(actor: User) -> frozenset[str]:
    perms = set()
    if can_view_inventory(actor):
        perms.add(InventoryPermission.VIEW)
    if can_manage_inventory(actor):
        perms.add(InventoryPermission.MANAGE)
    if can_view_sensitive(actor):
        perms.add(InventoryPermission.VIEW_SENSITIVE)
    return frozenset(perms)


def ensure_view_authority(actor: User) -> None:
    if not can_view_inventory(actor):
        raise PermissionDenied(_("You do not have permission to view inventory."))


def ensure_manage_authority(actor: User, owner: Office | None = None) -> InventoryScope:
    scope = inventory_scope(actor)
    if not can_manage_inventory(actor):
        raise PermissionDenied(_("You do not have permission to manage inventory."))
    if owner is not None and owner.pk not in scope.office_ids:
        raise PermissionDenied(
            _("That owning office is outside your administrative scope.")
        )
    return scope


def managed_item_queryset(actor: User) -> QuerySet[InventoryItem]:
    access = get_effective_access(actor)
    return InventoryItem.objects.for_manager(actor, access=access).select_related(
        "owner_office", "owner_office__region"
    )


def load_item(actor: User, public_id) -> InventoryItem | None:
    return managed_item_queryset(actor).filter(public_id=public_id).first()


def item_version(item: InventoryItem) -> str:
    stamp = item.updated_at.isoformat(timespec="microseconds")
    return f"{item.pk}:{stamp}"


def assert_item_version(item: InventoryItem, expected: str) -> None:
    if item_version(item) != expected.strip():
        raise StaleItemVersion


def parse_sort(params) -> tuple[str, str]:
    key = (params.get("sort") or "").strip()
    if key not in SORT_KEYS:
        key = "name"
    direction = "desc" if (params.get("direction") or "").strip() == "desc" else "asc"
    return key, direction


def _apply_sort(
    queryset: QuerySet[InventoryItem], sort_key: str, sort_direction: str
) -> QuerySet[InventoryItem]:
    fields = _SORT_FIELDS.get(sort_key, _SORT_FIELDS["name"])
    prefix = "-" if sort_direction == "desc" else ""
    return queryset.order_by(*(f"{prefix}{field}" for field in fields))


def parse_admin_filters(params) -> AdminInventoryFilters:
    from apps.inventory.taxonomy import CATEGORY_CODES, STATE_CODES, TRACKING_CODES

    category = (params.get("category") or "").strip()
    if category not in CATEGORY_CODES:
        category = ""
    tracking_mode = (params.get("tracking_mode") or "").strip()
    if tracking_mode not in TRACKING_CODES:
        tracking_mode = ""
    condition = (params.get("condition") or "").strip()
    if condition not in {code for code, _ in CONDITION_CHOICES}:
        condition = ""
    state = (params.get("state") or "").strip()
    if state not in STATE_CODES:
        state = ""
    include_retired = (params.get("include_retired") or "").lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    return AdminInventoryFilters(
        q=(params.get("q") or "").strip()[:120],
        category=category,
        tracking_mode=tracking_mode,
        condition=condition,
        state=state,
        owner=(params.get("owner") or "").strip()[:80],
        include_retired=include_retired,
    )


def _apply_admin_filters(
    queryset: QuerySet[InventoryItem],
    filters: AdminInventoryFilters,
    *,
    sort_key: str = "name",
    sort_direction: str = "asc",
) -> QuerySet[InventoryItem]:
    qs = queryset
    if not filters.include_retired:
        qs = qs.active_catalog()
    if filters.category:
        qs = qs.filter(category=filters.category)
    if filters.tracking_mode:
        qs = qs.filter(tracking_mode=filters.tracking_mode)
    if filters.condition:
        qs = qs.filter(condition=filters.condition)
    if filters.state:
        qs = qs.filter(availability_state=filters.state)
    if filters.owner:
        qs = qs.filter(owner_office__stable_key=filters.owner)
    if filters.q:
        qs = qs.filter(
            Q(name__icontains=filters.q)
            | Q(asset_id__icontains=filters.q)
            | Q(storage_location__icontains=filters.q)
        )
    return _apply_sort(qs, sort_key, sort_direction)


def _admin_row(item: InventoryItem, *, permissions: frozenset[str]) -> dict[str, Any]:
    row = serialize_item(item, permissions=permissions, include_retired_fields=False)
    row["version"] = item_version(item)
    row["detailHref"] = f"/operations/inventory/{item.public_id}"
    return row


def writable_offices(actor: User) -> QuerySet[Office]:
    scope = inventory_scope(actor)
    if not scope.office_ids:
        return Office.objects.none()
    return (
        Office.objects.filter(pk__in=scope.office_ids)
        .select_related("region", "parent")
        .order_by("sort_order", "name")
    )


def build_inventory_list(
    actor: User,
    *,
    filters: AdminInventoryFilters,
    page: int = 1,
    sort_key: str = "name",
    sort_direction: str = "asc",
) -> dict[str, Any]:
    ensure_view_authority(actor)
    permissions = actor_permissions(actor)
    queryset = _apply_admin_filters(
        managed_item_queryset(actor),
        filters,
        sort_key=sort_key,
        sort_direction=sort_direction,
    )
    total = queryset.count()
    page = max(1, page)
    start = (page - 1) * PAGE_SIZE
    rows = [
        _admin_row(item, permissions=permissions)
        for item in queryset[start : start + PAGE_SIZE]
    ]
    offices = writable_offices(actor)
    return {
        "items": list_response(
            rows,
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters.as_payload(),
            sort_key=sort_key,
            sort_direction=sort_direction,
        ),
        "writableOffices": [
            {"id": node.pk, "label": node.path_label(), "kind": node.kind}
            for node in offices
        ],
        "filterOptions": {
            "categories": [
                {"value": value, "label": str(label)}
                for value, label in CATEGORY_CHOICES
            ],
            "trackingModes": [
                {"value": value, "label": str(label)}
                for value, label in TRACKING_CHOICES
            ],
            "conditions": [
                {"value": value, "label": str(label)}
                for value, label in CONDITION_CHOICES
            ],
            "states": [
                {"value": value, "label": str(label)}
                for value, label in STATE_LABELS.items()
            ],
            "owners": [
                {"value": node.stable_key, "label": node.path_label()}
                for node in offices
            ],
        },
        "capabilities": {
            "canManage": can_manage_inventory(actor),
            "canViewSensitive": can_view_sensitive(actor),
        },
    }


def _parse_interval(start_raw: str, end_raw: str) -> DateTimeInterval | None:
    start = parse_datetime(start_raw.strip()) if start_raw else None
    end = parse_datetime(end_raw.strip()) if end_raw else None
    if start is None or end is None:
        return None
    return DateTimeInterval(start=start, end=end)


def detail_payload(
    actor: User,
    item: InventoryItem | None,
    *,
    availability_start: str = "",
    availability_end: str = "",
) -> dict[str, Any]:
    ensure_view_authority(actor)
    permissions = actor_permissions(actor)
    offices = writable_offices(actor)
    payload: dict[str, Any] = {
        "item": serialize_item(item, permissions=permissions)
        if item is not None
        else None,
        "version": item_version(item) if item is not None else "",
        "writableOffices": [
            {"id": node.pk, "label": node.path_label(), "kind": node.kind}
            for node in offices
        ],
        "capabilities": {
            "canManage": can_manage_inventory(actor),
            "canViewSensitive": can_view_sensitive(actor),
        },
        "filterOptions": {
            "categories": [
                {"value": value, "label": str(label)}
                for value, label in CATEGORY_CHOICES
            ],
            "trackingModes": [
                {"value": value, "label": str(label)}
                for value, label in TRACKING_CHOICES
            ],
            "conditions": [
                {"value": value, "label": str(label)}
                for value, label in CONDITION_CHOICES
            ],
        },
        "transfers": [],
        "reservations": [],
        "committedQuantity": 0,
        "availabilityPreview": None,
    }
    if item is None:
        return payload

    from apps.inventory.services import committed_quantity

    payload["committedQuantity"] = committed_quantity(item)
    payload["transfers"] = [
        {
            "publicId": str(transfer.public_id),
            "fromOffice": transfer.from_office.path_label(),
            "toOffice": transfer.to_office.path_label(),
            "performedAt": transfer.performed_at.isoformat(),
            "reason": transfer.reason,
        }
        for transfer in InventoryTransfer.objects.filter(item=item)
        .select_related("from_office", "to_office")
        .order_by("-performed_at")[:20]
    ]

    interval = _parse_interval(availability_start, availability_end)
    if interval is not None:
        payload["availabilityPreview"] = {
            "start": interval.start.isoformat(),
            "end": interval.end.isoformat(),
            "availableQuantity": available_quantity_for_range(item, interval),
            "totalQuantity": item.total_quantity,
            "physicalState": item.availability_state,
            "physicalStateLabel": item.availability_state_label,
            "isReservableCatalogState": item.is_reservable,
        }
    return payload
