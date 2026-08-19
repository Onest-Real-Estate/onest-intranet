"""Admin for DomainEvent and EventDelivery with operator replay action."""

from django.contrib import admin, messages
from django.http import HttpRequest
from django.utils.html import format_html

from .models import DomainEvent, EventDelivery


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

    @admin.action(description="Replay selected events (reset and re-dispatch)")
    def replay_selected(self, request: HttpRequest, queryset):
        if not request.user.has_perm("audit.can_replay_events"):
            self.message_user(
                request,
                "You do not have permission to replay events.",
                level=messages.ERROR,
            )
            return

        from .tasks import replay_event

        count = 0
        for event in queryset:
            replay_event.delay(str(event.pk))
            count += 1

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
        if not request.user.has_perm("audit.can_replay_events"):
            self.message_user(
                request,
                "You do not have permission to replay events.",
                level=messages.ERROR,
            )
            return

        from .tasks import replay_event

        count = 0
        for delivery in queryset.select_related("event"):
            if delivery.event is not None:
                replay_event.delay(str(delivery.event.pk), delivery.consumer)
                count += 1

        self.message_user(
            request, f"Queued replay for {count} delivery row(s).", messages.SUCCESS
        )


class AuditPermissions(admin.ModelAdmin):
    """Placeholder to surface the can_replay_events permission in the admin."""

    pass
