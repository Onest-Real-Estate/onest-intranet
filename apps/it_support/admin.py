from django.contrib import admin

from apps.it_support.models import SupportTicket, TicketAttachment, TicketReply


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("reference", "subject", "category", "status", "priority", "office")
    list_filter = ("status", "priority", "category")
    search_fields = ("reference", "subject")
    # Lifecycle belongs to the service layer; the admin is a read surface for
    # support, not a second way to move a ticket without an audit trail.
    readonly_fields = ("public_id", "reference", "resolved_at", "closed_at")


@admin.register(TicketReply)
class TicketReplyAdmin(admin.ModelAdmin):
    list_display = ("ticket", "author", "internal", "is_resolution", "created_at")
    list_filter = ("internal", "is_resolution")


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ("ticket", "display_name", "internal", "byte_size", "created_at")
    list_filter = ("internal",)
