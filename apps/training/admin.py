"""Django admin for training library models (staff / support surfaces).

Day-to-day publishing lives in the Hub workspace; this module is for category
governance, evidence inspection, and certificate verification fields.
"""

from __future__ import annotations

from django.contrib import admin

from apps.training.models import (
    TrainingAudience,
    TrainingCategory,
    TrainingCertificate,
    TrainingContent,
    TrainingEmbed,
    TrainingLiveSession,
    TrainingMedia,
    TrainingModule,
    TrainingProgress,
    TrainingQuiz,
    TrainingQuizAttempt,
    TrainingQuizQuestion,
    TrainingSessionRegistration,
    TrainingTranscription,
)


@admin.register(TrainingCategory)
class TrainingCategoryAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "is_active", "display_order", "is_system")
    list_filter = ("is_active", "is_system")
    search_fields = ("code", "label")
    ordering = ("display_order", "label")

    def get_readonly_fields(self, request, obj=None):
        return ("code", "is_system") if obj else ("is_system",)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (
            obj.is_system or TrainingContent.objects.filter(category=obj).exists()
        ):
            return False
        return super().has_delete_permission(request, obj)


class TrainingAudienceInline(admin.TabularInline):
    model = TrainingAudience
    extra = 0
    autocomplete_fields = ("office", "user")


class TrainingEmbedInline(admin.StackedInline):
    model = TrainingEmbed
    extra = 0
    max_num = 1


class TrainingTranscriptionInline(admin.StackedInline):
    model = TrainingTranscription
    extra = 0
    max_num = 1


class TrainingModuleInline(admin.TabularInline):
    model = TrainingModule
    fk_name = "course"
    extra = 0
    autocomplete_fields = ("child",)
    ordering = ("sort_order",)


@admin.register(TrainingContent)
class TrainingContentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "content_type",
        "status",
        "owner_office",
        "is_required",
        "version_number",
        "published_at",
    )
    list_filter = ("status", "content_type", "is_required", "category")
    search_fields = ("slug", "title", "summary")
    autocomplete_fields = (
        "owner_office",
        "category",
        "created_by",
        "updated_by",
    )
    readonly_fields = (
        "version_family",
        "published_at",
        "created_at",
        "updated_at",
    )
    inlines = [
        TrainingAudienceInline,
        TrainingEmbedInline,
        TrainingTranscriptionInline,
        TrainingModuleInline,
    ]
    ordering = ("-updated_at",)


@admin.register(TrainingMedia)
class TrainingMediaAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "content",
        "role",
        "media_type",
        "processing_state",
        "is_active",
        "byte_size",
    )
    list_filter = ("role", "processing_state", "is_active", "media_type")
    search_fields = ("display_name", "checksum", "content__title", "content__slug")
    autocomplete_fields = ("content",)
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


@admin.register(TrainingProgress)
class TrainingProgressAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "content",
        "status",
        "progress_percent",
        "source",
        "started_at",
        "completed_at",
    )
    list_filter = ("status", "source")
    search_fields = ("user__email", "content__title", "content__slug")
    autocomplete_fields = ("user", "content")
    readonly_fields = ("started_at", "completed_at", "updated_at")
    ordering = ("-updated_at",)


class TrainingQuizQuestionInline(admin.TabularInline):
    model = TrainingQuizQuestion
    extra = 0
    ordering = ("sort_order",)


@admin.register(TrainingQuiz)
class TrainingQuizAdmin(admin.ModelAdmin):
    list_display = (
        "content",
        "pass_threshold_percent",
        "max_attempts",
        "feedback_policy",
    )
    search_fields = ("content__title", "content__slug")
    autocomplete_fields = ("content",)
    inlines = [TrainingQuizQuestionInline]


@admin.register(TrainingQuizAttempt)
class TrainingQuizAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "content",
        "attempt_number",
        "score_percent",
        "passed",
        "submitted_at",
    )
    list_filter = ("passed",)
    search_fields = ("user__email", "content__title")
    autocomplete_fields = ("user", "content")
    readonly_fields = ("submitted_at",)


@admin.register(TrainingLiveSession)
class TrainingLiveSessionAdmin(admin.ModelAdmin):
    list_display = (
        "content",
        "starts_at",
        "timezone",
        "duration_minutes",
        "capacity",
    )
    search_fields = ("content__title", "content__slug", "meeting_url")
    autocomplete_fields = ("content",)


@admin.register(TrainingSessionRegistration)
class TrainingSessionRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "content",
        "status",
        "registered_at",
        "attended_at",
        "cancelled_at",
    )
    list_filter = ("status",)
    search_fields = ("user__email", "content__title")
    autocomplete_fields = ("user", "content")
    readonly_fields = ("registered_at", "attended_at", "cancelled_at")


@admin.register(TrainingCertificate)
class TrainingCertificateAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "user",
        "content",
        "status",
        "signature_algorithm",
        "approved_by",
        "approved_at",
    )
    list_filter = ("status", "signature_algorithm")
    search_fields = (
        "public_id",
        "signature",
        "user__email",
        "content__title",
        "content__slug",
    )
    autocomplete_fields = ("user", "content", "approved_by")
    readonly_fields = (
        "public_id",
        "signature",
        "signature_algorithm",
        "file",
        "approved_by",
        "approved_at",
        "created_at",
        "updated_at",
        "verify_url_display",
    )
    ordering = ("-approved_at", "-created_at")

    @admin.display(description="Verify URL")
    def verify_url_display(self, obj: TrainingCertificate) -> str:
        if not obj.public_id:
            return "—"
        from apps.training.certificate_crypto import verify_url

        return verify_url(obj.public_id)

    def has_add_permission(self, request):
        # Issuance runs through the Hub workspace (HMAC + PDF + QR).
        return False
