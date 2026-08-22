from django.urls import path

from .views import (
    announcement_attachment,
    announcement_detail,
    announcements,
    recipient_search,
)

urlpatterns = [
    path("announcements", announcements, name="announcements"),
    path(
        "announcements/recipients",
        recipient_search,
        name="announcement_recipient_search",
    ),
    path(
        "announcements/<int:announcement_id>",
        announcement_detail,
        name="announcement_detail",
    ),
    path(
        "announcements/<int:announcement_id>/attachment",
        announcement_attachment,
        name="announcement_attachment",
    ),
]
