from django.db import migrations

from apps.documents.taxonomy import CATEGORY_SEED


def seed(apps, schema_editor):
    Category = apps.get_model("documents", "DocumentCategory")
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
    Category = apps.get_model("documents", "DocumentCategory")
    Category.objects.filter(code__in=[item.code for item in CATEGORY_SEED]).update(
        is_system=False
    )


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
