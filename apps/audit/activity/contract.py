"""Stable activity timeline contract shared by API and Inertia embeds."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

ActorKind = Literal["user", "system", "service", "anonymous", "unknown"]
Visibility = Literal["full", "redacted", "summary"]


@dataclass(frozen=True)
class ActivityRecordRef:
    type: str
    id: str
    label: str = ""

    def to_payload(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id, "label": self.label}


@dataclass(frozen=True)
class ActivityFileRef:
    """Safe file pointer — never a permanent public URL."""

    id: str
    name: str
    content_type: str = ""

    def to_payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "contentType": self.content_type,
        }


@dataclass(frozen=True)
class ActivityEntry:
    id: str
    event_type: str
    summary: str
    occurred_at: datetime
    occurred_at_display: str
    actor_label: str
    actor_kind: ActorKind
    target: ActivityRecordRef
    source: str
    visibility: Visibility
    outcome: str = "success"
    reason: str = ""
    related: tuple[ActivityRecordRef, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    typed_action: str | None = None
    files: tuple[ActivityFileRef, ...] = ()
    change_summary: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "eventType": self.event_type,
            "summary": self.summary,
            "occurredAt": self.occurred_at.isoformat(),
            "occurredAtDisplay": self.occurred_at_display,
            "actorLabel": self.actor_label,
            "actorKind": self.actor_kind,
            "target": self.target.to_payload(),
            "related": [item.to_payload() for item in self.related],
            "source": self.source,
            "visibility": self.visibility,
            "outcome": self.outcome,
            "reason": self.reason,
            "metadata": self.metadata,
            "typedAction": self.typed_action,
            "files": [item.to_payload() for item in self.files],
            "changeSummary": list(self.change_summary),
        }


@dataclass(frozen=True)
class ActivityPage:
    entries: tuple[ActivityEntry, ...]
    next_cursor: str | None
    has_more: bool
    timezone: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "entries": [entry.to_payload() for entry in self.entries],
            "nextCursor": self.next_cursor,
            "hasMore": self.has_more,
            "timezone": self.timezone,
        }

    def __iter__(self):
        return iter(self.entries)


def entry_dict(entry: ActivityEntry) -> dict[str, Any]:
    payload = asdict(entry)
    payload["occurred_at"] = entry.occurred_at.isoformat()
    return payload
