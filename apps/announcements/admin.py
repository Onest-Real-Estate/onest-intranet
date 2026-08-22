"""Category governance lives in the Django admin.

The stable ``code`` is read-only after creation and seeded categories cannot
be deleted from here — the model and :mod:`apps.announcements.services` refuse
regardless of which door a request arrives through, and this file makes the
refusal visible rather than a surprise at save time.
"""

from django.contrib import admin

from apps.announcements.models import Announcement, AnnouncementCategory


@admin.register(AnnouncementCategory)
class AnnouncementCategoryAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "is_active", "display_order", "is_system")
    list_filter = ("is_active", "is_system")
    search_fields = ("code", "label")
    ordering = ("display_order", "label")

    def get_readonly_fields(self, request, obj=None):
        return ("code", "is_system") if obj else ("is_system",)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (
            obj.is_system or Announcement.objects.filter(category=obj).exists()
        ):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "owner_office", "category", "priority", "status")
    list_filter = ("status", "priority", "category")
    search_fields = ("slug", "title")
    autocomplete_fields = ("owner_office",)
