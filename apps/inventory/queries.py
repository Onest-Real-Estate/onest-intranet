"""Scoped inventory query services.

Every list endpoint must call one of these helpers before serialization.
Filtering by office, category, state, tracking mode, and search happens here
so indexes are used and scope cannot be widened later in Python.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q, QuerySet

from apps.inventory.models import InventoryItem
from apps.inventory.taxonomy import (
    CATEGORY_CODES,
    STATE_CODES,
    TRACKING_CODES,
)
from apps.user.models import Office, User


@dataclass(frozen=True)
class InventoryFilters:
    q: str = ""
    category: str = ""
    state: str = ""
    tracking_mode: str = ""

    @classmethod
    def from_params(cls, params) -> InventoryFilters:
        category = (params.get("category") or "").strip()
        if category not in CATEGORY_CODES:
            category = ""
        state = (params.get("state") or "").strip()
        if state not in STATE_CODES:
            state = ""
        tracking_mode = (params.get("tracking_mode") or "").strip()
        if tracking_mode not in TRACKING_CODES:
            tracking_mode = ""
        return cls(
            q=(params.get("q") or "").strip()[:120],
            category=category,
            state=state,
            tracking_mode=tracking_mode,
        )


def apply_filters(
    queryset: QuerySet[InventoryItem], filters: InventoryFilters
) -> QuerySet[InventoryItem]:
    qs = queryset
    if filters.category:
        qs = qs.filter(category=filters.category)
    if filters.state:
        qs = qs.filter(availability_state=filters.state)
    if filters.tracking_mode:
        qs = qs.filter(tracking_mode=filters.tracking_mode)
    if filters.q:
        term = filters.q
        qs = qs.filter(
            Q(name__icontains=term)
            | Q(asset_id__icontains=term)
            | Q(storage_location__icontains=term)
        )
    return qs.order_by("name", "pk")


def manager_inventory(
    user: User,
    *,
    access,
    filters: InventoryFilters | None = None,
    include_retired: bool = False,
) -> QuerySet[InventoryItem]:
    """Inventory visible to a manager with ``web.view_inventory``."""
    qs = InventoryItem.objects.for_manager(user, access=access).select_related(
        "owner_office", "owner_office__region"
    )
    if not include_retired:
        qs = qs.active_catalog()
    if filters is not None:
        qs = apply_filters(qs, filters)
    return qs


def agent_inventory(
    user: User,
    *,
    filters: InventoryFilters | None = None,
) -> QuerySet[InventoryItem]:
    """Active reservable items for the reader's primary office."""
    office = getattr(user, "office", None)
    qs = InventoryItem.objects.for_agent_office(office).select_related("owner_office")
    if filters is not None:
        qs = apply_filters(qs, filters)
    return qs


def item_for_manager(
    user: User,
    *,
    access,
    public_id,
    include_retired: bool = False,
) -> InventoryItem | None:
    qs = manager_inventory(user, access=access, include_retired=include_retired).filter(
        public_id=public_id
    )
    return qs.first()


def item_for_agent(user: User, *, public_id) -> InventoryItem | None:
    return agent_inventory(user).filter(public_id=public_id).first()


def office_assignable_for_inventory(office: Office | None) -> bool:
    return office is not None and office.is_active and office.is_assignable
