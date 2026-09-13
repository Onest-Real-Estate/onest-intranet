"""Celery tasks for compliance acknowledgement reminders."""

from __future__ import annotations

from celery import shared_task


@shared_task
def send_policy_ack_reminders() -> int:
    """Remind users with overdue mandatory acknowledgements.

    Idempotent via notification ``dedupe_key`` per user+policy version.
    """
    from apps.compliance.notification_schedule import publish_ack_reminders

    return publish_ack_reminders()
