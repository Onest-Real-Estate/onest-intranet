"""Background delivery for audiences too large to write inside a request.

A company announcement is one row per recipient. Writing five thousand of them
in the request that publishes it would hold a transaction open for the length
of the write and time out the person who clicked the button, so audience
delivery is always queued and always chunked.

Re-running a chunk is safe: :func:`apps.notifications.service.deliver_many`
de-duplicates on ``(recipient, dedupe_key)``.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils.dateparse import parse_datetime

logger = logging.getLogger("apps.notifications")


def _request_from_payload(payload: dict, recipient_id: int):
    from apps.notifications.contract import NotificationRequest

    available_at = payload.get("available_at")
    expires_at = payload.get("expires_at")
    return NotificationRequest(
        recipient_id=recipient_id,
        notification_type=payload["notification_type"],
        event_key=payload["event_key"],
        title=payload["title"],
        dedupe_key=payload["dedupe_key"],
        priority=payload.get("priority", 3),
        is_mandatory=bool(payload.get("is_mandatory", False)),
        source_module=payload.get("source_module", ""),
        source_record_type=payload.get("source_record_type", ""),
        source_record_id=payload.get("source_record_id", ""),
        action_key=payload.get("action_key", ""),
        action_args=tuple(payload.get("action_args", ())),
        available_at=parse_datetime(available_at) if available_at else None,
        expires_at=parse_datetime(expires_at) if expires_at else None,
    )


@shared_task(ignore_result=True)
def fan_out_notifications(payload: dict, recipient_ids: list[int]) -> int:
    """Deliver one chunk, then hand the remainder to a fresh task.

    Returns the number created by *this* chunk. The tail is queued rather than
    looped so a long audience cannot monopolise one worker.
    """
    from apps.notifications.service import FAN_OUT_CHUNK_SIZE, deliver_many

    head = recipient_ids[:FAN_OUT_CHUNK_SIZE]
    tail = recipient_ids[FAN_OUT_CHUNK_SIZE:]
    created = deliver_many(
        [_request_from_payload(payload, recipient_id) for recipient_id in head]
    )
    if tail:
        fan_out_notifications.delay(payload, tail)
    logger.info(
        "notifications.fan_out event=%s chunk=%d created=%d remaining=%d",
        payload.get("event_key", ""),
        len(head),
        created,
        len(tail),
    )
    return created


@shared_task(ignore_result=True)
def purge_expired_notifications() -> int:
    """Housekeeping for expired rows; safe to schedule with celery beat."""
    from apps.notifications.service import purge_expired

    deleted = purge_expired()
    logger.info("notifications.purged expired=%d", deleted)
    return deleted
