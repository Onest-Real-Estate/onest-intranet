import os

from django.core.management.base import BaseCommand

from apps.user.office_seed import SeedConflictError
from apps.user.user_seed import seed_users


class Command(BaseCommand):
    help = (
        "Seed demo users with display names, offices, and role assignments "
        "(local/dev only)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=os.environ.get("SEED_USER_PASSWORD", "onest-dev-seed"),
            help="Password for newly created seed users (default: onest-dev-seed).",
        )
        parser.add_argument(
            "--skip-prerequisites",
            action="store_true",
            help="Do not run office/role seeding before creating users.",
        )
        parser.add_argument(
            "--faker-seed",
            type=int,
            default=int(os.environ.get("SEED_FAKER_SEED", "42")),
            help="Faker seed for deterministic names and profile fields (default: 42).",
        )

    def handle(self, *args, **options):
        try:
            report = seed_users(
                password=options["password"],
                ensure_prerequisites=not options["skip_prerequisites"],
                faker_seed=options["faker_seed"],
            )
        except SeedConflictError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Users seeded: {len(report.created)} created, "
                f"{len(report.matched)} matched; "
                f"{len(report.assignments_created)} assignments created, "
                f"{len(report.assignments_matched)} matched."
            )
        )
