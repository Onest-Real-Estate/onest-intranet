"""Grant the administrative profile permissions to the management roles.

Scope is enforced separately, in ``services.agent_administration``: holding
``change_user_administration`` lets a branch manager edit the people in their
own office, and nobody else.
"""

from django.db import migrations

PERMISSION_NAMES = {
    "view_user_administration": "Can view administrative profile fields",
    "change_user_administration": "Can change administrative profile fields",
}

ROLE_CODENAMES = {
    "Admins": frozenset(PERMISSION_NAMES),
    "Region Managers": frozenset(PERMISSION_NAMES),
    "Branch Managers": frozenset(PERMISSION_NAMES),
}


def grant_administration_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    content_type, _created = ContentType.objects.get_or_create(
        app_label="user",
        model="user",
    )
    permissions = {}
    for codename, name in PERMISSION_NAMES.items():
        permission, _created = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission
    for group_name, codenames in ROLE_CODENAMES.items():
        group, _created = Group.objects.get_or_create(name=group_name)
        group.permissions.add(*(permissions[codename] for codename in codenames))


def revoke_administration_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(
        content_type__app_label="user",
        content_type__model="user",
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
        ("user", "0013_agent_administration_fields"),
    ]

    operations = [
        migrations.RunPython(
            grant_administration_permissions,
            revoke_administration_permissions,
        ),
    ]
