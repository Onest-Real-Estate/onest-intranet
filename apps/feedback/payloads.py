"""Serialization for the Inertia surface.

Every function here receives rows that have already passed ``for_reader`` and
``visible_notes``. Nothing here filters, and nothing here may start: a payload
builder that could decide visibility would be a second authorization path, and
the one in the queryset would stop being the only one.

Note the absence of a screenshot URL. Files are fetched through a view that
re-authorizes on every request; serializing a storage path would create the
permanent link that arrangement exists to prevent.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from apps.feedback.models import FeedbackTicket
from apps.feedback.taxonomy import (
    CATEGORY_LABELS,
    PRIORITY_KEYS,
    PRIORITY_LABELS,
    STATUS_LABELS,
    URGENCY_LABELS,
    FeedbackPriority,
    FeedbackStatus,
)

#: Status → chip tone. Presentation lives here, not in the taxonomy, so a
#: design change never becomes a data migration.
STATUS_TONES: dict[str, str] = {
    FeedbackStatus.NEW: "info",
    FeedbackStatus.TRIAGED: "neutral",
    FeedbackStatus.IN_PROGRESS: "info",
    FeedbackStatus.NEEDS_INFO: "warning",
    FeedbackStatus.RESOLVED: "success",
    FeedbackStatus.CLOSED: "neutral",
}

PRIORITY_TONES: dict[int, str] = {
    FeedbackPriority.CRITICAL: "destructive",
    FeedbackPriority.HIGH: "warning",
    FeedbackPriority.NORMAL: "neutral",
    FeedbackPriority.LOW: "neutral",
}


def _person(user) -> dict[str, Any] | None:
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


def ticket_row(ticket: FeedbackTicket) -> dict[str, Any]:
    return {
        "id": str(ticket.public_id),
        "reference": ticket.reference,
        "summary": ticket.summary,
        "category": {
            "code": ticket.category,
            "label": str(CATEGORY_LABELS.get(ticket.category, "Other")),
        },
        "status": status_badge(ticket.status),
        "priority": priority_badge(ticket.priority),
        "urgency": {
            "code": ticket.urgency,
            "label": str(URGENCY_LABELS.get(ticket.urgency, "")),
        },
        "submitter": _person(ticket.submitter),
        "assignee": _person(ticket.assignee),
        "office": {"id": ticket.office.pk, "name": ticket.office.name}
        if ticket.office
        else None,
        "createdAt": ticket.created_at.isoformat(),
        "updatedAt": ticket.updated_at.isoformat(),
    }


def note_payload(note) -> dict[str, Any]:
    return {
        "id": str(note.public_id),
        "author": _person(note.author),
        "body": note.body,
        "internal": note.internal,
        "createdAt": note.created_at.isoformat(),
    }


def screenshot_payload(shot) -> dict[str, Any]:
    """Metadata plus a *route*, never a storage path.

    The href points at a view that re-checks the reader against the parent
    ticket. Nothing durable is handed out that could outlive their access.
    """
    return {
        "id": str(shot.public_id),
        "displayName": shot.display_name,
        "mediaType": shot.media_type,
        "byteSize": shot.byte_size,
        "width": shot.width,
        "height": shot.height,
        "href": reverse(
            "feedback_screenshot",
            args=[str(shot.ticket.public_id), str(shot.public_id)],
        ),
    }


def ticket_detail(
    ticket: FeedbackTicket,
    *,
    notes,
    screenshots,
    transitions,
    can_triage: bool,
) -> dict[str, Any]:
    payload = ticket_row(ticket)
    payload.update(
        {
            "description": ticket.description,
            "notes": [note_payload(note) for note in notes],
            "screenshots": [screenshot_payload(shot) for shot in screenshots],
            "transitions": [
                {
                    "target": move.target,
                    "label": str(move.label),
                    "requiresReply": move.requires_reply,
                    "tone": STATUS_TONES.get(move.target, "neutral"),
                }
                for move in transitions
            ],
            "resolvedAt": ticket.resolved_at.isoformat()
            if ticket.resolved_at
            else None,
            "closedAt": ticket.closed_at.isoformat() if ticket.closed_at else None,
            "convertedTaskId": ticket.converted_task_id,
        }
    )
    if can_triage:
        # The captured diagnostics are a triage tool, and they are shown only
        # to somebody who can act on them. They are already scrubbed, but there
        # is no reason for a bystander to read another person's page history.
        payload["diagnostics"] = {
            "pageUrl": ticket.page_url,
            "metadata": dict(ticket.browser_metadata or {}),
        }
    return payload


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
        "urgencies": [
            {"value": code, "label": str(label)}
            for code, label in URGENCY_LABELS.items()
        ],
    }
