from django.contrib import admin

from apps.inventory.models import (
    InventoryItem,
    InventoryReservation,
    InventoryTransfer,
    ReservationTransitionEvent,
)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner_office",
        "tracking_mode",
        "availability_state",
        "total_quantity",
        "requires_approval",
    )
    list_filter = (
        "tracking_mode",
        "availability_state",
        "category",
        "requires_approval",
    )
    search_fields = ("name", "asset_id", "serial_number")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(InventoryTransfer)
class InventoryTransferAdmin(admin.ModelAdmin):
    list_display = ("item", "from_office", "to_office", "performed_at")
    readonly_fields = ("public_id", "performed_at")


@admin.register(InventoryReservation)
class InventoryReservationAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "item_name",
        "owner",
        "status",
        "starts_at",
        "ends_at",
        "quantity",
    )
    list_filter = ("status",)
    search_fields = ("reference", "item_name", "purpose")
    readonly_fields = (
        "public_id",
        "reference",
        "submission_key",
        "status",
        "created_at",
        "updated_at",
    )


@admin.register(ReservationTransitionEvent)
class ReservationTransitionEventAdmin(admin.ModelAdmin):
    list_display = ("reservation", "action", "from_status", "to_status", "occurred_at")
    readonly_fields = (
        "reservation",
        "action",
        "from_status",
        "to_status",
        "actor",
        "reason",
        "notes",
        "metadata",
        "idempotency_key",
        "occurred_at",
    )
