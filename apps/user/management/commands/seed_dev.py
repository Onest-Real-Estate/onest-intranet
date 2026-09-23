import os
from collections.abc import Callable

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.announcements.seed import seed_announcements
from apps.compliance.seed import seed_compliance
from apps.contract.seed import seed_contracts
from apps.documents.seed import seed_documents
from apps.feedback.seed import seed_feedback
from apps.inventory.seed import seed_inventory
from apps.it_support.seed import seed_it_support
from apps.marketing.seed import seed_marketing
from apps.notifications.seed import seed_notifications
from apps.onboarding_tools.seed import seed_onboarding
from apps.operational_tasks.seed import seed_operational_tasks
from apps.reservations.seed import seed_reservations
from apps.training.seed import seed_training
from apps.transactions.seed import seed_transactions
from apps.user.office_resource_seed import seed_office_resources
from apps.user.office_seed import SeedConflictError, seed_offices
from apps.user.roles import seed_role_groups
from apps.user.user_seed import ready_existing_superusers, seed_users
from apps.web.seed import seed_quick_access
from apps.web.seed_support import SeedReport
from config.celery import app as celery_app

#: Domain seeds in dependency order. Notifications run last so they can point
#: at the rows the others created.
DOMAIN_SEEDS: tuple[tuple[str, Callable[[], SeedReport]], ...] = (
    ("office resources", seed_office_resources),
    ("quick access links", seed_quick_access),
    ("onboarding", seed_onboarding),
    ("transactions", seed_transactions),
    ("IT tickets", seed_it_support),
    ("feedback tickets", seed_feedback),
    ("operational tasks", seed_operational_tasks),
    ("inventory", seed_inventory),
    ("rooms & bookings", seed_reservations),
    ("training", seed_training),
    ("documents", seed_documents),
    ("marketing assets", seed_marketing),
    ("policies", seed_compliance),
    ("agent contracts", seed_contracts),
    ("notifications", seed_notifications),
)


class Command(BaseCommand):
    help = (
        "Seed offices, roles, demo users, and demo data for every hub module "
        "(local development only)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=os.environ.get("SEED_USER_PASSWORD", "onest-dev-seed"),
            help="Password for newly created seed users (default: onest-dev-seed).",
        )
        parser.add_argument(
            "--faker-seed",
            type=int,
            default=int(os.environ.get("SEED_FAKER_SEED", "42")),
            help="Faker seed for deterministic names and profile fields (default: 42).",
        )
        parser.add_argument(
            "--core-only",
            action="store_true",
            help="Seed offices, roles, users, and announcements only.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        try:
            with transaction.atomic():
                office_report = seed_offices()
                if office_report.conflicting:
                    raise SeedConflictError(
                        f"Office seed conflicts: {office_report.conflicting}"
                    )
                seed_role_groups()
                user_report = seed_users(
                    password=password,
                    ensure_prerequisites=False,
                    faker_seed=options["faker_seed"],
                )
                readied = ready_existing_superusers()
                # After users: the role selectors only mean something once
                # somebody holds those roles.
                announcement_report = seed_announcements()
        except SeedConflictError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Core seed complete: "
                f"{len(office_report.created)} offices created, "
                f"{len(office_report.matched)} matched; "
                f"{len(user_report.created)} users created, "
                f"{len(user_report.matched)} matched; "
                f"{len(announcement_report.created)} announcements created, "
                f"{len(announcement_report.matched)} updated; "
                f"superusers readied: {', '.join(readied) or 'none'}."
            )
        )
        if options["core_only"]:
            return
        self._seed_domains()

    def _seed_domains(self) -> None:
        # Services schedule notification fan-out and event delivery on Celery.
        # A dev box often has no broker, so run those tasks inline for the
        # duration of the seed rather than hanging on a connection retry.
        # The app reads Django settings under the ``CELERY`` namespace, so only
        # the prefixed key takes effect; ``conf.task_always_eager = …`` is
        # silently ignored.
        previous = celery_app.conf.task_always_eager
        celery_app.conf.CELERY_TASK_ALWAYS_EAGER = True
        failed: list[str] = []
        try:
            for label, seed in DOMAIN_SEEDS:
                try:
                    with transaction.atomic():
                        report = seed()
                except Exception as exc:  # noqa: BLE001 — report and continue
                    failed.append(label)
                    self.stderr.write(self.style.ERROR(f"  {label}: failed — {exc!r}"))
                    continue
                line = f"  {label}: {report.summary('rows')}"
                if report.skipped:
                    line += f"; skipped {len(report.skipped)}: {report.skipped}"
                self.stdout.write(line)
        finally:
            celery_app.conf.CELERY_TASK_ALWAYS_EAGER = previous
        if failed:
            self.stderr.write(
                self.style.ERROR(f"Demo seed finished with failures: {failed}")
            )
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Demo data seeded for every module."))
