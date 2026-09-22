from django.contrib import admin

from apps.transactions.models import (
    Transaction,
    TransactionAssignment,
    TransactionDocument,
    TransactionDocumentReviewComment,
    TransactionDocumentVersion,
    TransactionKeyDate,
    TransactionNote,
    TransactionParty,
    TransactionPropertySnapshot,
)


class TransactionAssignmentInline(admin.TabularInline):
    model = TransactionAssignment
    extra = 0
    fields = ("user", "role", "assigned_by", "assigned_at", "ended_at")
    readonly_fields = ("assigned_at", "public_id")
    show_change_link = True


class TransactionPartyInline(admin.TabularInline):
    model = TransactionParty
    extra = 0
    fields = ("role", "display_name", "kind", "is_primary", "ended_at")
    readonly_fields = ("public_id",)
    show_change_link = True


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Read-oriented on purpose.

    Status is not editable here. The lifecycle is enforced in the service
    layer with an actor, an expected-state check, and an audit event.
    """

    list_display = (
        "reference",
        "transaction_type",
        "status",
        "office",
        "primary_agent",
        "coordinator",
        "closing_date",
    )
    list_filter = ("status", "transaction_type", "representation_type", "office")
    search_fields = ("reference", "mls_number", "public_id")
    readonly_fields = (
        "public_id",
        "reference",
        "status",
        "held_from_status",
        "preparing_at",
        "under_contract_at",
        "pending_at",
        "compliance_review_at",
        "compliance_approved_at",
        "ready_to_close_at",
        "closed_at",
        "archived_at",
        "on_hold_at",
        "cancelled_at",
        "withdrawn_at",
        "terminated_at",
        "archived_by",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("office", "primary_agent", "coordinator", "created_by")
    inlines = (TransactionAssignmentInline, TransactionPartyInline)


@admin.register(TransactionAssignment)
class TransactionAssignmentAdmin(admin.ModelAdmin):
    list_display = ("transaction", "user", "role", "assigned_at", "ended_at")
    list_filter = ("role",)
    readonly_fields = ("public_id", "assigned_at")
    autocomplete_fields = ("transaction", "user", "assigned_by")


@admin.register(TransactionParty)
class TransactionPartyAdmin(admin.ModelAdmin):
    list_display = ("transaction", "role", "display_name", "is_primary", "ended_at")
    list_filter = ("role", "kind")
    readonly_fields = ("public_id", "snapshot", "created_at", "updated_at")
    autocomplete_fields = ("transaction", "created_by")


@admin.register(TransactionKeyDate)
class TransactionKeyDateAdmin(admin.ModelAdmin):
    list_display = ("transaction", "date_type", "occurs_at", "ended_at")
    list_filter = ("date_type",)
    readonly_fields = ("public_id", "created_at", "updated_at")
    raw_id_fields = ("transaction", "created_by", "superseded_by")


@admin.register(TransactionNote)
class TransactionNoteAdmin(admin.ModelAdmin):
    list_display = ("transaction", "visibility", "author", "created_at", "ended_at")
    list_filter = ("visibility",)
    readonly_fields = ("public_id", "created_at", "updated_at")
    raw_id_fields = ("transaction", "author")


@admin.register(TransactionPropertySnapshot)
class TransactionPropertySnapshotAdmin(admin.ModelAdmin):
    list_display = ("transaction", "mls_number", "recorded_at")
    readonly_fields = ("public_id", "snapshot", "change_summary", "recorded_at")
    raw_id_fields = ("transaction", "recorded_by")


@admin.register(TransactionDocument)
class TransactionDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "transaction",
        "category",
        "requirement",
        "ended_at",
    )
    list_filter = ("category", "requirement", "retention_policy")
    readonly_fields = ("public_id", "created_at", "updated_at")
    raw_id_fields = ("transaction", "current_version", "created_by")
    search_fields = ("title", "transaction__reference")


@admin.register(TransactionDocumentVersion)
class TransactionDocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "document",
        "version_number",
        "processing_state",
        "signature_status",
        "compliance_status",
        "locked_at",
    )
    list_filter = ("processing_state", "signature_status", "compliance_status")
    readonly_fields = (
        "public_id",
        "checksum",
        "byte_size",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("document", "uploaded_by", "locked_by")


@admin.register(TransactionDocumentReviewComment)
class TransactionDocumentReviewCommentAdmin(admin.ModelAdmin):
    list_display = (
        "version",
        "visibility",
        "resolution_state",
        "author",
        "created_at",
        "ended_at",
    )
    list_filter = ("visibility", "resolution_state")
    readonly_fields = ("public_id", "created_at", "updated_at")
    raw_id_fields = ("version", "author", "resolved_by")
