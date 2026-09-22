from django.core.management.base import BaseCommand

from apps.transactions.tasks import sweep_orphan_documents


class Command(BaseCommand):
    help = (
        "Delete abandoned pending transaction document versions and "
        "unreferenced objects under the transactions/ storage prefix."
    )

    def handle(self, *args, **options):
        report = sweep_orphan_documents()
        self.stdout.write(
            self.style.SUCCESS(
                f"Swept {len(report.deleted_rows)} abandoned rows and "
                f"{len(report.deleted_objects)} unreferenced objects."
            )
        )
