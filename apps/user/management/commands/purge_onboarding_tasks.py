from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.audit.service import AuditTarget, log_event, system_actor
from apps.user.models import OnboardingTask


class Command(BaseCommand):
    help = "Purge resolved onboarding task titles after the two-year retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Delete eligible rows. Without this flag the command is a dry run.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=730)
        queryset = OnboardingTask.objects.filter(
            status=OnboardingTask.Status.RESOLVED,
            resolved_at__lt=cutoff,
        )
        count = queryset.count()
        if not options["commit"]:
            self.stdout.write(
                f"Dry run: {count} resolved onboarding task(s) are eligible for purge."
            )
            return
        with transaction.atomic():
            deleted, _details = queryset.delete()
            log_event(
                "user.onboarding.tasks_retention_purged",
                actor=system_actor("onboarding-retention"),
                target=AuditTarget(
                    target_type="user.onboarding_task.retention",
                    target_label="Resolved onboarding tasks",
                ),
                after={"deleted_count": deleted, "cutoff": cutoff},
                source="management_command",
                channel="retention",
            )
        self.stdout.write(
            self.style.SUCCESS(f"Purged {deleted} resolved onboarding task(s).")
        )
