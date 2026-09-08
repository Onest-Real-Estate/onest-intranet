from django.urls import path

from apps.reservations import views

urlpatterns = [
    path("rooms", views.room_availability, name="room_availability"),
    path(
        "rooms/reservations/new",
        views.room_reservation_new,
        name="room_reservation_new",
    ),
    path(
        "rooms/reservations",
        views.room_reservation_create,
        name="room_reservation_create",
    ),
]
