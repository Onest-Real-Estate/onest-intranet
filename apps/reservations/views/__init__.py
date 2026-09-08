from apps.reservations.views.admin_views import (
    space_administration,
    space_administration_activation,
    space_administration_block_create,
    space_administration_block_delete,
    space_administration_block_update,
    space_administration_booking_cancel,
    space_administration_booking_move,
    space_administration_create,
    space_administration_retire,
    space_administration_schedule,
    space_administration_update,
    space_administration_workspace,
)
from apps.reservations.views.agents_views import (
    room_availability,
    room_reservation_create,
    room_reservation_new,
)

__all__ = [
    "room_availability",
    "room_reservation_create",
    "room_reservation_new",
    "space_administration",
    "space_administration_activation",
    "space_administration_block_create",
    "space_administration_block_delete",
    "space_administration_block_update",
    "space_administration_booking_cancel",
    "space_administration_booking_move",
    "space_administration_create",
    "space_administration_retire",
    "space_administration_schedule",
    "space_administration_update",
    "space_administration_workspace",
]
