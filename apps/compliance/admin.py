"""Category governance lives in the Django admin."""

from django.contrib import admin

from apps.compliance.models import (
    PolicyAcknowledgement,
    PolicyAcknowledgementCorrection,
    PolicyAcknowledgementWaiver,
    PolicyCategory,
    PolicyFile,
    PolicyRequirement,
    PolicyVersion,
    PolicyVersionAccess,
)


class EvidenceAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PolicyCategory)
class PolicyCategoryAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "is_active", "display_order", "is_system")
    list_filter = ("is_active", "is_system")
    search_fields = ("code", "label")
    ordering = ("display_order", "label")

    def get_readonly_fields(self, request, obj=None):
        return ("code", "is_system") if obj else ("is_system",)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (
            obj.is_system or PolicyVersion.objects.filter(category=obj).exists()
        ):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(PolicyVersion)
class PolicyVersionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "version_number",
        "status",
        "category",
        "owner_office",
        "is_mandatory",
    )
    list_filter = ("status", "is_mandatory", "category")
    search_fields = ("title", "summary")
    autocomplete_fields = ("owner_office", "owner_user", "category")
    readonly_fields = (
        "version_family",
        "content_checksum",
        "published_at",
        "published_by",
        "created_at",
        "updated_at",
    )


@admin.register(PolicyFile)
class PolicyFileAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "policy_version",
        "role",
        "processing_state",
        "is_active",
    )
    list_filter = ("role", "processing_state", "is_active")
    search_fields = ("display_name", "checksum")


@admin.register(PolicyRequirement)
class PolicyRequirementAdmin(admin.ModelAdmin):
    list_display = ("policy_version", "due_at", "is_active", "created_at")
    list_filter = ("is_active",)


@admin.register(PolicyVersionAccess)
class PolicyVersionAccessAdmin(EvidenceAdmin):
    list_display = ("user", "policy_version", "kind", "accessed_at")
    list_filter = ("kind",)
    search_fields = ("user__email", "content_checksum")
    readonly_fields = (
        "user",
        "policy_version",
        "policy_file",
        "kind",
        "content_checksum",
        "accessed_at",
    )


@admin.register(PolicyAcknowledgement)
class PolicyAcknowledgementAdmin(EvidenceAdmin):
    list_display = (
        "user",
        "policy_version",
        "disclosure_version",
        "acknowledged_at",
    )
    search_fields = ("user__email", "content_checksum")
    readonly_fields = (
        "user",
        "policy_version",
        "content_checksum",
        "disclosure_version",
        "disclosure_text",
        "acknowledged_at",
        "request_meta",
    )


@admin.register(PolicyAcknowledgementWaiver)
class PolicyAcknowledgementWaiverAdmin(EvidenceAdmin):
    list_display = ("user", "policy_version", "waived_by", "waived_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__email", "reason")
    readonly_fields = (
        "user",
        "policy_version",
        "reason",
        "waived_by",
        "waived_at",
        "is_active",
    )


@admin.register(PolicyAcknowledgementCorrection)
class PolicyAcknowledgementCorrectionAdmin(EvidenceAdmin):
    list_display = ("user", "policy_version", "kind", "corrected_by", "created_at")
    list_filter = ("kind",)
    search_fields = ("user__email", "reason")
    readonly_fields = (
        "user",
        "policy_version",
        "kind",
        "reason",
        "corrected_by",
        "created_at",
    )
