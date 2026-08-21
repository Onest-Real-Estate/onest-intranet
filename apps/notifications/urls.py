from django.urls import path

from . import views

urlpatterns = [
    path("notifications", views.notification_center, name="notifications"),
    path(
        "notifications/preferences",
        views.notification_preferences,
        name="notification_preferences",
    ),
    path(
        "notifications/preferences/submit",
        views.notification_preferences_submit,
        name="notification_preferences_submit",
    ),
    path(
        "notifications/summary",
        views.notification_summary,
        name="notification_summary",
    ),
    path(
        "notifications/read-all",
        views.notification_read_all,
        name="notification_read_all",
    ),
    path(
        "notifications/<uuid:public_id>/state",
        views.notification_state,
        name="notification_state",
    ),
]
