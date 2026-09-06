"""Domain mappers: AuditEvent → ActivityEntry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.utils import timezone
from django.utils.formats import date_format

from apps.audit.activity.contract import (
    ActivityEntry,
    ActivityFileRef,
    ActivityRecordRef,
    ActorKind,
    Visibility,
)
from apps.audit.activity.redaction import scrub_metadata, summarize_changes
from apps.audit.models import AuditEvent

SYSTEM_ACTOR_LABEL = "System"
UNKNOWN_ACTOR_LABEL = "Unknown actor"
DELETED_TARGET_LABEL = "Deleted record"


@dataclass(frozen=True)
class DomainMapper:
    record_type: str
    action_labels: dict[str, str]
    typed_actions: dict[str, str]

    def label_for(self, action: str) -> str:
        if action in self.action_labels:
            return self.action_labels[action]
        leaf = action.rsplit(".", 1)[-1].replace("_", " ")
        return leaf[:1].upper() + leaf[1:] if leaf else action


def _display_timestamp(occurred_at: datetime) -> str:
    local = timezone.localtime(occurred_at)
    return date_format(local, "N j, Y, g:i A")


def _actor_kind(event: AuditEvent) -> ActorKind:
    mapping: dict[str, ActorKind] = {
        AuditEvent.ActorType.USER: "user",
        AuditEvent.ActorType.SYSTEM: "system",
        AuditEvent.ActorType.SERVICE: "service",
        AuditEvent.ActorType.ANONYMOUS: "anonymous",
    }
    return mapping.get(event.actor_type, "unknown")


def _actor_label(event: AuditEvent) -> str:
    kind = _actor_kind(event)
    label = (event.actor_label or "").strip()
    if kind == "system":
        return label or SYSTEM_ACTOR_LABEL
    if kind == "service":
        return label or "Service"
    if kind == "anonymous":
        return label or "Anonymous"
    if not label and not event.actor_id:
        return UNKNOWN_ACTOR_LABEL
    return label or UNKNOWN_ACTOR_LABEL


def _files_from_metadata(metadata: dict) -> tuple[ActivityFileRef, ...]:
    raw = metadata.get("files")
    if not isinstance(raw, list):
        single = metadata.get("file")
        raw = [single] if isinstance(single, dict) else []
    files: list[ActivityFileRef] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        file_id = str(item.get("id") or item.get("fileId") or "").strip()
        name = str(item.get("name") or item.get("fileName") or "").strip()
        if not file_id or not name:
            continue
        files.append(
            ActivityFileRef(
                id=file_id,
                name=name,
                content_type=str(
                    item.get("contentType") or item.get("content_type") or ""
                ),
            )
        )
    return tuple(files)


def _visibility_for(change_visibility: str) -> Visibility:
    if change_visibility == "full":
        return "full"
    if change_visibility == "redacted":
        return "redacted"
    return "summary"


def map_event(
    event: AuditEvent,
    *,
    viewer,
    record_type: str,
    record_id: str,
    mapper: DomainMapper,
) -> ActivityEntry:
    summary = mapper.label_for(event.action)
    typed = mapper.typed_actions.get(event.action)
    change_labels, safe_changes, change_visibility = summarize_changes(
        event.changes if isinstance(event.changes, dict) else {},
        viewer=viewer,
    )
    metadata = scrub_metadata(
        event.metadata if isinstance(event.metadata, dict) else {},
        viewer=viewer,
    )
    if safe_changes:
        metadata = {**metadata, "changes": safe_changes}
    if change_labels and change_visibility != "full":
        count = len(change_labels)
        summary = f"{summary} ({count} field{'s' if count != 1 else ''} changed)"

    target_label = (event.target_label or "").strip() or DELETED_TARGET_LABEL
    return ActivityEntry(
        id=str(event.id),
        event_type=event.action,
        summary=summary,
        occurred_at=event.occurred_at,
        occurred_at_display=_display_timestamp(event.occurred_at),
        actor_label=_actor_label(event),
        actor_kind=_actor_kind(event),
        target=ActivityRecordRef(
            type=record_type,
            id=str(record_id),
            label=target_label,
        ),
        source=event.source or "app",
        visibility=_visibility_for(change_visibility),
        outcome=event.outcome or AuditEvent.Outcome.SUCCESS,
        reason=event.reason or "",
        metadata=metadata,
        typed_action=typed,
        files=_files_from_metadata(metadata),
        change_summary=change_labels,
    )


USER_MAPPER = DomainMapper(
    record_type="user",
    action_labels={
        "user.administration.updated": "Administrative record updated",
        "user.license_verification.reset": "License verification reset",
        "user.account.disabled": "Account disabled",
        "user.account.reactivated": "Account reactivated",
        "user.onboarded": "Onboarding completed",
        "user.profile.updated": "Profile updated",
        "user.headshot.updated": "Headshot updated",
        "user.headshot.removed": "Headshot removed",
    },
    typed_actions={
        "user.account.disabled": "account.disable",
        "user.account.reactivated": "account.reactivate",
        "user.headshot.updated": "file.upload",
        "user.headshot.removed": "file.remove",
    },
)

CONTRACT_MAPPER = DomainMapper(
    record_type="contract",
    action_labels={
        "contract.created": "Contract created",
        "contract.issued": "Contract issued",
        "contract.signed": "Contract signed",
        "contract.activated": "Contract activated",
        "contract.superseded": "Contract superseded",
        "contract.terminated": "Contract terminated",
        "contract.expired": "Contract expired",
        "contract.updated": "Contract updated",
        "contract.cancelled": "Contract cancelled",
        "contract.submitted_for_review": "Contract submitted for review",
        "contract.reopened": "Contract reopened",
        "contract.viewed": "Contract viewed",
        "contract.generation_error": "Contract generation error",
        "contract.generation_retried": "Contract generation retried",
        "contract.pdf_generated": "Contract PDF generated",
        "contract.signed_pdf_generated": "Signed contract PDF generated",
        "contract.signed_pdf_generation_failed": (
            "Signed contract PDF generation failed"
        ),
        "contract.artifact.downloaded": "Contract artifact downloaded",
    },
    typed_actions={
        "contract.signed": "contract.sign",
        "contract.cancelled": "contract.cancel",
        "contract.issued": "contract.issue",
    },
)

TRANSACTION_MAPPER = DomainMapper(
    record_type="transaction",
    action_labels={
        "transaction.created": "Transaction opened",
        "transaction.updated": "Transaction updated",
        "transaction.closed": "Transaction closed",
        "transaction.cancelled": "Transaction cancelled",
    },
    typed_actions={
        "transaction.closed": "transaction.close",
        "transaction.cancelled": "transaction.cancel",
    },
)

LEAD_MAPPER = DomainMapper(
    record_type="lead",
    action_labels={
        "lead.created": "Lead created",
        "lead.updated": "Lead updated",
        "lead.assigned": "Lead assigned",
        "lead.closed": "Lead closed",
    },
    typed_actions={
        "lead.assigned": "lead.assign",
        "lead.closed": "lead.close",
    },
)

RESERVATION_MAPPER = DomainMapper(
    record_type="reservation",
    action_labels={
        "reservation.created": "Reservation recorded",
        "reservation.updated": "Reservation updated",
        "reservation.cancelled": "Reservation cancelled",
        "reservation.completed": "Reservation completed",
    },
    typed_actions={
        "reservation.cancelled": "reservation.cancel",
        "reservation.completed": "reservation.complete",
    },
)

SUPPORT_MAPPER = DomainMapper(
    record_type="support",
    action_labels={
        "support.ticket.created": "Support ticket opened",
        "support.ticket.updated": "Support ticket updated",
        "support.ticket.resolved": "Support ticket resolved",
        "support.ticket.closed": "Support ticket closed",
        "support.ticket.commented": "Comment added",
    },
    typed_actions={
        "support.ticket.resolved": "support.resolve",
        "support.ticket.closed": "support.close",
        "support.ticket.commented": "support.comment",
    },
)

MAPPERS: dict[str, DomainMapper] = {
    "user": USER_MAPPER,
    "contract": CONTRACT_MAPPER,
    "transaction": TRANSACTION_MAPPER,
    "lead": LEAD_MAPPER,
    "reservation": RESERVATION_MAPPER,
    "support": SUPPORT_MAPPER,
}


def mapper_for(record_type: str) -> DomainMapper:
    try:
        return MAPPERS[record_type]
    except KeyError as exc:
        raise KeyError(f"No activity mapper for record type {record_type!r}") from exc


def application_timezone() -> str:
    return getattr(settings, "TIME_ZONE", "UTC")
