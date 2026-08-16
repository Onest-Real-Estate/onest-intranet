"""Celery tasks for the Onest app (auto-discovered by config/celery.py)."""

from celery import shared_task


@shared_task
def ping(message: str = "pong") -> str:
    """Minimal task proving the worker wiring — replace with real work.

    Run it in the Django shell with ``ping.delay()`` (or call synchronously
    with ``ping.run()``) once the worker is up (``make up`` + celery service).
    """
    return f"ping: {message}"
