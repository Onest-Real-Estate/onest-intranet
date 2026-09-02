from django.core.management.base import BaseCommand, CommandError

from apps.user.office_seed import SeedConflictError
from apps.user.onintra.loader import IMPORT_SECTIONS, load_onintra_dump


class Command(BaseCommand):
    help = (
        "Import legacy onintra MariaDB dump data into Hub users, role "
        "assignments, and announcements."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dump",
            required=True,
            help="Path to the legacy onintra .sql dump file.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate the import, then roll back all writes.",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            default=True,
            help="Skip users and announcements that already exist (default: true).",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update users and announcements when a matching record exists.",
        )
        parser.add_argument(
            "--only",
            action="append",
            choices=IMPORT_SECTIONS,
            help=(
                "Limit import to one section. Repeat for multiple sections "
                f"({', '.join(IMPORT_SECTIONS)})."
            ),
        )

    def handle(self, *args, **options):
        skip_existing = options["skip_existing"] and not options["update_existing"]
        only = tuple(options["only"]) if options["only"] else None
        try:
            report = load_onintra_dump(
                dump_path=options["dump"],
                dry_run=options["dry_run"],
                skip_existing=skip_existing,
                only=only,
            )
        except SeedConflictError as exc:
            raise CommandError(str(exc)) from exc
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(report.summary()))
        for warning in report.warnings[:25]:
            self.stdout.write(self.style.WARNING(warning))
        if len(report.warnings) > 25:
            self.stdout.write(
                self.style.WARNING(
                    f"... and {len(report.warnings) - 25} more warnings."
                )
            )
        if options["dry_run"]:
            self.stdout.write(self.style.NOTICE("Dry run complete; no changes saved."))
