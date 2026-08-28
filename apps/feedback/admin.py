from django.contrib import admin

from apps.feedback.models import FeedbackNote, FeedbackScreenshot, FeedbackTicket


class FeedbackNoteInline(admin.TabularInline):
    model = FeedbackNote
    extra = 0
    fields = ("author", "internal", "body", "created_at")
    readonly_fields = ("created_at",)


@admin.register(FeedbackTicket)
class FeedbackTicketAdmin(admin.ModelAdmin):
    """Read-oriented on purpose.

    Status is not editable here. The lifecycle is enforced in the service layer
    with an actor, an expected-state check, and an audit event; an admin
    dropdown writing the column directly would route around all three.
    """

    list_display = (
        "reference",
        "summary",
        "category",
        "status",
        "priority",
        "office",
        "assignee",
        "created_at",
    )
    list_filter = ("status", "category", "urgency", "priority")
    search_fields = ("reference", "summary", "submission_key")
    readonly_fields = (
        "public_id",
        "reference",
        "status",
        "submission_key",
        "page_url",
        "browser_metadata",
        "converted_task_id",
        "resolved_at",
        "closed_at",
        "created_at",
        "updated_at",
    )
    inlines = (FeedbackNoteInline,)


@admin.register(FeedbackScreenshot)
class FeedbackScreenshotAdmin(admin.ModelAdmin):
    list_display = ("display_name", "ticket", "media_type", "byte_size", "created_at")
    readonly_fields = ("public_id", "checksum", "created_at")
