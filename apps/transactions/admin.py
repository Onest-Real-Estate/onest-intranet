from django.contrib import admin

from apps.transactions.models import Transaction, TransactionAssignment


class TransactionAssignmentInline(admin.TabularInline):
    model = TransactionAssignment
    extra = 0
    fields = ("user", "role", "assigned_by", "assigned_at", "ended_at")
    readonly_fields = ("assigned_at", "public_id")
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
    inlines = (TransactionAssignmentInline,)


@admin.register(TransactionAssignment)
class TransactionAssignmentAdmin(admin.ModelAdmin):
    list_display = ("transaction", "user", "role", "assigned_at", "ended_at")
    list_filter = ("role",)
    readonly_fields = ("public_id", "assigned_at")
    autocomplete_fields = ("transaction", "user", "assigned_by")
