import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.announcements.seed import seed_announcements
from apps.user.office_seed import SeedConflictError, seed_offices
from apps.user.roles import seed_role_groups
from apps.user.user_seed import seed_users


class Command(BaseCommand):
    help = "Seed offices, role groups, and demo users for local development."

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
                # After users: the role selectors only mean something once
                # somebody holds those roles.
                announcement_report = seed_announcements()
        except SeedConflictError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Dev seed complete: "
                f"{len(office_report.created)} offices created, "
                f"{len(office_report.matched)} matched; "
                f"{len(user_report.created)} users created, "
                f"{len(user_report.matched)} matched; "
                f"{len(announcement_report.created)} announcements created, "
                f"{len(announcement_report.matched)} updated."
            )
        )
