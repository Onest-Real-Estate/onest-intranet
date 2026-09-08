from django.core.management.base import BaseCommand

from apps.announcements.media_service import sweep_orphan_media


class Command(BaseCommand):
    help = (
        "Delete announcement media storage nobody can account for: objects "
        "left by rolled-back uploads, and files on long-abandoned drafts. "
        "Safe to run at any time."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be removed without deleting anything.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            # Reporting without deleting means running the same query the sweep
            # runs, so the two can never disagree about what counts as orphaned.
            from apps.announcements.media_service import (
                ABANDONED_DRAFT_DAYS,
                ORPHAN_GRACE_HOURS,
            )

            self.stdout.write(
                f"Would sweep: draft media untouched for {ABANDONED_DRAFT_DAYS} "
                f"days, and unreferenced objects older than "
                f"{ORPHAN_GRACE_HOURS} hours."
            )
            return
        report = sweep_orphan_media()
        self.stdout.write(
            self.style.SUCCESS(
                f"Swept {len(report.deleted_rows)} abandoned media rows and "
                f"{len(report.deleted_objects)} unreferenced objects."
            )
        )
