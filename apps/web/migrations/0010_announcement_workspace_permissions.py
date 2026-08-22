"""Split announcement authority into authoring, publication, and pinning.

``web.manage_announcements`` already existed and keeps its meaning narrowed to
*authoring*: open the workspace, write and save drafts. Two new grants carry
the halves that change what readers see — ``web.publish_announcements`` for the
draft → scheduled → published → archived lifecycle, and
``web.pin_announcements`` for feed ordering.

Grants follow the reviewed bundles in ``apps/user/roles.py``: everybody who
already held ``manage_announcements`` keeps the ability to publish, so no
existing publisher is locked out by the split, while the roles that gain
authoring here (office administrators, compliance, IT support) receive only the
grant their bundle names.
"""

from django.db import migrations

PERMISSION_NAMES = {
    "publish_announcements": "Can publish, schedule, and archive announcements",
    "pin_announcements": "Can pin announcements",
}

#: Roles whose bundle carries ``web.manage_announcements`` after this change.
AUTHOR_GROUPS = (
    "Admins",
    "Principal Broker",
    "Broker Admin",
    "Region Managers",
    "Regional Admin",
    "Branch Managers",
    "Branch Admin",
    "Marketing Team",
    "Compliance",
    "IT Support",
)

PUBLISH_GROUPS = (
    "Admins",
    "Principal Broker",
    "Broker Admin",
    "Region Managers",
    "Branch Managers",
    "Marketing Team",
    "Compliance",
)

PIN_GROUPS = (
    "Admins",
    "Principal Broker",
    "Broker Admin",
    "Region Managers",
    "Marketing Team",
)


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
    manage, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename="manage_announcements",
        defaults={"name": "Can manage announcements"},
    )

    for group_name in AUTHOR_GROUPS:
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(manage)
    for group_name in PUBLISH_GROUPS:
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(permissions["publish_announcements"])
    for group_name in PIN_GROUPS:
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(permissions["pin_announcements"])


def revoke_permissions(apps, schema_editor):
    """Only the new grants are withdrawn.

    ``manage_announcements`` predates this migration, so removing it on reverse
    would take away authority the previous state legitimately held.
    """
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
        ("web", "0009_office_resource_admin_permissions"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
