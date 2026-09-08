"""Create and grant the office resources administration permissions.

Creates ``web.view_office_resources_admin``, ``web.manage_office_resources``,
and ``web.publish_company_resources`` permission rows and hands them to the
groups whose role bundles carry them (``_OPS_ALL`` / ``_OPS_REGIONAL`` /
``_OPS_BRANCH`` plus Regional Admin, Branch Admin, and Marketing Team).
"""

from django.db import migrations


PERMISSION_NAMES = {
    "view_office_resources_admin": "Can view the office resources console",
    "manage_office_resources": "Can manage scoped office resources",
    "publish_company_resources": "Can publish company-wide office resources",
}

READ_MANAGE_GROUPS = (
    "Admins",
    "Principal Broker",
    "Broker Admin",
    "Region Managers",
    "Regional Admin",
    "Branch Managers",
    "Branch Admin / Office Admin",
    "Marketing Team",
)

PUBLISH_GROUPS = ("Admins", "Principal Broker", "Broker Admin")


def grant_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="web",
        model="operationspermission",
    )
    permissions = {}
    for codename, name in PERMISSION_NAMES.items():
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission

    for group_name in READ_MANAGE_GROUPS:
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(
            permissions["view_office_resources_admin"],
            permissions["manage_office_resources"],
        )
    for group_name in PUBLISH_GROUPS:
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(permissions["publish_company_resources"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(
        content_type__app_label="web",
        content_type__model="operationspermission",
        codename__in=PERMISSION_NAMES,
    )
    for group in Group.objects.all():
        group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0008_quick_access_click"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
