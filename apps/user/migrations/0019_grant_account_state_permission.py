"""Grant ``user.manage_account_state`` to the groups that already hold it in code.

``0018`` creates the permission row; this hands it to the brokerage-admin
groups so the deploy that ships the account-access panel does not need a
manual grant. The bundle matches ``_OPS_ALL`` in ``apps.user.roles`` — System
Admin, Principal Broker, and Broker Admin. Anybody else who needs it (IT
support, most likely) is an explicit decision somebody makes in the hub, not a
default.
"""

from django.db import migrations

CODENAME = "manage_account_state"
NAME = "Can disable or reactivate user accounts"
GROUPS = ("Admins", "Principal Broker", "Broker Admin")


def grant_permission(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    content_type, _created = ContentType.objects.get_or_create(
        app_label="user", model="user"
    )
    permission, _created = Permission.objects.get_or_create(
        content_type=content_type,
        codename=CODENAME,
        defaults={"name": NAME},
    )
    for name in GROUPS:
        group, _created = Group.objects.get_or_create(name=name)
        group.permissions.add(permission)


def revoke_permission(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permission = Permission.objects.filter(
        content_type__app_label="user",
        content_type__model="user",
        codename=CODENAME,
    ).first()
    if permission is None:
        return
    for group in Group.objects.filter(name__in=GROUPS):
        group.permissions.remove(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("user", "0018_account_state_permission"),
    ]

    operations = [migrations.RunPython(grant_permission, revoke_permission)]
