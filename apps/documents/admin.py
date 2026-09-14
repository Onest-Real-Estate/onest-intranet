"""Category and library seed surfaces for staff until Hub administration ships."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError

from apps.documents.media import inspect_document_upload
from apps.documents.media_service import upload_document
from apps.documents.models import (
    DocumentAudience,
    DocumentCategory,
    DocumentFamily,
    DocumentFile,
    DocumentVersion,
)
from apps.documents.services import publish_version


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "is_active", "display_order", "is_system")
    list_filter = ("is_active", "is_system")
    search_fields = ("code", "label")
    ordering = ("display_order", "label")

    def get_readonly_fields(self, request, obj=None):
        return ("code", "is_system") if obj else ("is_system",)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (
            obj.is_system or DocumentVersion.objects.filter(category=obj).exists()
        ):
            return False
        return super().has_delete_permission(request, obj)


class DocumentAudienceInline(admin.TabularInline):
    model = DocumentAudience
    extra = 0
    autocomplete_fields = ("office", "user")


class DocumentFileInline(admin.TabularInline):
    model = DocumentFile
    extra = 0
    readonly_fields = (
        "display_name",
        "media_type",
        "byte_size",
        "checksum",
        "processing_state",
        "created_at",
    )


@admin.register(DocumentFamily)
class DocumentFamilyAdmin(admin.ModelAdmin):
    list_display = ("key", "owner_office", "updated_at")
    search_fields = ("key",)
    autocomplete_fields = ("owner_office",)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "version_number",
        "status",
        "category",
        "family",
        "effective_at",
    )
    list_filter = ("status", "category")
    search_fields = ("name", "description", "family__key")
    autocomplete_fields = ("family", "category", "owner_user")
    readonly_fields = (
        "published_at",
        "published_by",
        "created_at",
        "updated_at",
    )
    inlines = [DocumentAudienceInline, DocumentFileInline]
    actions = ["publish_selected"]

    @admin.action(description="Publish selected draft versions")
    def publish_selected(self, request, queryset):
        published = 0
        for version in queryset:
            try:
                publish_version(request.user, version)
            except (ValidationError, PermissionDenied) as exc:
                self.message_user(request, f"{version}: {exc}", level=messages.ERROR)
            else:
                published += 1
        if published:
            self.message_user(request, f"Published {published} version(s).")


@admin.register(DocumentFile)
class DocumentFileAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "document_version",
        "processing_state",
        "byte_size",
        "is_active",
    )
    list_filter = ("processing_state", "is_active")
    search_fields = ("display_name", "document_version__name")
    autocomplete_fields = ("document_version",)
    readonly_fields = (
        "display_name",
        "media_type",
        "byte_size",
        "checksum",
        "processing_state",
        "processing_note",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get("file")
        if uploaded and hasattr(uploaded, "read"):
            if change and obj.pk:
                inspect_document_upload(uploaded)
                super().save_model(request, obj, form, change)
                return
            row = upload_document(request.user, obj.document_version, uploaded)
            obj.pk = row.pk
            return
        super().save_model(request, obj, form, change)
