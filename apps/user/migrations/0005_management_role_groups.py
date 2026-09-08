"""Seed hub management roles.

Superadmin is Django ``is_superuser``, not a group. The default agent group
``Users`` is created in 0002; this migration adds Admins, Region Managers,
and Branch Managers.
"""

from django.db import migrations

MANAGEMENT_GROUPS = ("Admins", "Region Managers", "Branch Managers")


def create_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in MANAGEMENT_GROUPS:
        Group.objects.get_or_create(name=name)


def remove_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=MANAGEMENT_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0004_office_and_profile_fields"),
    ]

    operations = [
        migrations.RunPython(create_role_groups, remove_role_groups),
    ]
