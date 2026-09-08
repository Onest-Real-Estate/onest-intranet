from django.contrib import admin

from apps.onboarding_tools.models import (
    AgentToolStatus,
    OnboardingTool,
    OnboardingToolOfficeAudience,
)


class OfficeAudienceInline(admin.TabularInline):
    model = OnboardingToolOfficeAudience
    extra = 0
    autocomplete_fields = ("office",)


@admin.register(OnboardingTool)
class OnboardingToolAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "group",
        "provisioning",
        "company_wide",
        "is_required",
        "is_active",
        "sort_order",
    )
    list_filter = ("group", "provisioning", "company_wide", "is_required", "is_active")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (OfficeAudienceInline,)


@admin.register(AgentToolStatus)
class AgentToolStatusAdmin(admin.ModelAdmin):
    list_display = ("agent", "tool", "state", "updated_by", "updated_at")
    list_filter = ("state", "tool__group")
    search_fields = ("agent__email", "tool__name")
    # Progress belongs to the service layer, which authorizes and audits.
    readonly_fields = ("ready_at",)
