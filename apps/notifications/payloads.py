"""Serialize notifications for Inertia (camelCase), one page at a time.

Serialization is where the source resolution is applied, so it is the single
place a revoked grant has to be honoured. A row whose source will not vouch
for the reader loses its detail *and* its destination here, whatever the
stored ``action_key`` says.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from django.utils import formats, timezone

from apps.notifications.actions import action_label, resolve_action_href
from apps.notifications.contract import (
    PRIORITY_KEYS,
    PRIORITY_LABELS,
    TYPE_LABELS,
)
from apps.notifications.models import Notification
from apps.notifications.sources import SourceResolution, resolve_sources

#: Shown in place of a destination that no longer resolves — a renamed route,
#: an action removed from the allowlist, or a source that withdrew access.
STALE_ACTION_NOTE = "This shortcut is no longer available."


def received_label(notification: Notification, *, now: datetime) -> str:
    local = timezone.localtime(notification.available_at)
    delta = now - notification.available_at
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    return formats.date_format(local, "M j, Y")


def serialize_notification(
    notification: Notification,
    *,
    resolution: SourceResolution,
    now: datetime,
) -> dict:
    expired = notification.is_expired(now=now)
    href = ""
    if (
        notification.action_key
        and resolution.action_available
        and not expired
        and not notification.is_archived
    ):
        href = resolve_action_href(notification.action_key, notification.action_args)
    stale_action = bool(notification.action_key) and not href
    return {
        "id": str(notification.public_id),
        "type": notification.notification_type,
        "typeLabel": TYPE_LABELS.get(
            notification.notification_type, notification.notification_type
        ),
        "eventKey": notification.event_key,
        "title": notification.title,
        # Empty whenever the source declines: never a cached copy of a detail
        # the reader may no longer see.
        "detail": resolution.detail if resolution.available and not expired else "",
        "priority": PRIORITY_KEYS[notification.priority],
        "priorityLabel": PRIORITY_LABELS[notification.priority],
        "mandatory": notification.is_mandatory,
        "createdAt": notification.created_at.isoformat(),
        "availableAt": notification.available_at.isoformat(),
        "receivedLabel": received_label(notification, now=now),
        "expiresAt": notification.expires_at.isoformat()
        if notification.expires_at
        else None,
        "readAt": notification.read_at.isoformat() if notification.read_at else None,
        "archivedAt": notification.archived_at.isoformat()
        if notification.archived_at
        else None,
        "read": notification.is_read,
        "archived": notification.is_archived,
        "expired": expired,
        "action": {
            "label": action_label(notification.action_key),
            "href": href,
        }
        if href
        else None,
        "staleAction": stale_action,
        "staleActionNote": STALE_ACTION_NOTE if stale_action else "",
        "unavailableReason": ""
        if resolution.available and not expired
        else (
            "This notification has expired."
            if expired
            else resolution.unavailable_reason
        ),
    }


def serialize_page(user, rows: Sequence[Notification], *, now: datetime) -> list[dict]:
    """One batched source resolution for the whole page, then serialization."""
    resolutions = resolve_sources(user, rows)
    return [
        serialize_notification(
            row,
            resolution=resolutions.get(row.public_id, SourceResolution.unavailable()),
            now=now,
        )
        for row in rows
    ]
