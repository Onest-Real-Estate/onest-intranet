"""Brokerage role catalog table plus stable-code backfill.

Creates ``BrokerageRole`` rows for the fourteen system roles, remaps legacy
``UserRoleAssignment.role`` group names to stable codes, and grants each role's
default permission bundle additively onto its Django group.
"""

import django.utils.timezone
from django.db import migrations, models


LEGACY_ROLE_ALIASES = {
    "Admins": "system_admin",
    "Users": "realtor",
    "Region Managers": "regional_manager",
    "Branch Managers": "branch_manager",
    "Admin": "system_admin",
    "Agent": "realtor",
    "Region manager": "regional_manager",
    "Branch manager": "branch_manager",
}


def seed_and_remap_roles(apps, schema_editor):
    from apps.user.roles import (
        ROLE_BY_KEY,
        ROLE_DEFINITIONS,
        normalize_role_code,
        seed_brokerage_roles,
    )

    seed_brokerage_roles(sync_presentation=True, sync_permissions=True)

    UserRoleAssignment = apps.get_model("user", "UserRoleAssignment")
    Conflict = apps.get_model("user", "UserRoleAssignmentMigrationConflict")

    for assignment in UserRoleAssignment.objects.all().iterator():
        raw = assignment.role
        code = normalize_role_code(raw) or LEGACY_ROLE_ALIASES.get(raw)
        if code is None:
            Conflict.objects.get_or_create(
                user_id=assignment.user_id,
                legacy_role=raw,
                defaults={
                    "detail": (
                        "Unknown role string during brokerage catalog migration; "
                        "left unchanged for manual review."
                    ),
                },
            )
            continue
        if raw != code:
            assignment.role = code
            assignment.save(update_fields=["role"])

    # Ensure every required code exists once (seed already did; assert for ops).
    BrokerageRole = apps.get_model("user", "BrokerageRole")
    existing = set(BrokerageRole.objects.values_list("code", flat=True))
    missing = set(ROLE_BY_KEY) - existing
    if missing:
        raise RuntimeError(f"Brokerage role seed missed codes: {sorted(missing)}")

    # Presentation sanity: fourteen definitions.
    if len(ROLE_DEFINITIONS) != 14:
        raise RuntimeError("Expected 14 brokerage role definitions.")


def noop_reverse(apps, schema_editor):
    """Leaving remapped codes in place is safer than guessing legacy strings."""


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0016_organization_hierarchy_membership"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("web", "0005_grant_new_agent_onboarding_permission"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userroleassignment",
            name="role",
            field=models.CharField(db_index=True, max_length=64, verbose_name="role"),
        ),
        migrations.CreateModel(
            name="BrokerageRole",
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
                    "code",
                    models.SlugField(max_length=64, unique=True, verbose_name="code"),
                ),
                (
                    "display_name",
                    models.CharField(max_length=128, verbose_name="display name"),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="description"),
                ),
                (
                    "group_name",
                    models.CharField(max_length=150, verbose_name="django group name"),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="active"),
                ),
                (
                    "is_assignable",
                    models.BooleanField(default=True, verbose_name="assignable"),
                ),
                (
                    "is_system",
                    models.BooleanField(default=True, verbose_name="system managed"),
                ),
                (
                    "is_protected",
                    models.BooleanField(default=False, verbose_name="protected"),
                ),
                (
                    "valid_scope_types",
                    models.JSONField(default=list, verbose_name="valid scope types"),
                ),
                (
                    "priority",
                    models.PositiveSmallIntegerField(
                        default=100, verbose_name="priority"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        verbose_name="created at",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="updated at"),
                ),
            ],
            options={
                "verbose_name": "brokerage role",
                "verbose_name_plural": "brokerage roles",
                "ordering": ["priority", "code"],
                "indexes": [
                    models.Index(
                        fields=["is_active", "is_assignable"],
                        name="brokerage_role_assign",
                    )
                ],
            },
        ),
        migrations.RunPython(seed_and_remap_roles, noop_reverse),
    ]
