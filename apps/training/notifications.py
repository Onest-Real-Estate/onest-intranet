"""Training assignment notices, and the resolver that keeps them honest.

Producers live behind the shared event consumer. This module builds the
requests and re-checks visibility on every inbox read so a revoked audience
selector or an expired window retires old rows without rewriting them.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from apps.audit.events import EventEnvelope
from apps.notifications.contract import (
    NotificationPriority,
    NotificationRequest,
    NotificationType,
)
from apps.notifications.sources import (
    SourceResolution,
    register_resolver,
    registered_modules,
)
from apps.training.audience import recipients_for, visible_training_content
from apps.training.models import TrainingContent, TrainingProgress
from apps.training.taxonomy import VERSION_POLICY_ANY

SOURCE_MODULE = "training"
RECORD_TYPE = "training_content"
ASSIGNMENT_DEDUPE = "training.assigned"

_ASSIGNMENT_EVENTS = frozenset(
    {
        "training.published",
        "training.required_changed",
    }
)


def _int_or_none(value: object) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number or None


def _is_live(content: TrainingContent, *, now=None) -> bool:
    return (
        TrainingContent.objects.filter(pk=content.pk)
        .published()
        .within_window(now=now)
        .exists()
    )


def _satisfied_user_ids(content: TrainingContent) -> set[int]:
    completed = TrainingProgress.objects.filter(
        status=TrainingProgress.Status.COMPLETED
    )
    if content.version_completion_policy == VERSION_POLICY_ANY:
        return set(
            completed.filter(
                content__version_family=content.version_family
            ).values_list("user_id", flat=True)
        )
    return set(completed.filter(content=content).values_list("user_id", flat=True))


def _assignment_requests(
    content: TrainingContent, envelope: EventEnvelope
) -> list[NotificationRequest]:
    if not content.is_required or not _is_live(content):
        return []
    excluded = _satisfied_user_ids(content)
    actor_id = _int_or_none(envelope.actor_id)
    if actor_id is not None:
        excluded.add(actor_id)
    recipient_ids = [
        user_id
        for user_id in recipients_for(content).values_list("pk", flat=True)
        if user_id not in excluded
    ]
    if not recipient_ids:
        return []
    dedupe = f"{ASSIGNMENT_DEDUPE}:{content.pk}:{content.version_number}"
    return [
        NotificationRequest(
            recipient_id=recipient_id,
            notification_type=NotificationType.TRAINING,
            event_key=envelope.name,
            title="Required training was assigned to you",
            dedupe_key=dedupe,
            priority=NotificationPriority.HIGH,
            source_module=SOURCE_MODULE,
            source_record_type=RECORD_TYPE,
            source_record_id=str(content.pk),
            action_key="open_training_detail",
            action_args=(content.pk,),
        )
        for recipient_id in recipient_ids
    ]


def requests_for_event(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Build assignment notices for a live required-training event."""
    if envelope.name == "training.required_changed" and not envelope.payload.get(
        "is_required"
    ):
        return []
    if envelope.name not in _ASSIGNMENT_EVENTS:
        return []
    content_id = _int_or_none(envelope.payload.get("content_id"))
    if content_id is None:
        return []
    content = TrainingContent.objects.filter(pk=content_id).first()
    if content is None:
        return []
    return _assignment_requests(content, envelope)


def resolve_training_notifications(
    user, notifications: Sequence
) -> dict[UUID, SourceResolution]:
    """Whether each notice still points at training this reader may open."""
    wanted = {
        int(record_id)
        for notification in notifications
        if (record_id := str(notification.source_record_id)).isdigit()
    }
    if not wanted:
        return {}
    visible = {
        row.pk: row for row in visible_training_content(user).filter(pk__in=wanted)
    }
    resolved: dict[UUID, SourceResolution] = {}
    for notification in notifications:
        raw = str(notification.source_record_id)
        content = visible.get(int(raw)) if raw.isdigit() else None
        if content is None:
            resolved[notification.public_id] = SourceResolution.unavailable()
            continue
        resolved[notification.public_id] = SourceResolution(
            available=True,
            detail=content.title,
            action_available=True,
        )
    return resolved


if SOURCE_MODULE not in registered_modules():
    register_resolver(SOURCE_MODULE, resolve_training_notifications)
