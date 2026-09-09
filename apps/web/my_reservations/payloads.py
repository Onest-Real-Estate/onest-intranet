"""Inertia serialization for the unified reservation feed.

Times cross as instants plus the zone they must be read in; the page formats
them. All-day rows also carry their local date, which is the only honest way to
render a pickup window that has no clock time.
"""

from __future__ import annotations

from typing import Any

from apps.web.my_reservations.contract import (
    DISPLAY_STATUS_LABELS,
    DISPLAY_STATUS_TONES,
    SOURCE_LABELS,
    ReservationAction,
    ReservationSummary,
)


def serialize_action(action: ReservationAction) -> dict[str, Any]:
    return {
        "key": action.key,
        "label": action.label,
        "href": action.href,
        "method": action.method,
        "destructive": action.destructive,
        "expectedStatus": action.expected_status,
    }


def serialize_summary(summary: ReservationSummary) -> dict[str, Any]:
    return {
        "sourceId": summary.source_id,
        "source": summary.source,
        "sourceLabel": str(SOURCE_LABELS[summary.source]),
        "publicId": summary.public_id,
        "reference": summary.reference,
        "title": summary.title,
        "subtitle": summary.subtitle,
        "officeName": summary.office_name,
        "timezone": summary.timezone,
        "startsAt": summary.starts_at.isoformat(),
        "endsAt": summary.ends_at.isoformat(),
        "allDay": summary.all_day,
        "localDate": summary.local_date.isoformat() if summary.local_date else None,
        "displayStatus": summary.display_status,
        "displayStatusLabel": str(DISPLAY_STATUS_LABELS[summary.display_status]),
        "tone": DISPLAY_STATUS_TONES[summary.display_status],
        # The domain's own words travel with the row so the reader is never
        # shown only a flattened status.
        "sourceStatus": summary.source_status,
        "statusLabel": summary.status_label,
        "purpose": summary.purpose,
        "quantity": summary.quantity,
        "instructions": summary.instructions,
        "contact": summary.contact,
        "detailHref": summary.detail_href,
        "actions": [serialize_action(action) for action in summary.actions],
    }
