"""Admin for DomainEvent, EventDelivery, and AuditEvent."""

from typing import cast

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.utils.html import format_html

from apps.audit.query import query_audit_events
from apps.audit.replay import request_replay_event
from apps.user.models import User
from apps.web.authorization import has_admin_permission

from .models import AuditEvent, DomainEvent, EventDelivery


class EventDeliveryInline(admin.TabularInline):
    model = EventDelivery
    extra = 0
    readonly_fields = [
        "id",
        "consumer",
        "status",
        "attempts",
        "last_error",
        "created_at",
        "delivered_at",
        "next_attempt_at",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DomainEvent)
class DomainEventAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "name",
        "version",
        "status",
        "actor_id",
        "subject",
        "occurred_at",
        "dispatched_at",
    ]
    list_filter = ["status", "name", "version"]
    search_fields = ["id", "name", "actor_id", "subject"]
    readonly_fields = [
        "id",
        "name",
        "version",
        "actor_id",
        "subject",
        "organization_id",
        "correlation_id",
        "causation_id",
        "payload",
        "occurred_at",
        "created_at",
        "status",
        "dispatched_at",
    ]
    ordering = ["-occurred_at"]
    inlines = [EventDeliveryInline]
    actions = ["replay_selected"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return has_admin_permission(request.user, "audit.can_replay_events")

    def has_view_permission(self, request, obj=None):
        return has_admin_permission(request.user, "audit.can_replay_events")

    @admin.action(description="Replay selected events (reset and re-dispatch)")
    def replay_selected(self, request: HttpRequest, queryset):
        count = 0
        try:
            for event in queryset:
                request_replay_event(
                    actor=cast(User, request.user),
                    event_id=str(event.pk),
                    request_id=getattr(request, "audit_request_id", ""),
                )
                count += 1
        except PermissionDenied as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return

        self.message_user(
            request, f"Queued replay for {count} event(s).", messages.SUCCESS
        )


@admin.register(EventDelivery)
class EventDeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "event_link",
        "consumer",
        "status",
        "attempts",
        "created_at",
        "delivered_at",
        "next_attempt_at",
    ]
    list_filter = ["status", "consumer"]
    search_fields = ["id", "consumer", "event__name"]
    readonly_fields = [
        "id",
        "event",
        "consumer",
        "status",
        "attempts",
        "last_error",
        "created_at",
        "delivered_at",
        "next_attempt_at",
    ]
    ordering = ["-created_at"]
    actions = ["replay_selected_deliveries"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return has_admin_permission(request.user, "audit.can_replay_events")

    def has_view_permission(self, request, obj=None):
        return has_admin_permission(request.user, "audit.can_replay_events")

    @admin.display(description="Event")
    def event_link(self, obj: EventDelivery):
        event = obj.event
        if event is not None:
            return format_html(
                '<a href="/admin/audit/domainevent/{}/change/">{}</a>',
                event.pk,
                str(event.pk)[:8],
            )
        return "—"

    @admin.action(description="Replay selected deliveries")
    def replay_selected_deliveries(self, request: HttpRequest, queryset):
        count = 0
        try:
            for delivery in queryset.select_related("event"):
                if delivery.event is not None:
                    request_replay_event(
                        actor=cast(User, request.user),
                        event_id=str(delivery.event.pk),
                        consumer_id=delivery.consumer,
                        request_id=getattr(request, "audit_request_id", ""),
                    )
                    count += 1
        except PermissionDenied as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return

        self.message_user(
            request, f"Queued replay for {count} delivery row(s).", messages.SUCCESS
        )


class AuditPermissions(admin.ModelAdmin):
    """Placeholder to surface the can_replay_events permission in the admin."""

    pass


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = [
        "occurred_at",
        "action",
        "outcome",
        "actor_label",
        "target_label",
        "source",
        "request_id",
    ]
    list_filter = ["outcome", "source", "actor_type", "action"]
    search_fields = [
        "action",
        "actor_id",
        "actor_label",
        "target_id",
        "target_label",
        "request_id",
    ]
    readonly_fields = [
        "id",
        "payload_version",
        "action",
        "actor_type",
        "actor_id",
        "actor_label",
        "actor_snapshot",
        "impersonated_by",
        "target_type",
        "target_id",
        "target_label",
        "target_snapshot",
        "organization_id",
        "office_id",
        "region_id",
        "source",
        "channel",
        "request_id",
        "correlation_id",
        "remote_addr",
        "user_agent",
        "outcome",
        "reason",
        "before",
        "after",
        "changes",
        "metadata",
        "occurred_at",
        "recorded_at",
    ]
    ordering = ["-occurred_at", "-recorded_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return has_admin_permission(request.user, "audit.can_view_audit_events")

    def has_view_permission(self, request, obj=None):
        return has_admin_permission(request.user, "audit.can_view_audit_events")

    def get_queryset(self, request):
        if getattr(request.user, "is_superuser", False):
            return super().get_queryset(request)
        return query_audit_events(request.user, limit=1000)
