"""Opaque keyset cursors for deterministic activity pagination."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID

from django.utils.dateparse import parse_datetime


class ActivityCursorError(ValueError):
    """Raised when a client cursor is malformed or tampered with."""


def encode_cursor(*, occurred_at: datetime, event_id: UUID | str) -> str:
    raw = f"{occurred_at.isoformat()}|{event_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    if not cursor or not isinstance(cursor, str):
        raise ActivityCursorError("Cursor is required.")
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = base64.urlsafe_b64decode(cursor + padding).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ActivityCursorError("Cursor is invalid.") from exc
    try:
        stamp, event_id = decoded.split("|", 1)
    except ValueError as exc:
        raise ActivityCursorError("Cursor is invalid.") from exc
    occurred_at = parse_datetime(stamp)
    if occurred_at is None:
        raise ActivityCursorError("Cursor timestamp is invalid.")
    try:
        UUID(str(event_id))
    except ValueError as exc:
        raise ActivityCursorError("Cursor id is invalid.") from exc
    return occurred_at, str(event_id)
