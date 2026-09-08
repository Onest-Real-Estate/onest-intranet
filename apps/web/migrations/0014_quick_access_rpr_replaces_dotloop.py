"""Retire the dotloop launcher and seed RPR in its place.

Not a rename. ``QuickAccessLink.stable_key`` is immutable by model validation,
and ``QuickAccessClick.link_stable_key`` keeps counting against the key long
after a tool is retired — so renaming ``dotloop`` to ``rpr`` would silently
re-attribute every historic dotloop click to a product the brokerage had not
adopted yet. Archiving the old row and inserting a new one keeps both stories
true: dotloop's usage stays answerable, RPR starts from zero.

Archiving rather than deleting is the model's own documented rule: audit rows
and onboarding tool-setup steps reference these links.

Idempotent in both directions. A deployment that already renamed the row by
hand keeps whatever it has — the insert is keyed on ``rpr`` and skipped when
present.
"""

from django.db import migrations
from django.utils import timezone

RETIRED_KEY = "dotloop"
NEW_KEY = "rpr"
NEW_NAME = "RPR"
NEW_URL = "https://www.narrpr.com"
#: RPR's own published mark, shipped in the bundle by `BrandMarks.tsx`.
NEW_ICON = "rpr"


def replace(apps, schema_editor):
    QuickAccessLink = apps.get_model("web", "QuickAccessLink")

    retired = QuickAccessLink.objects.filter(stable_key=RETIRED_KEY).first()
    sort_order = retired.sort_order if retired is not None else 40

    if retired is not None and not retired.is_archived:
        retired.is_archived = True
        retired.is_active = False
        retired.archived_at = timezone.now()
        retired.save(
            update_fields=["is_archived", "is_active", "archived_at", "updated_at"]
        )

    if not QuickAccessLink.objects.filter(stable_key=NEW_KEY).exists():
        # Same field set the original four were seeded with, so RPR arrives
        # configured exactly as the tool it replaces was.
        QuickAccessLink.objects.create(
            stable_key=NEW_KEY,
            name=NEW_NAME,
            description="",
            destination_type="external_url",
            destination_value=NEW_URL,
            icon=NEW_ICON,
            sort_order=sort_order,
            is_active=True,
            is_archived=False,
            company_wide=True,
            owner_scope="company",
            sso_capability="none",
            integration_health="unknown",
            setup_behavior="self_service",
        )


def restore(apps, schema_editor):
    QuickAccessLink = apps.get_model("web", "QuickAccessLink")
    QuickAccessLink.objects.filter(stable_key=NEW_KEY).delete()
    retired = QuickAccessLink.objects.filter(stable_key=RETIRED_KEY).first()
    if retired is not None:
        retired.is_archived = False
        retired.is_active = True
        retired.archived_at = None
        retired.save(
            update_fields=["is_archived", "is_active", "archived_at", "updated_at"]
        )


class Migration(migrations.Migration):
    dependencies = [("web", "0013_alter_operationspermission_options")]

    operations = [migrations.RunPython(replace, restore)]
