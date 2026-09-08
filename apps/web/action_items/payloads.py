"""Serialize ordered action items for Inertia (camelCase)."""

from __future__ import annotations

from datetime import datetime

from django.utils import formats, timezone

from apps.web.action_items.contract import (
    PRIORITY_KEYS,
    PRIORITY_LABELS,
    ActionItem,
)
from apps.web.action_items.ordering import is_overdue


def _due_label(item: ActionItem, *, now: datetime) -> str:
    if item.due_at is None:
        return "No due date"
    local = timezone.localtime(item.due_at)
    stamped = formats.date_format(local, "M j, Y")
    if is_overdue(item, now=now):
        return f"Overdue · {stamped}"
    return f"Due {stamped}"


def serialize_item(item: ActionItem, *, now: datetime) -> dict:
    overdue = is_overdue(item, now=now)
    return {
        "id": item.id,
        "dedupeKey": item.dedupe_key,
        "title": item.title,
        "type": item.type,
        "priority": PRIORITY_KEYS[item.priority],
        "priorityLabel": PRIORITY_LABELS[item.priority],
        "dueAt": item.due_at.isoformat() if item.due_at else None,
        "dueLabel": _due_label(item, now=now),
        "overdue": overdue,
        "state": item.state,
        "source": {
            "module": item.source_module,
            "recordType": item.source_record_type,
            "recordId": item.source_record_id,
        },
        "context": item.context,
        "ctaLabel": item.cta_label,
        "ctaHref": item.cta_href,
        "assigneeId": item.assignee_id,
    }


def serialize_queue(
    items: list[ActionItem],
    *,
    now: datetime,
    view_all_href: str,
) -> dict:
    return {
        "total": len(items),
        "items": [serialize_item(item, now=now) for item in items],
        "viewAllHref": view_all_href,
    }
