from django.db import migrations, models

PERMISSION_NAMES = {
    "view_own_transactions": "Can view own transaction metrics",
    "view_own_tasks": "Can view own task metrics",
    "view_own_commission": "Can view own commission metrics",
    "view_own_leads": "Can view own lead metrics",
    "view_office_tasks": "Can view scoped team task metrics",
}

SELF_SCOPE_CODENAMES = frozenset(
    {
        "view_own_transactions",
        "view_own_tasks",
        "view_own_commission",
        "view_own_leads",
    }
)

# Managers keep their own book of business, so every role receives the
# self-scope grants; only management roles receive the team task aggregate.
ROLE_CODENAMES = {
    "Admins": frozenset(PERMISSION_NAMES),
    "Region Managers": frozenset(PERMISSION_NAMES),
    "Branch Managers": frozenset(PERMISSION_NAMES),
    "Users": SELF_SCOPE_CODENAMES,
}


def grant_dashboard_metric_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="web",
        model="dashboardmetricpermission",
    )
    permissions = {}
    for codename, name in PERMISSION_NAMES.items():
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission
    for group_name, codenames in ROLE_CODENAMES.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(*(permissions[codename] for codename in codenames))


def revoke_dashboard_metric_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(
        content_type__app_label="web",
        content_type__model="dashboardmetricpermission",
        codename__in=PERMISSION_NAMES,
    )
    for group_name in ROLE_CODENAMES:
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("web", "0002_operations_role_permissions"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardMetricPermission",
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
            ],
            options={
                "permissions": (
                    ("view_own_transactions", "Can view own transaction metrics"),
                    ("view_own_tasks", "Can view own task metrics"),
                    ("view_own_commission", "Can view own commission metrics"),
                    ("view_own_leads", "Can view own lead metrics"),
                    ("view_office_tasks", "Can view scoped team task metrics"),
                ),
                "managed": False,
                "default_permissions": (),
            },
        ),
        migrations.RunPython(
            grant_dashboard_metric_permissions,
            revoke_dashboard_metric_permissions,
        ),
    ]
