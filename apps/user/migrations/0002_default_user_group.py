"""Seed the default role group (see config/settings.DEFAULT_USER_GROUP).

Data migration so the group exists before the first signup, letting admins
grant it permissions in the Django admin ahead of rollout. The signup signal
(apps/user/signals.py) also get_or_creates it, so renaming the default group
in settings self-heals for new users.
"""

from django.db import migrations

# Keep in sync with config/settings.DEFAULT_USER_GROUP ("Users").
DEFAULT_USER_GROUP = "Users"


def create_default_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=DEFAULT_USER_GROUP)


def remove_default_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=DEFAULT_USER_GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_group, remove_default_group),
    ]
