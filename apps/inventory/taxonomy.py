"""Inventory vocabulary: categories, conditions, tracking, and lifecycle.

Stable machine codes are stored; labels are presentation only. The lifecycle
lives here rather than on the model because reservation eligibility is a policy
question enforced in :mod:`apps.inventory.services` and
:mod:`apps.inventory.availability`.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _


class ItemCategory:
    FURNITURE = "furniture"
    ELECTRONICS = "electronics"
    SIGNAGE = "signage"
    MARKETING = "marketing"
    KEYS_LOCKBOX = "keys_lockbox"
    VEHICLE = "vehicle"
    OFFICE_SUPPLIES = "office_supplies"
    OTHER = "other"


CATEGORY_LABELS: dict[str, str] = {
    ItemCategory.FURNITURE: _("Furniture"),
    ItemCategory.ELECTRONICS: _("Electronics"),
    ItemCategory.SIGNAGE: _("Signage"),
    ItemCategory.MARKETING: _("Marketing materials"),
    ItemCategory.KEYS_LOCKBOX: _("Keys and lockboxes"),
    ItemCategory.VEHICLE: _("Vehicle"),
    ItemCategory.OFFICE_SUPPLIES: _("Office supplies"),
    ItemCategory.OTHER: _("Other"),
}

CATEGORY_CHOICES = tuple(CATEGORY_LABELS.items())
CATEGORY_CODES = frozenset(CATEGORY_LABELS)


class ItemCondition:
    NEW = "new"
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    NEEDS_REPAIR = "needs_repair"


CONDITION_LABELS: dict[str, str] = {
    ItemCondition.NEW: _("New"),
    ItemCondition.EXCELLENT: _("Excellent"),
    ItemCondition.GOOD: _("Good"),
    ItemCondition.FAIR: _("Fair"),
    ItemCondition.POOR: _("Poor"),
    ItemCondition.NEEDS_REPAIR: _("Needs repair"),
}

CONDITION_CHOICES = tuple(CONDITION_LABELS.items())
CONDITION_CODES = frozenset(CONDITION_LABELS)


class TrackingMode:
    SERIALIZED = "serialized"
    POOLED = "pooled"


TRACKING_LABELS: dict[str, str] = {
    TrackingMode.SERIALIZED: _("Individually serialized"),
    TrackingMode.POOLED: _("Pooled quantity"),
}

TRACKING_CHOICES = tuple(TRACKING_LABELS.items())
TRACKING_CODES = frozenset(TRACKING_LABELS)


class ItemAvailabilityState:
    """Operational availability — not collapsed into a single active boolean."""

    ACTIVE = "active"
    AVAILABLE = "available"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    DAMAGED = "damaged"
    LOST = "lost"
    RETIRED = "retired"


STATE_LABELS: dict[str, str] = {
    ItemAvailabilityState.ACTIVE: _("Active"),
    ItemAvailabilityState.AVAILABLE: _("Available for reservation"),
    ItemAvailabilityState.TEMPORARILY_UNAVAILABLE: _("Temporarily unavailable"),
    ItemAvailabilityState.DAMAGED: _("Damaged"),
    ItemAvailabilityState.LOST: _("Lost"),
    ItemAvailabilityState.RETIRED: _("Retired"),
}

STATE_CHOICES = tuple(STATE_LABELS.items())
STATE_CODES = frozenset(STATE_LABELS)

#: States from which a new reservation may be created. Interval overlap is
#: still checked separately in :mod:`apps.inventory.availability`.
RESERVABLE_STATES: frozenset[str] = frozenset(
    {
        ItemAvailabilityState.ACTIVE,
        ItemAvailabilityState.AVAILABLE,
    }
)

TERMINAL_STATES: frozenset[str] = frozenset({ItemAvailabilityState.RETIRED})

SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"USD", "CAD"})


class InventoryPermission:
    """Permission family for the inventory module."""

    VIEW = "web.view_inventory"
    MANAGE = "inventory.manage_inventory"
    VIEW_SENSITIVE = "inventory.view_inventory_sensitive"
