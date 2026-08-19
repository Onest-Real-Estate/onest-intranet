from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.audit.service import actor_from_user, log_model_change
from apps.web.authorization import (
    assert_admin_bulk_scope,
    has_admin_permission,
    scope_queryset_for_offices,
    scope_queryset_for_user_office,
)

from .models import (
    Office,
    OfficeContactAssignment,
    User,
    UserRoleAssignment,
    UserRoleAssignmentMigrationConflict,
)
from .services.role_assignments import (
    create_role_assignment,
    revoke_role_assignment,
    update_role_assignment,
    would_remove_last_management_role,
)


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


class UserRoleAssignmentAdminForm(forms.ModelForm):
    class Meta:
        model = UserRoleAssignment
        fields = "__all__"


class UserRoleAssignmentInline(admin.TabularInline):
    model = UserRoleAssignment
    fk_name = "user"
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "role",
        "scope_type",
        "scope_office",
        "status",
        "starts_at",
        "ends_at",
        "business_reason",
        "assigned_by",
        "revoked_by",
        "revoked_at",
    )
    readonly_fields = ("assigned_by", "revoked_by", "revoked_at")


@admin.register(UserRoleAssignment)
class UserRoleAssignmentAdmin(admin.ModelAdmin):
    form = UserRoleAssignmentAdminForm
    list_display = (
        "user",
        "role",
        "scope_type",
        "scope_office",
        "status",
        "starts_at",
        "ends_at",
        "assigned_by",
        "revoked_at",
    )
    list_filter = ("role", "scope_type", "status")
    search_fields = ("user__email", "business_reason")
    autocomplete_fields = ("user", "scope_office", "assigned_by", "revoked_by")
    readonly_fields = (
        "assigned_by",
        "revoked_by",
        "revoked_at",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            _("Assignment"),
            {
                "fields": (
                    "user",
                    "role",
                    "scope_type",
                    "scope_office",
                    "status",
                    "starts_at",
                    "ends_at",
                    "business_reason",
                )
            },
        ),
        (
            _("Lifecycle"),
            {
                "fields": (
                    "assigned_by",
                    "revoked_by",
                    "revoked_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly.extend(
                ["user", "role", "scope_type", "scope_office", "assigned_by"]
            )
        return readonly

    def has_module_permission(self, request):
        return has_admin_permission(
            request.user,
            "user.view_userroleassignment",
        )

    def has_view_permission(self, request, obj=None):
        return has_admin_permission(
            request.user,
            "user.view_userroleassignment",
        )

    def has_add_permission(self, request):
        return has_admin_permission(request.user, "user.add_userroleassignment")

    def has_change_permission(self, request, obj=None):
        return has_admin_permission(request.user, "user.change_userroleassignment")

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .select_related(
                "scope_office", "scope_office__region", "user", "user__office"
            )
        )
        return scope_queryset_for_user_office(
            request.user,
            queryset,
            field_name="scope_office",
        )

    def save_model(self, request, obj, form, change):
        try:
            if not change:
                created = create_role_assignment(
                    actor=request.user,
                    target_user=obj.user,
                    role=obj.role,
                    scope_type=obj.scope_type,
                    scope_office=obj.scope_office,
                    starts_at=obj.starts_at,
                    ends_at=obj.ends_at,
                    business_reason=obj.business_reason,
                )
                obj.pk = created.pk
                obj.status = created.status
                obj.assigned_by = created.assigned_by
                obj.revoked_by = created.revoked_by
                obj.revoked_at = created.revoked_at
                return

            previous = UserRoleAssignment.objects.get(pk=obj.pk)
            if (
                obj.status == UserRoleAssignment.Status.REVOKED
                and previous.status != UserRoleAssignment.Status.REVOKED
            ):
                if would_remove_last_management_role(request.user, assignment=previous):
                    messages.warning(
                        request,
                        _(
                            "Revoking this assignment removes your last "
                            "management role."
                        ),
                    )
                updated = revoke_role_assignment(
                    actor=request.user,
                    assignment=previous,
                    business_reason=obj.business_reason,
                )
            else:
                updated = update_role_assignment(
                    actor=request.user,
                    assignment=previous,
                    starts_at=obj.starts_at,
                    ends_at=obj.ends_at,
                    business_reason=obj.business_reason,
                )
            obj.status = updated.status
            obj.revoked_by = updated.revoked_by
            obj.revoked_at = updated.revoked_at
            obj.assigned_by = updated.assigned_by
        except (ValidationError, PermissionDenied) as exc:
            if isinstance(exc, ValidationError):
                raise forms.ValidationError(exc) from exc
            raise forms.ValidationError(str(exc)) from exc


@admin.register(UserRoleAssignmentMigrationConflict)
class UserRoleAssignmentMigrationConflictAdmin(admin.ModelAdmin):
    list_display = ("user", "legacy_role", "detail", "created_at")
    list_filter = ("legacy_role",)
    search_fields = ("user__email", "legacy_role", "detail")
    autocomplete_fields = ("user",)
    readonly_fields = ("user", "legacy_role", "detail", "created_at")

    def has_module_permission(self, request):
        return has_admin_permission(
            request.user,
            "user.view_userroleassignmentmigrationconflict",
        )

    def has_view_permission(self, request, obj=None):
        return has_admin_permission(
            request.user,
            "user.view_userroleassignmentmigrationconflict",
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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

    def has_module_permission(self, request):
        return has_admin_permission(request.user, "user.view_office")

    def has_view_permission(self, request, obj=None):
        return has_admin_permission(request.user, "user.view_office")

    def has_add_permission(self, request):
        return has_admin_permission(request.user, "user.add_office")

    def has_change_permission(self, request, obj=None):
        return has_admin_permission(request.user, "user.change_office")

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("region", "parent")
        return scope_queryset_for_offices(request.user, queryset)

    def save_model(self, request, obj, form, change):
        before = None
        if change:
            before = Office.objects.get(pk=obj.pk)
        super().save_model(request, obj, form, change)
        log_model_change(
            "office.updated" if change else "office.created",
            actor=actor_from_user(request.user),
            instance=obj,
            before_instance=before,
            snapshot_fields=[
                "name",
                "stable_key",
                "slug",
                "kind",
                "parent",
                "region",
                "is_assignable",
                "is_active",
                "street_address",
                "city",
                "state",
                "zip_code",
                "main_phone",
                "public_email",
                "internal_email",
                "office_hours",
                "parking_instructions",
                "access_instructions",
            ],
            metadata={"admin": True},
        )

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        actor = actor_from_user(request.user)
        for deleted in formset.deleted_objects:
            log_model_change(
                "office.assignment.deleted",
                actor=actor,
                instance=deleted,
                before_instance=deleted,
                snapshot_fields=[
                    "office",
                    "user",
                    "assignment_type",
                    "is_primary",
                    "starts_at",
                    "ends_at",
                ],
                metadata={"admin": True},
            )
            deleted.delete()
        for instance in instances:
            before = None
            action = "office.assignment.created"
            if instance.pk:
                before = OfficeContactAssignment.objects.get(pk=instance.pk)
                action = "office.assignment.updated"
            instance.save()
            log_model_change(
                action,
                actor=actor,
                instance=instance,
                before_instance=before,
                snapshot_fields=[
                    "office",
                    "user",
                    "assignment_type",
                    "is_primary",
                    "starts_at",
                    "ends_at",
                ],
                metadata={"admin": True},
            )
        formset.save_m2m()


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
    list_filter = ["is_staff", "is_superuser", "is_active", "office"]
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
                    "legacy_groups_preview",
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
    readonly_fields = ["profile_completed_at", "legacy_groups_preview"]
    actions = ["reset_onboarding"]
    inlines = [UserRoleAssignmentInline]

    @admin.display(description="Legacy groups")
    def legacy_groups_preview(self, obj):
        if obj.pk is None:
            return "-"
        names = list(obj.groups.values_list("name", flat=True))
        return ", ".join(names) if names else "-"

    @admin.action(description="Reset onboarding for selected users")
    def reset_onboarding(self, request: HttpRequest, queryset):
        scoped_queryset = scope_queryset_for_user_office(
            request.user,
            queryset,
            field_name="office",
        )
        assert_admin_bulk_scope(
            request.user,
            queryset,
            scoped_queryset=scoped_queryset,
            policy_key="user_admin_reset_onboarding",
        )
        actor = actor_from_user(request.user)
        before_by_pk = {
            user.pk: User.objects.get(pk=user.pk) for user in scoped_queryset
        }
        count = scoped_queryset.update(
            profile_completed=False,
            profile_completed_at=None,
        )
        # Increment version so the reset is distinguishable from the original.
        for user in scoped_queryset:
            user.onboarding_version = (user.onboarding_version or 0) + 1
            user.save(update_fields=["onboarding_version"])
            log_model_change(
                "user.onboarding.reset",
                actor=actor,
                instance=user,
                before_instance=before_by_pk[user.pk],
                snapshot_fields=[
                    "profile_completed",
                    "profile_completed_at",
                    "onboarding_version",
                    "office",
                ],
                metadata={"admin": True},
            )
        self.message_user(
            request,
            f"Reset onboarding for {count} user(s). "
            "They will be redirected to /onboarding on next login.",
            messages.SUCCESS,
        )

    def has_module_permission(self, request):
        return has_admin_permission(request.user, "user.view_user")

    def has_view_permission(self, request, obj=None):
        return has_admin_permission(request.user, "user.view_user")

    def has_add_permission(self, request):
        return has_admin_permission(request.user, "user.add_user")

    def has_change_permission(self, request, obj=None):
        return has_admin_permission(request.user, "user.change_user")

    def get_queryset(self, request):
        queryset = (
            super().get_queryset(request).select_related("office", "office__region")
        )
        return scope_queryset_for_user_office(
            request.user,
            queryset,
            field_name="office",
        )

    def save_model(self, request, obj, form, change):
        before = None
        if change:
            before = User.objects.get(pk=obj.pk)
        super().save_model(request, obj, form, change)
        if change:
            log_model_change(
                "user.role_scope.updated",
                actor=actor_from_user(request.user),
                instance=obj,
                before_instance=before,
                snapshot_fields=[
                    "office",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "profile_completed",
                ],
                metadata={
                    "groups": list(obj.groups.values_list("name", flat=True)),
                    "permissions": list(
                        obj.user_permissions.values_list("codename", flat=True)
                    ),
                },
            )
