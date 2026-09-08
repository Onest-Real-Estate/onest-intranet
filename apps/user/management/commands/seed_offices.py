from django.core.management.base import BaseCommand
from django.db import transaction

from apps.user.office_seed import SeedConflictError, seed_offices


class Command(BaseCommand):
    help = "Seed the Onest org tree (head office, regions, branches)."

    def handle(self, *args, **options):
        with transaction.atomic():
            report = seed_offices()
        if report.conflicting:
            raise SeedConflictError(f"Office seed conflicts: {report.conflicting}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Offices seeded: {report.created} created, {report.matched} matched."
            )
        )
