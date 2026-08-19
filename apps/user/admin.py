from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from .models import Office, OfficeContactAssignment, User


class UserCreationForm(forms.ModelForm):
    """Creation form for the email-based user (no username field)."""

    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(
        label=_("Password confirmation"), widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ("email", "display_name")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("Passwords don't match."))
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label=_("Password"),
        help_text=_(
            "Raw passwords are not stored, so there is no way to see this "
            "user's password, but you can change the password using "
            '<a href="../password/">this form</a>.'
        ),
    )

    class Meta:
        model = User
        fields = "__all__"


class OfficeChildInline(admin.TabularInline):
    model = Office
    fk_name = "parent"
    extra = 0
    fields = (
        "name",
        "stable_key",
        "slug",
        "kind",
        "is_assignable",
        "is_active",
        "sort_order",
    )
    show_change_link = True


class OfficeContactAssignmentInline(admin.TabularInline):
    model = OfficeContactAssignment
    extra = 0
    autocomplete_fields = ["user"]
    fields = (
        "assignment_type",
        "user",
        "is_primary",
        "starts_at",
        "ends_at",
    )


class OfficeAdminForm(forms.ModelForm):
    class Meta:
        model = Office
        fields = "__all__"


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    form = OfficeAdminForm
    list_display = (
        "name",
        "stable_key",
        "kind",
        "region",
        "parent",
        "is_assignable",
        "is_active",
        "sort_order",
    )
    list_filter = ("kind", "region", "is_assignable", "is_active")
    search_fields = ("name", "slug", "stable_key", "city", "public_email")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [OfficeChildInline, OfficeContactAssignmentInline]
    ordering = ("sort_order", "name")
    autocomplete_fields = ["parent", "region"]
    fieldsets = (
        (
            _("Identity"),
            {
                "fields": (
                    "name",
                    "stable_key",
                    "slug",
                    "kind",
                    "is_active",
                    "is_assignable",
                    "sort_order",
                )
            },
        ),
        (_("Hierarchy"), {"fields": ("parent", "region")}),
        (
            _("Address & contact"),
            {
                "fields": (
                    "street_address",
                    "city",
                    "state",
                    "zip_code",
                    "main_phone",
                    "public_email",
                    "internal_email",
                    "office_hours",
                )
            },
        ),
        (
            _("Operations"),
            {
                "fields": (
                    "parking_instructions",
                    "access_instructions",
                    "access_instructions_internal",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly.extend(["stable_key", "region"])
        return readonly


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    ordering = ["email"]
    list_display = [
        "email",
        "display_name",
        "office",
        "is_staff",
        "is_superuser",
        "is_active",
    ]
    list_filter = ["is_staff", "is_superuser", "is_active", "groups", "office"]
    search_fields = [
        "email",
        "display_name",
        "first_name",
        "last_name",
        "mls_number",
        "nrds_number",
    ]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {
                "fields": (
                    "display_name",
                    "first_name",
                    "last_name",
                    "phone_number",
                )
            },
        ),
        (
            _("Address"),
            {"fields": ("street_address", "city", "state", "zip_code")},
        ),
        (
            _("Profile & photo"),
            {"fields": ("headshot",)},
        ),
        (
            _("Office & licenses"),
            {
                "fields": (
                    "office",
                    "mls_number",
                    "nrds_number",
                    "profile_completed",
                    "profile_completed_at",
                    "onboarding_version",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "password1", "password2"),
            },
        ),
    )
    autocomplete_fields = ["office"]
    readonly_fields = ["profile_completed_at"]
    actions = ["reset_onboarding"]

    @admin.action(description="Reset onboarding for selected users")
    def reset_onboarding(self, request: HttpRequest, queryset):
        count = queryset.update(
            profile_completed=False,
            profile_completed_at=None,
        )
        # Increment version so the reset is distinguishable from the original.
        for user in queryset:
            user.onboarding_version = (user.onboarding_version or 0) + 1
            user.save(update_fields=["onboarding_version"])
        self.message_user(
            request,
            f"Reset onboarding for {count} user(s). "
            "They will be redirected to /onboarding on next login.",
            messages.SUCCESS,
        )
