from django.core.management.base import BaseCommand

from apps.announcements.seed import seed_announcements


class Command(BaseCommand):
    help = (
        "Seed demo announcements covering every audience selector, priority, "
        "and lifecycle state. Idempotent."
    )

    def handle(self, *args, **options):
        report = seed_announcements()
        if report.skipped:
            self.stderr.write(
                self.style.WARNING(
                    "Skipped (run seed_offices first): " + ", ".join(report.skipped)
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Announcement seed complete: "
                f"{len(report.created)} created, {len(report.matched)} updated."
            )
        )
