from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.translation import gettext_lazy as _

from .models import Office, User


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
    fields = ("name", "slug", "kind", "is_assignable", "is_active", "sort_order")
    show_change_link = True


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "kind",
        "parent",
        "is_assignable",
        "is_active",
        "sort_order",
    )
    list_filter = ("kind", "is_assignable", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [OfficeChildInline]
    ordering = ("sort_order", "name")


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
            _("Office & licenses"),
            {"fields": ("office", "mls_number", "nrds_number", "profile_completed")},
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
