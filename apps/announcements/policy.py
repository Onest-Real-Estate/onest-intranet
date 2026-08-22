"""How announcement priority becomes notification behaviour — and nothing else.

Priority is a *presentation and routing* signal. This adapter is the only
place it is allowed to influence delivery, and even here it decides two
things: whether the publish is worth interrupting someone for, and how the
resulting notification sorts. It never decides **who** receives one — that
comes from the announcement's audience scope, computed in
:mod:`apps.announcements.services` before this module is consulted.

Mapping to :class:`apps.notifications.contract.NotificationPriority` keeps one
scale across the hub: an urgent announcement and a critical contract deadline
sort against each other correctly in the notification centre instead of each
domain inventing its own numbering.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.announcements.taxonomy import (
    PRIORITY_IMPORTANT,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    resolve_priority,
)
from apps.notifications.contract import NotificationPriority, NotificationType


@dataclass(frozen=True)
class NotificationBehavior:
    """What publishing an announcement at one priority should do.

    ``notify`` false means the announcement lands in the feed and the
    dashboard band only. Routine news does not earn a badge increment; making
    every publish notify is how a notification centre stops being read.
    """

    notify: bool
    priority: int
    notification_type: str
    rationale: str


_BEHAVIORS: dict[str, NotificationBehavior] = {
    PRIORITY_URGENT: NotificationBehavior(
        notify=True,
        priority=NotificationPriority.CRITICAL,
        notification_type=NotificationType.ANNOUNCEMENT,
        rationale="Urgent notices need to reach people away from the hub.",
    ),
    PRIORITY_IMPORTANT: NotificationBehavior(
        notify=True,
        priority=NotificationPriority.HIGH,
        notification_type=NotificationType.ANNOUNCEMENT,
        rationale="Important news is worth a badge, not an interruption.",
    ),
    PRIORITY_NORMAL: NotificationBehavior(
        notify=False,
        priority=NotificationPriority.NORMAL,
        notification_type=NotificationType.ANNOUNCEMENT,
        rationale="Routine news is read in the feed, not pushed.",
    ),
}

#: Where an unknown stored code lands. Identical to the taxonomy fallback, so
#: a legacy row behaves like ``normal`` everywhere rather than one way in the
#: feed and another in notifications.
FALLBACK_BEHAVIOR: NotificationBehavior = _BEHAVIORS[PRIORITY_NORMAL]


def notification_behavior(priority_code: str | None) -> NotificationBehavior:
    """Never raises; unknown codes resolve through the taxonomy fallback."""
    return _BEHAVIORS.get(resolve_priority(priority_code).code, FALLBACK_BEHAVIOR)


def should_notify(priority_code: str | None) -> bool:
    return notification_behavior(priority_code).notify
