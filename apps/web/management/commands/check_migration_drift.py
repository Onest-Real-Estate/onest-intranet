"""Surface drift between ``django_migrations`` and the files on disk.

``makemigrations --check`` compares models against migration files; it never
looks at the database. A database that applied a migration from a feature
branch that later landed renumbered keeps a recorder row no file owns, and
the schema disagreement stays invisible until a write fails
(https://github.com/Onest-Real-Estate/onest-intranet/issues/204). Duplicate
recorder rows are the scar tissue of concurrent ``migrate`` runs racing at
stack startup.

This command makes both visible. ``--prune`` deletes the orphaned rows; it
only ever touches the ``django_migrations`` recorder table, never schema.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = (
        "Report migration recorder rows no file on disk owns (phantoms) and "
        "duplicate recorder rows. --prune deletes them; schema is never touched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Delete phantom and duplicate recorder rows.",
        )
        parser.add_argument(
            "--database",
            default="default",
            help="Database alias to check (default: default).",
        )

    def handle(self, *, prune: bool, database: str, **options):
        connection = connections[database]
        recorder = MigrationRecorder(connection)
        loader = MigrationLoader(connection, load=False)
        loader.load_disk()
        disk = set(loader.disk_migrations)

        rows = list(
            recorder.migration_qs.order_by("app", "name", "applied").values(
                "id", "app", "name"
            )
        )

        phantom_ids: list[int] = []
        phantoms: list[str] = []
        seen: set[tuple[str, str]] = set()
        duplicate_ids: list[int] = []
        duplicates: list[str] = []
        for row in rows:
            key = (row["app"], row["name"])
            label = f"{row['app']}/{row['name']}"
            if key not in disk:
                phantom_ids.append(row["id"])
                phantoms.append(label)
            elif key in seen:
                duplicate_ids.append(row["id"])
                duplicates.append(label)
            else:
                seen.add(key)

        unapplied = sorted(f"{app}/{name}" for app, name in disk - seen)

        if phantoms:
            self.stdout.write(
                self.style.WARNING("Applied but no file on disk (phantoms):")
            )
            for label in phantoms:
                self.stdout.write(f"  {label}")
        if duplicates:
            self.stdout.write(self.style.WARNING("Duplicate recorder rows:"))
            for label in duplicates:
                self.stdout.write(f"  {label}")
        if unapplied:
            self.stdout.write("On disk but not applied (run migrate):")
            for label in unapplied:
                self.stdout.write(f"  {label}")

        if not (phantoms or duplicates):
            self.stdout.write(self.style.SUCCESS("No migration drift."))
            return

        if not prune:
            raise CommandError(
                f"{len(phantoms)} phantom(s), {len(duplicates)} duplicate(s). "
                "Re-run with --prune to delete these recorder rows."
            )

        deleted, _ = recorder.migration_qs.filter(
            id__in=[*phantom_ids, *duplicate_ids]
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"Pruned {deleted} recorder row(s)."))
