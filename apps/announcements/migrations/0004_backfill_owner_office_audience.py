"""Turn each announcement's owning office into an explicit audience row.

Before this migration the owning node *implied* the audience: head office
meant brokerage-wide, a region meant that region, a branch meant that branch.
Audience is now explicit, so the implication is written down once here and
``owner_office`` keeps only its other job — provenance and the scope a manager
needs authority over.

Idempotent: rows are created only where the announcement has no selector yet,
so a re-run after a partial deploy adds nothing twice. The reverse pass drops
only the rows this migration would create, leaving hand-authored selectors
alone.
"""

from django.db import migrations

HEAD_OFFICE = "head_office"
REGION = "region"


def _kind_for(office_kind: str) -> str:
    if office_kind == HEAD_OFFICE:
        return "company"
    if office_kind == REGION:
        return "region"
    return "office"


def backfill(apps, schema_editor):
    Announcement = apps.get_model("announcements", "Announcement")
    Audience = apps.get_model("announcements", "AnnouncementAudience")

    rows = []
    for announcement in Announcement.objects.select_related("owner_office").exclude(
        audiences__isnull=False
    ):
        kind = _kind_for(announcement.owner_office.kind)
        rows.append(
            Audience(
                announcement=announcement,
                kind=kind,
                role="",
                office=None if kind == "company" else announcement.owner_office,
                user=None,
            )
        )
    Audience.objects.bulk_create(rows, ignore_conflicts=True)


def drop_backfilled(apps, schema_editor):
    Announcement = apps.get_model("announcements", "Announcement")
    Audience = apps.get_model("announcements", "AnnouncementAudience")

    for announcement in Announcement.objects.select_related("owner_office"):
        kind = _kind_for(announcement.owner_office.kind)
        Audience.objects.filter(
            announcement=announcement,
            kind=kind,
            office=None if kind == "company" else announcement.owner_office,
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        (
            "announcements",
            "0003_announcement_attachment_announcement_attachment_name_and_more",
        )
    ]

    operations = [migrations.RunPython(backfill, drop_backfilled)]
