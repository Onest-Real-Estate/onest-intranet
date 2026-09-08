"""Operator visibility over the email delivery ledger.

Read-only on purpose. A delivery row is a record of what the pipeline did, and
an operator editing one by hand would either lose a message or send it twice.
Recovery is a queue operation — ``sweep_notification_emails`` — not an edit.
"""

from __future__ import annotations

from django.contrib import admin

from apps.notifications.models import NotificationEmail, NotificationPreference


@admin.register(NotificationEmail)
class NotificationEmailAdmin(admin.ModelAdmin):
    list_display = (
        "delivery_key",
        "channel",
        "status",
        "attempts",
        "queued_at",
        "last_attempt_at",
        "next_attempt_at",
        "suppression_reason",
    )
    list_filter = ("status", "channel", "suppression_reason")
    search_fields = ("delivery_key", "to_email")
    date_hierarchy = "queued_at"
    ordering = ("-queued_at",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """Visible for support, never editable here.

    Preferences are the reader's own choice and the settings page is the only
    thing that writes them, so support can see what somebody chose without
    being able to choose it for them.
    """

    list_display = ("user", "policy_version", "updated_at")
    list_filter = ("policy_version",)
    search_fields = ("user__email",)
    ordering = ("-updated_at",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
