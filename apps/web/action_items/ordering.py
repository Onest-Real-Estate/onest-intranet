"""Deterministic merge of action-item rows from every registered source."""

from __future__ import annotations

from datetime import datetime

from apps.web.action_items.contract import ActionItem


def is_overdue(item: ActionItem, *, now: datetime) -> bool:
    return item.due_at is not None and item.due_at < now


def sort_key(item: ActionItem, *, now: datetime) -> tuple:
    """Overdue first, then priority, due time, stable id.

    Items without a due date sort after dated peers at the same priority so a
    timeless nudge never hides a dated deadline.
    """
    overdue = 0 if is_overdue(item, now=now) else 1
    due = item.due_at or datetime.max.replace(tzinfo=now.tzinfo)
    return (overdue, item.priority, due, item.id)


def dedupe(items: list[ActionItem]) -> list[ActionItem]:
    """Keep the first occurrence of each dedupe key after callers sort.

    Sources that race to describe the same required action collapse to one
    row. Deterministic input order makes the survivor stable.
    """
    seen: set[str] = set()
    unique: list[ActionItem] = []
    for item in items:
        if item.dedupe_key in seen:
            continue
        seen.add(item.dedupe_key)
        unique.append(item)
    return unique


def order_items(items: list[ActionItem], *, now: datetime) -> list[ActionItem]:
    ordered = sorted(items, key=lambda item: sort_key(item, now=now))
    return dedupe(ordered)
