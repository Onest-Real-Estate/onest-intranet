"""Celery tasks for compliance acknowledgement reminders and delayed publish."""

from __future__ import annotations

from celery import shared_task


@shared_task
def send_policy_ack_reminders() -> int:
    """Remind users with overdue mandatory acknowledgements.

    Idempotent via notification ``dedupe_key`` per user+policy version.
    """
    from apps.compliance.notification_schedule import publish_ack_reminders

    return publish_ack_reminders()


@shared_task
def release_effective_mandatory_policies() -> int:
    """Fan out mandatory policies whose effective window just opened."""
    from apps.compliance.notification_schedule import (
        release_effective_mandatory_policies as release,
    )

    return release()
