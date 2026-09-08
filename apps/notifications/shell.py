"""The header badge contract shared with every Inertia page.

One indexed count for the signed-in reader, computed per request and never
cached across users. It is intentionally the smallest possible payload: the
shell needs a number and a destination, not a preview of the inbox.
"""

from __future__ import annotations

from typing import TypedDict

from django.urls import reverse

from apps.notifications.service import unread_summary


class NotificationShell(TypedDict):
    unreadCount: int
    mandatoryCount: int
    href: str


def notification_shell_payload(user) -> NotificationShell | None:
    if not getattr(user, "is_authenticated", False):
        return None
    summary = unread_summary(user)
    return {
        "unreadCount": summary["unreadCount"],
        "mandatoryCount": summary["mandatoryCount"],
        "href": reverse("notifications"),
    }
