"""Seed the initial tool catalog.

Content, not schema: every row here is editable afterwards without a deploy,
which is the whole reason the catalog is data. The rows live in
``apps.onboarding_tools.catalog`` so the list stays reviewable — a migration is
the wrong place to argue about what SmartMLS is for.

Idempotent by slug, so re-running adds what is missing and leaves edited rows
alone. It deliberately does **not** update an existing row: an administrator who
corrected a contact name should not have that overwritten by a redeploy.
"""

from __future__ import annotations

from django.db import migrations


def seed(apps, schema_editor):
    Tool = apps.get_model("onboarding_tools", "OnboardingTool")
    Audience = apps.get_model("onboarding_tools", "OnboardingToolOfficeAudience")
    Office = apps.get_model("user", "Office")

    from apps.onboarding_tools.catalog import seed_rows

    for row in seed_rows():
        office_slugs = row.pop("offices", ())
        slug = row.pop("slug")
        tool, created = Tool.objects.get_or_create(
            slug=slug,
            defaults={
                "company_wide": not office_slugs,
                "is_required": row.pop("is_required", True),
                **row,
            },
        )
        if not created or not office_slugs:
            continue
        # An office slug this deployment does not have is skipped rather than
        # failing the migration: the seed must not depend on one brokerage's
        # office tree existing exactly as written.
        for office in Office.objects.filter(slug__in=office_slugs):
            Audience.objects.get_or_create(
                tool=tool, office=office, defaults={"include_descendants": True}
            )


def unseed(apps, schema_editor):
    """Remove only rows nobody has recorded progress against.

    A tool an agent is already marked Ready on is somebody's record, and a
    reversed migration should not delete it.
    """
    Tool = apps.get_model("onboarding_tools", "OnboardingTool")
    from apps.onboarding_tools.catalog import seed_rows

    slugs = [row["slug"] for row in seed_rows()]
    Tool.objects.filter(slug__in=slugs, agent_statuses__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("onboarding_tools", "0001_initial"),
        ("user", "0027_feedback_triage_role_grants"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
