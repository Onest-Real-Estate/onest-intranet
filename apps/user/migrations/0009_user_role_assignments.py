import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def backfill_role_assignments(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("user", "User")
    UserRoleAssignment = apps.get_model("user", "UserRoleAssignment")
    Conflict = apps.get_model("user", "UserRoleAssignmentMigrationConflict")

    group_names = {"Admins", "Region Managers", "Branch Managers", "Users"}
    groups = {
        group.name: group
        for group in Group.objects.filter(name__in=group_names).only("id", "name")
    }
    membership_rows = User.groups.through.objects.filter(
        group_id__in=[group.id for group in groups.values()]
    ).values_list("user_id", "group_id")
    memberships_by_user = {}
    for user_id, group_id in membership_rows:
        memberships_by_user.setdefault(user_id, []).append(group_id)
    name_by_group_id = {group.id: name for name, group in groups.items()}

    for user in User.objects.select_related("office", "office__region").all():
        for group_id in memberships_by_user.get(user.pk, []):
            legacy_role = name_by_group_id[group_id]
            scope_type = None
            scope_office_id = None
            detail = None

            if legacy_role == "Admins":
                scope_type = "company"
            elif legacy_role == "Region Managers":
                if user.office_id and user.office and user.office.region_id:
                    scope_type = "region"
                    scope_office_id = user.office.region_id
                else:
                    detail = (
                        "Legacy region manager is missing a resolvable region scope."
                    )
            elif legacy_role in {"Branch Managers", "Users"}:
                if user.office_id:
                    scope_type = "office"
                    scope_office_id = user.office_id
                else:
                    detail = "Legacy scoped role is missing a home office."

            if detail is not None:
                Conflict.objects.get_or_create(
                    user_id=user.pk,
                    legacy_role=legacy_role,
                    detail=detail,
                )
                continue

            UserRoleAssignment.objects.get_or_create(
                user_id=user.pk,
                role=legacy_role,
                scope_type=scope_type,
                scope_office_id=scope_office_id,
                defaults={
                    "status": "active",
                    "created_at": django.utils.timezone.now(),
                    "updated_at": django.utils.timezone.now(),
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0008_expand_office_domain_model"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserRoleAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("role", models.CharField(max_length=64, verbose_name="role")),
                (
                    "scope_type",
                    models.CharField(
                        choices=[
                            ("company", "Company"),
                            ("region", "Region"),
                            ("office", "Office"),
                        ],
                        max_length=32,
                        verbose_name="scope type",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("scheduled", "Scheduled"),
                            ("active", "Active"),
                            ("expired", "Expired"),
                            ("revoked", "Revoked"),
                        ],
                        default="active",
                        max_length=16,
                        verbose_name="status",
                    ),
                ),
                (
                    "starts_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="starts at"
                    ),
                ),
                (
                    "ends_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="ends at"),
                ),
                (
                    "revoked_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="revoked at"
                    ),
                ),
                (
                    "business_reason",
                    models.TextField(blank=True, verbose_name="business reason"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="created at"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="updated at"),
                ),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="granted_role_assignments",
                        to="user.user",
                        verbose_name="assigned by",
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revoked_role_assignments",
                        to="user.user",
                        verbose_name="revoked by",
                    ),
                ),
                (
                    "scope_office",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="role_assignments",
                        to="user.office",
                        verbose_name="scope office",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="role_assignments",
                        to="user.user",
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "user role assignment",
                "verbose_name_plural": "user role assignments",
                "ordering": ["user__email", "role", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="UserRoleAssignmentMigrationConflict",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "legacy_role",
                    models.CharField(max_length=64, verbose_name="legacy role"),
                ),
                ("detail", models.TextField(verbose_name="detail")),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="created at"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_assignment_migration_conflicts",
                        to="user.user",
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "user role assignment migration conflict",
                "verbose_name_plural": "user role assignment migration conflicts",
                "ordering": ["user__email", "legacy_role", "created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="userroleassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("ends_at__isnull", True),
                    ("starts_at__isnull", True),
                    _connector="OR",
                )
                | models.Q(("ends_at__gte", models.F("starts_at"))),
                name="user_role_assignment_valid_dates",
            ),
        ),
        migrations.AddConstraint(
            model_name="userroleassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("scope_type", "company"), ("scope_office__isnull", True)
                )
                | ~models.Q(("scope_type", "company")),
                name="user_role_assignment_company_scope_empty",
            ),
        ),
        migrations.AddConstraint(
            model_name="userroleassignment",
            constraint=models.CheckConstraint(
                condition=~models.Q(("scope_type__in", ["region", "office"]))
                | models.Q(("scope_office__isnull", False)),
                name="user_role_assignment_scoped_office_required",
            ),
        ),
        migrations.AddConstraint(
            model_name="userroleassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["scheduled", "active"])),
                fields=("user", "role", "scope_type", "scope_office"),
                name="user_role_assignment_unique_live_scope",
            ),
        ),
        migrations.AddIndex(
            model_name="userroleassignment",
            index=models.Index(
                fields=["user", "status", "starts_at", "ends_at"],
                name="user_role_asgn_user_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="userroleassignment",
            index=models.Index(
                fields=["scope_type", "scope_office", "status"],
                name="user_role_asgn_scope_idx",
            ),
        ),
        migrations.RunPython(backfill_role_assignments, migrations.RunPython.noop),
    ]
