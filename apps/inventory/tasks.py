"""Celery tasks for inventory reservation notifications and overdue sync."""

from __future__ import annotations

from celery import shared_task


@shared_task
def send_inventory_return_notifications() -> int:
    """Beat-safe return reminders and overdue escalations."""
    from apps.inventory.notification_schedule import (
        publish_inventory_return_notifications,
    )

    return publish_inventory_return_notifications()
