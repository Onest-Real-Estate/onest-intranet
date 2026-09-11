"""Drain marketing files that never finished processing.

An upload lands in ``PENDING`` and a Celery worker moves it to ``READY``. When
no worker consumes the queue — a local run without ``make up``, or an outage in
production — the row stays ``PENDING`` for ever, the publish checklist keeps
reporting "Files are still being processed", and nothing ever changes that on
its own.

This runs the *same* task in-process, so a stuck backlog clears without a
worker and without a second implementation of the processing pass. It is
idempotent: the task re-derives everything from the stored bytes, so a row that
already succeeded lands on the same state.
"""

from django.core.management.base import BaseCommand

from apps.marketing.models import MarketingFile

State = MarketingFile.ProcessingState


class Command(BaseCommand):
    help = (
        "Process marketing files stuck in PENDING because no Celery worker "
        "consumed it. Runs the real processing task in-process. Safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--asset",
            type=int,
            default=None,
            help="Limit to one marketing asset id.",
        )
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help=(
                "Also retry rows that FAILED, which is usually unreadable "
                "storage and can be transient. Quarantined rows are never "
                "retried: that verdict is a security decision, not an error."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be processed without touching anything.",
        )

    def handle(self, *args, **options):
        from apps.marketing.tasks import process_marketing_file

        states = [State.PENDING]
        if options["retry_failed"]:
            states.append(State.FAILED)
        rows = MarketingFile.objects.filter(processing_state__in=states)
        if options["asset"] is not None:
            rows = rows.filter(asset_id=options["asset"])
        rows = rows.order_by("pk")

        if not rows.exists():
            self.stdout.write("Nothing is waiting to be processed.")
            return

        if options["dry_run"]:
            for row in rows:
                self.stdout.write(
                    f"Would process #{row.pk} {row.display_name} "
                    f"({row.processing_state}) on asset "
                    f"{row.asset.pk}"
                )
            return

        outcomes: dict[str, int] = {}
        # The ids are collected first: the task mutates the rows the queryset
        # filters on, so iterating it lazily would walk a moving set.
        for media_id in list(rows.values_list("pk", flat=True)):
            # ``apply`` runs the task in this process whatever the broker is
            # doing — that is the whole point of the command.
            state = str(process_marketing_file.apply(args=(media_id,)).get())
            outcomes[state] = outcomes.get(state, 0) + 1
            self.stdout.write(f"#{media_id} -> {state}")

        summary = ", ".join(
            f"{count} {state}" for state, count in sorted(outcomes.items())
        )
        ready = outcomes.get(State.READY, 0)
        style = self.style.SUCCESS if ready else self.style.WARNING
        self.stdout.write(style(f"Processed {sum(outcomes.values())}: {summary}."))
