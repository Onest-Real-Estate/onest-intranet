from django.contrib import admin

from apps.operational_tasks.models import (
    OperationalTask,
    TaskAttachment,
    TaskComment,
)


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0
    fields = ("author", "internal", "body", "created_at")
    readonly_fields = ("created_at",)


@admin.register(OperationalTask)
class OperationalTaskAdmin(admin.ModelAdmin):
    """Read-oriented on purpose.

    Status is not editable here. The lifecycle is enforced in the service
    layer with an actor, an expected-state check, and an audit event; an admin
    dropdown that writes the column directly would route around all three.
    """

    list_display = (
        "reference",
        "title",
        "category",
        "status",
        "priority",
        "office",
        "assignee",
        "due_at",
    )
    list_filter = ("status", "category", "priority", "source", "office")
    search_fields = ("reference", "title", "source_reference")
    readonly_fields = (
        "public_id",
        "reference",
        "status",
        "started_at",
        "resolved_at",
        "closed_at",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("office", "assignee", "reporter")
    inlines = (TaskCommentInline,)


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(admin.ModelAdmin):
    list_display = ("display_name", "task", "internal", "byte_size", "created_at")
    list_filter = ("internal",)
    readonly_fields = ("public_id", "created_at")
