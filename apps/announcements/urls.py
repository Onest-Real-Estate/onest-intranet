from django.urls import path

from .administration_views import (
    announcement_create,
    announcement_edit,
    announcement_lifecycle,
    announcement_new,
    announcement_pin,
    announcement_update,
)
from .views import (
    announcement_detail,
    announcement_media,
    announcement_media_manager,
    announcement_media_remove,
    announcement_media_reorder,
    announcement_media_replace,
    announcement_media_upload,
    announcement_media_variant,
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
    # Media reads. Keyed by the media row, never by a storage key: the key is
    # random, private, and never leaves the server.
    path(
        "announcements/media/<int:media_id>",
        announcement_media,
        name="announcement_media",
    ),
    path(
        "announcements/media/<int:media_id>/<slug:variant>",
        announcement_media_variant,
        name="announcement_media_variant",
    ),
    # Workspace. Every one of these loads through the actor's scoped queryset,
    # so an out-of-scope id is a 404 rather than a 403.
    path(
        "operations/announcements/new",
        announcement_new,
        name="announcement_new",
    ),
    path(
        "operations/announcements/create",
        announcement_create,
        name="announcement_create",
    ),
    path(
        "operations/announcements/<int:announcement_id>/edit",
        announcement_edit,
        name="announcement_edit",
    ),
    path(
        "operations/announcements/<int:announcement_id>/save",
        announcement_update,
        name="announcement_update",
    ),
    path(
        "operations/announcements/<int:announcement_id>/lifecycle",
        announcement_lifecycle,
        name="announcement_lifecycle",
    ),
    path(
        "operations/announcements/<int:announcement_id>/pin",
        announcement_pin,
        name="announcement_pin",
    ),
    # Media management.
    path(
        "operations/announcements/<int:announcement_id>/media",
        announcement_media_manager,
        name="announcement_media_manager",
    ),
    path(
        "operations/announcements/<int:announcement_id>/media/upload",
        announcement_media_upload,
        name="announcement_media_upload",
    ),
    path(
        "operations/announcements/<int:announcement_id>/media/reorder",
        announcement_media_reorder,
        name="announcement_media_reorder",
    ),
    path(
        "operations/announcements/media/<int:media_id>/replace",
        announcement_media_replace,
        name="announcement_media_replace",
    ),
    path(
        "operations/announcements/media/<int:media_id>/remove",
        announcement_media_remove,
        name="announcement_media_remove",
    ),
]
