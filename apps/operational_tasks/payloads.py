"""Serialization for the Inertia surface.

Every function here takes rows that have **already** passed
``for_reader``/``visible_comments``. Nothing in this module filters, and
nothing here may start: a payload builder that could decide visibility is a
second authorization path, and the one in the queryset would stop being the
only one.

Keys are camelCase because Inertia props are; the stable machine codes travel
alongside their labels so the client never has to know how to spell a status.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.operational_tasks.models import OperationalTask
from apps.operational_tasks.taxonomy import (
    BOARD_STATUSES,
    CATEGORY_LABELS,
    PRIORITY_KEYS,
    PRIORITY_LABELS,
    STATUS_LABELS,
    TaskPriority,
    TaskStatus,
)

#: Status → chip tone. Presentation lives here rather than in the taxonomy so a
#: design change never becomes a data migration, and it is a plain map rather
#: than a class name so the frontend keeps its own token vocabulary.
STATUS_TONES: dict[str, str] = {
    TaskStatus.OPEN: "neutral",
    TaskStatus.IN_PROGRESS: "info",
    TaskStatus.BLOCKED: "destructive",
    TaskStatus.WAITING: "warning",
    TaskStatus.RESOLVED: "success",
    TaskStatus.CLOSED: "neutral",
    TaskStatus.CANCELLED: "neutral",
}

PRIORITY_TONES: dict[int, str] = {
    TaskPriority.CRITICAL: "destructive",
    TaskPriority.HIGH: "warning",
    TaskPriority.NORMAL: "neutral",
    TaskPriority.LOW: "neutral",
}


def _person(user) -> dict[str, Any] | None:
    """Just enough to name somebody.

    Never an email: the task surface is scoped by office, and a directory of
    addresses is a wider disclosure than the task itself.
    """
    if user is None:
        return None
    return {"id": user.pk, "name": user.get_full_name() or user.get_short_name()}


def status_badge(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "label": str(STATUS_LABELS.get(code, code)),
        "tone": STATUS_TONES.get(code, "neutral"),
        "known": code in STATUS_LABELS,
    }


def priority_badge(rank: int) -> dict[str, Any]:
    return {
        "code": PRIORITY_KEYS.get(rank, "normal"),
        "label": str(PRIORITY_LABELS.get(rank, "Normal")),
        "tone": PRIORITY_TONES.get(rank, "neutral"),
        "rank": rank,
    }


def task_row(task: OperationalTask, *, now=None) -> dict[str, Any]:
    """One row for the list and the board."""
    moment = now or timezone.now()
    return {
        "id": str(task.public_id),
        "reference": task.reference,
        "title": task.title,
        "category": {
            "code": task.category,
            "label": str(CATEGORY_LABELS.get(task.category, "Uncategorized")),
        },
        "status": status_badge(task.status),
        "priority": priority_badge(task.priority),
        "office": {"id": task.office.pk, "name": task.office.name},
        "assignee": _person(task.assignee),
        "team": task.team,
        "dueAt": task.due_at.isoformat() if task.due_at else None,
        "isOverdue": task.is_overdue(at=moment),
        "source": task.source,
        "tags": list(task.tags or []),
        "createdAt": task.created_at.isoformat(),
        "updatedAt": task.updated_at.isoformat(),
    }


def comment_payload(comment) -> dict[str, Any]:
    return {
        "id": str(comment.public_id),
        "author": _person(comment.author),
        "body": comment.body,
        "internal": comment.internal,
        "createdAt": comment.created_at.isoformat(),
    }


def attachment_payload(attachment) -> dict[str, Any]:
    """No URL.

    Files live in private storage and are fetched through a view that
    re-authorizes the reader against the parent task. Serializing a storage
    path here would create the permanent link that arrangement exists to
    prevent.
    """
    return {
        "id": str(attachment.public_id),
        "displayName": attachment.display_name,
        "mediaType": attachment.media_type,
        "byteSize": attachment.byte_size,
        "internal": attachment.internal,
        "uploadedBy": _person(attachment.uploaded_by),
        "createdAt": attachment.created_at.isoformat(),
    }


def task_detail(
    task: OperationalTask, *, comments, attachments, transitions, now=None
) -> dict[str, Any]:
    payload = task_row(task, now=now)
    payload.update(
        {
            "description": task.description,
            "reporter": _person(task.reporter),
            "sourceReference": task.source_reference,
            "relatedObject": (
                {"type": task.related_object_type, "id": task.related_object_id}
                if task.related_object_type
                else None
            ),
            "startedAt": task.started_at.isoformat() if task.started_at else None,
            "resolvedAt": task.resolved_at.isoformat() if task.resolved_at else None,
            "closedAt": task.closed_at.isoformat() if task.closed_at else None,
            "comments": [comment_payload(c) for c in comments],
            "attachments": [attachment_payload(a) for a in attachments],
            # Only the moves this actor may actually make. The service re-checks
            # every one of them, so this is a convenience and never the gate.
            "transitions": [
                {
                    "target": move.target,
                    "label": str(move.label),
                    "requiresNote": move.requires_note,
                    "tone": STATUS_TONES.get(move.target, "neutral"),
                }
                for move in transitions
            ],
        }
    )
    return payload


def board_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group rows into the board's fixed columns.

    Grouped server-side so the column order, the empty columns, and the counts
    are the same fact the list page is reading — a client-side ``groupBy`` would
    silently drop a status the server knows about.
    """
    by_status: dict[str, list[dict[str, Any]]] = {
        status: [] for status in BOARD_STATUSES
    }
    for row in rows:
        code = row["status"]["code"]
        if code in by_status:
            by_status[code].append(row)
    return [
        {
            "status": status_badge(status),
            "items": by_status[status],
            "count": len(by_status[status]),
        }
        for status in BOARD_STATUSES
    ]


def filter_options() -> dict[str, list[dict[str, str]]]:
    return {
        "statuses": [
            {"value": code, "label": str(label)}
            for code, label in STATUS_LABELS.items()
        ],
        "categories": [
            {"value": code, "label": str(label)}
            for code, label in CATEGORY_LABELS.items()
        ],
        "priorities": [
            {"value": PRIORITY_KEYS[rank], "label": str(label)}
            for rank, label in PRIORITY_LABELS.items()
        ],
    }
