"""Serialization for the Inertia surface.

Every function here takes rows that have **already** passed ``for_reader`` /
``visible_replies`` / ``visible_attachments``. Nothing here filters, and
nothing here may start: a payload builder that could decide visibility is a
second authorization path, and the one in the queryset would stop being the
only one.

Keys are camelCase because Inertia props are; the stable machine codes travel
alongside their labels so the client never has to know how to spell a status.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.it_support.models import SupportTicket
from apps.it_support.taxonomy import (
    CATEGORY_LABELS,
    CONTACT_METHOD_LABELS,
    PRIORITY_KEYS,
    PRIORITY_LABELS,
    STATUS_LABELS,
    SupportPriority,
    SupportStatus,
)

#: Status → chip tone. Presentation lives here rather than in the taxonomy so a
#: design change never becomes a data migration.
STATUS_TONES: dict[str, str] = {
    SupportStatus.NEW: "info",
    SupportStatus.OPEN: "neutral",
    SupportStatus.IN_PROGRESS: "info",
    SupportStatus.WAITING_USER: "warning",
    SupportStatus.RESOLVED: "success",
    SupportStatus.CLOSED: "neutral",
}

PRIORITY_TONES: dict[int, str] = {
    SupportPriority.URGENT: "destructive",
    SupportPriority.HIGH: "warning",
    SupportPriority.NORMAL: "neutral",
    SupportPriority.LOW: "neutral",
}


def _person(user) -> dict[str, Any] | None:
    """Just enough to name somebody.

    Never an email: the queue is scoped by office, and a directory of
    addresses is a wider disclosure than the tickets themselves.
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


def ticket_row(ticket: SupportTicket) -> dict[str, Any]:
    """One row for the queue and the requester's own list."""
    return {
        "id": str(ticket.public_id),
        "reference": ticket.reference,
        "subject": ticket.subject,
        "category": {
            "code": ticket.category,
            "label": str(CATEGORY_LABELS.get(ticket.category, "Other")),
        },
        "status": status_badge(ticket.status),
        "priority": priority_badge(ticket.priority),
        "office": (
            {"id": ticket.office.pk, "name": ticket.office.name}
            if ticket.office
            else None
        ),
        "submitter": _person(ticket.submitter),
        "aboutUser": _person(ticket.about_user),
        "assignee": _person(ticket.assignee),
        "createdAt": ticket.created_at.isoformat(),
        "updatedAt": ticket.updated_at.isoformat(),
    }


def reply_payload(reply) -> dict[str, Any]:
    return {
        "id": str(reply.public_id),
        "author": _person(reply.author),
        "body": reply.body,
        "internal": reply.internal,
        "isResolution": reply.is_resolution,
        "createdAt": reply.created_at.isoformat(),
    }


def attachment_payload(attachment) -> dict[str, Any]:
    """No URL.

    Files live in private storage and are fetched through a view that
    re-authorizes the reader against the parent ticket. Serializing a storage
    path here would create the permanent link that arrangement prevents.
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


def ticket_detail(
    ticket: SupportTicket,
    *,
    replies,
    attachments,
    transitions,
    can_triage: bool,
) -> dict[str, Any]:
    payload = ticket_row(ticket)
    payload.update(
        {
            "description": ticket.description,
            "location": ticket.location,
            "preferredContact": {
                "code": ticket.preferred_contact,
                "label": str(
                    CONTACT_METHOD_LABELS.get(ticket.preferred_contact, "In the hub")
                ),
            },
            # Diagnostics are staff-only: they are of no use to the requester
            # and describe their machine, which is not something to echo back
            # onto a page somebody may screen-share.
            "deviceInfo": ticket.device_info if can_triage else "",
            "pageUrl": ticket.page_url if can_triage else "",
            "resolvedAt": (
                ticket.resolved_at.isoformat() if ticket.resolved_at else None
            ),
            "closedAt": ticket.closed_at.isoformat() if ticket.closed_at else None,
            "replies": [reply_payload(reply) for reply in replies],
            "attachments": [attachment_payload(item) for item in attachments],
            # Only the moves this actor may actually make. The service re-checks
            # every one, so this is a convenience and never the gate.
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
        "contactMethods": [
            {"value": code, "label": str(label)}
            for code, label in CONTACT_METHOD_LABELS.items()
        ],
    }


def queue_metrics(queryset, *, now=None) -> dict[str, int]:
    """The IT desk's own figures, counted inside the reader's scope.

    Every count runs on the already-scoped queryset, so a triager whose reach
    is one branch sees that branch's numbers rather than the brokerage's.
    """
    moment = now or timezone.now()
    return {
        "open": queryset.open().count(),
        "urgent": queryset.open().filter(priority=SupportPriority.URGENT).count(),
        "unassigned": queryset.unassigned().count(),
        "waitingUser": queryset.filter(status=SupportStatus.WAITING_USER).count(),
        "resolvedRecently": queryset.filter(
            status__in=(SupportStatus.RESOLVED, SupportStatus.CLOSED),
            resolved_at__isnull=False,
            resolved_at__gte=moment - timezone.timedelta(days=7),
        ).count(),
    }
