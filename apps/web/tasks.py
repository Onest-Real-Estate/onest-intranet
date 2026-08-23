"""Celery tasks for the Onest app (auto-discovered by config/celery.py)."""

from celery import shared_task

# Reporting export tasks live in apps.web.reporting.tasks; import so the
# worker registers them via this app's autodiscovered tasks module.
from apps.web.reporting.tasks import (  # noqa: F401
    expire_report_exports,
    run_report_export,
)


@shared_task
def ping(message: str = "pong") -> str:
    """Minimal task proving the worker wiring — replace with real work.

    Run it in the Django shell with ``ping.delay()`` (or call synchronously
    with ``ping.run()``) once the worker is up (``make up`` + celery service).
    """
    return f"ping: {message}"
