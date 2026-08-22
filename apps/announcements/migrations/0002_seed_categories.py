"""Seed the eight governed categories as protected system rows.

Idempotent and non-destructive in both directions: the forward pass only
creates codes that are missing (an operator's relabel survives a redeploy),
and the reverse pass unmarks ``is_system`` rather than deleting rows that
announcements may already reference.
"""

from django.db import migrations

from apps.announcements.taxonomy import CATEGORY_SEED


def seed(apps, schema_editor):
    Category = apps.get_model("announcements", "AnnouncementCategory")
    for item in CATEGORY_SEED:
        Category.objects.update_or_create(
            code=item.code,
            defaults={"is_system": True},
            create_defaults={
                "code": item.code,
                "label": item.label,
                "description": item.description,
                "display_order": item.display_order,
                "is_active": True,
                "is_system": True,
            },
        )


def unseed(apps, schema_editor):
    Category = apps.get_model("announcements", "AnnouncementCategory")
    Category.objects.filter(code__in=[item.code for item in CATEGORY_SEED]).update(
        is_system=False
    )


class Migration(migrations.Migration):
    dependencies = [("announcements", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
