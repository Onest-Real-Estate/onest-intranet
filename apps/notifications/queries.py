"""Reading the notification centre: filters, bounded pages, and nothing else.

Every query in this module starts from the signed-in reader. There is no code
path that takes a recipient identifier from the client, so "self-only" is not
a check that can be forgotten — it is the only way to build a queryset here.

Pagination is bounded by a fixed page size and a clamped page number: a reader
cannot ask for page 10,000 or a page of 5,000 rows, and every ordering the
page offers is backed by an index on ``(recipient, …, available_at)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.notifications.contract import (
    NOTIFICATION_TYPES,
    PRIORITY_BY_KEY,
    PRIORITY_KEYS,
    PRIORITY_LABELS,
    TYPE_LABELS,
)
from apps.notifications.models import Notification

PAGE_SIZE = 20

STATUS_UNREAD = "unread"
STATUS_ALL = "all"
STATUS_ARCHIVED = "archived"
STATUS_VALUES = (STATUS_UNREAD, STATUS_ALL, STATUS_ARCHIVED)
STATUS_LABELS = {
    STATUS_UNREAD: "Unread",
    STATUS_ALL: "All",
    STATUS_ARCHIVED: "Archived",
}


@dataclass(frozen=True)
class NotificationFilters:
    status: str = STATUS_UNREAD
    notification_type: str = ""
    priority: str = ""

    def as_payload(self) -> dict[str, str]:
        return {
            "status": self.status,
            "type": self.notification_type,
            "priority": self.priority,
        }

    @property
    def active_count(self) -> int:
        return sum(
            1
            for value in (
                self.status != STATUS_UNREAD,
                bool(self.notification_type),
                bool(self.priority),
            )
            if value
        )


@dataclass(frozen=True)
class NotificationPage:
    rows: list[Notification]
    page: int
    page_size: int
    total: int


def parse_filters(params) -> NotificationFilters:
    """Unknown values fall back to the default rather than erroring.

    A hand-edited query string is not worth a 400, and silently dropping an
    unrecognised filter keeps the page from ever showing a wider set than the
    reader asked for.
    """
    status = str(params.get("status", "")).strip()
    if status not in STATUS_VALUES:
        status = STATUS_UNREAD
    notification_type = str(params.get("type", "")).strip()
    if notification_type not in NOTIFICATION_TYPES:
        notification_type = ""
    priority = str(params.get("priority", "")).strip()
    if priority not in PRIORITY_BY_KEY:
        priority = ""
    return NotificationFilters(
        status=status, notification_type=notification_type, priority=priority
    )


def parse_page(params) -> int:
    try:
        return max(1, int(str(params.get("page", "1")).strip() or "1"))
    except ValueError:
        return 1


def filtered_queryset(user, filters: NotificationFilters, *, now: datetime):
    queryset = Notification.objects.for_recipient(user).released(now=now)
    if filters.status == STATUS_ARCHIVED:
        queryset = queryset.filter(archived_at__isnull=False)
    elif filters.status == STATUS_UNREAD:
        queryset = queryset.unexpired(now=now).filter(
            archived_at__isnull=True, read_at__isnull=True
        )
    else:
        queryset = queryset.filter(archived_at__isnull=True)
    if filters.notification_type:
        queryset = queryset.filter(notification_type=filters.notification_type)
    if filters.priority:
        queryset = queryset.filter(priority=PRIORITY_BY_KEY[filters.priority])
    return queryset.order_by("-available_at", "-pk")


def build_page(
    user,
    *,
    filters: NotificationFilters,
    page: int,
    now: datetime | None = None,
) -> NotificationPage:
    moment = now or timezone.now()
    queryset = filtered_queryset(user, filters, now=moment)
    total = queryset.count()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * PAGE_SIZE
    rows = list(queryset[start : start + PAGE_SIZE])
    return NotificationPage(rows=rows, page=current, page_size=PAGE_SIZE, total=total)


def status_options() -> list[dict[str, str]]:
    return [{"value": value, "label": STATUS_LABELS[value]} for value in STATUS_VALUES]


def type_options() -> list[dict[str, str]]:
    return [
        {"value": value, "label": label} for value, label in sorted(TYPE_LABELS.items())
    ]


def priority_options() -> list[dict[str, str]]:
    return [
        {"value": PRIORITY_KEYS[value], "label": PRIORITY_LABELS[value]}
        for value in sorted(PRIORITY_KEYS)
    ]
