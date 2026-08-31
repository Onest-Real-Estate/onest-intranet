"""Inventory app URL routes."""

from django.urls import path

from apps.inventory.views.administration_views import (
    inventory_admin_index,
    inventory_item_create,
    inventory_item_detail,
    inventory_item_photo,
    inventory_item_transfer,
    inventory_item_transition,
    inventory_item_update,
)
from apps.inventory.views.browser_views import (
    office_inventory,
    office_inventory_item,
    office_inventory_photo,
)

urlpatterns = [
    path("office-inventory", office_inventory, name="office_inventory"),
    path(
        "office-inventory/<uuid:public_id>",
        office_inventory_item,
        name="office_inventory_item",
    ),
    path(
        "office-inventory/<uuid:public_id>/photo",
        office_inventory_photo,
        name="office_inventory_photo",
    ),
    path(
        "operations/inventory",
        inventory_admin_index,
        name="admin_inventory",
    ),
    path(
        "operations/inventory/create",
        inventory_item_create,
        name="admin_inventory_create",
    ),
    path(
        "operations/inventory/<uuid:public_id>",
        inventory_item_detail,
        name="admin_inventory_item",
    ),
    path(
        "operations/inventory/<uuid:public_id>/update",
        inventory_item_update,
        name="admin_inventory_update",
    ),
    path(
        "operations/inventory/<uuid:public_id>/transition",
        inventory_item_transition,
        name="admin_inventory_transition",
    ),
    path(
        "operations/inventory/<uuid:public_id>/transfer",
        inventory_item_transfer,
        name="admin_inventory_transfer",
    ),
    path(
        "operations/inventory/<uuid:public_id>/photo",
        inventory_item_photo,
        name="admin_inventory_photo",
    ),
]
