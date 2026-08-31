from django.contrib import admin

from apps.inventory.models import InventoryItem, InventoryTransfer


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner_office",
        "tracking_mode",
        "availability_state",
        "total_quantity",
    )
    list_filter = ("tracking_mode", "availability_state", "category")
    search_fields = ("name", "asset_id", "serial_number")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(InventoryTransfer)
class InventoryTransferAdmin(admin.ModelAdmin):
    list_display = ("item", "from_office", "to_office", "performed_at")
    readonly_fields = ("public_id", "performed_at")
