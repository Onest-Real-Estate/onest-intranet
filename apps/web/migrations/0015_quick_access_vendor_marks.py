"""Point Lofty, SkySlope, and RPR at their own vendor marks.

These three were seeded with *category* glyphs — a contact card for the CRM, a
shield for the compliance tool, a chart for the data service. That was the
right default while the bundle shipped no artwork for them: a silhouette
nobody mistakes for a logo beats an approximation of one.

The bundle now ships each vendor's own published mark (see
``frontend/components/BrandMarks.tsx``), so the stored key moves to it.

Only rows still holding the seeded category glyph are touched. An
administrator who has deliberately chosen a different mark keeps their choice,
which is what makes this safe to run against a live database.
"""

from django.db import migrations

#: stable key → (icon it was seeded with, icon it moves to). The "from" half is
#: what makes this conservative: a row that has drifted is left alone.
MOVES: tuple[tuple[str, str, str], ...] = (
    ("lofty", "contact", "lofty"),
    ("skyslope", "shield-check", "skyslope"),
    # Only reachable on a database that ran 0014 before the artwork landed;
    # a fresh one is seeded with the vendor mark already.
    ("rpr", "chart-line", "rpr"),
)


def apply_marks(apps, schema_editor):
    QuickAccessLink = apps.get_model("web", "QuickAccessLink")
    for stable_key, seeded_icon, vendor_icon in MOVES:
        QuickAccessLink.objects.filter(stable_key=stable_key, icon=seeded_icon).update(
            icon=vendor_icon
        )


def revert_marks(apps, schema_editor):
    QuickAccessLink = apps.get_model("web", "QuickAccessLink")
    for stable_key, seeded_icon, vendor_icon in MOVES:
        QuickAccessLink.objects.filter(stable_key=stable_key, icon=vendor_icon).update(
            icon=seeded_icon
        )


class Migration(migrations.Migration):
    dependencies = [("web", "0014_quick_access_rpr_replaces_dotloop")]

    operations = [migrations.RunPython(apply_marks, revert_marks)]
