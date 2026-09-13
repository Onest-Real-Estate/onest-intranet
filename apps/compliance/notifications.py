"""Policy notices, and the resolver that keeps them honest over time.

Publish fan-out and overdue reminders both point at a policy version. Detail
and the destination are re-derived on every inbox read through the same
audience + jurisdiction predicates the library uses.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from django.db.models import Q

from apps.audit.events import EventEnvelope
from apps.compliance.acknowledgements import user_ack_status
from apps.compliance.audience import recipients_for, visible_policies
from apps.compliance.models import (
    PolicyAcknowledgement,
    PolicyAcknowledgementWaiver,
    PolicyVersion,
)
from apps.compliance.services import apply_jurisdiction_visibility
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

SOURCE_MODULE = "compliance"
RECORD_TYPE = "policy_version"
PUBLISH_DEDUPE = "policy.published"
PUBLISH_EVENT = "policy.published"
REMINDER_EVENT = "policy.ack_reminder"


def _int_or_none(value: object) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number or None


def _is_live(version: PolicyVersion, *, now=None) -> bool:
    return (
        PolicyVersion.objects.filter(pk=version.pk)
        .filter(status=PolicyVersion.Status.PUBLISHED)
        .within_window(now=now)
        .exists()
    )


def _visible_recipient_ids(version: PolicyVersion, *, now=None) -> list[int]:
    """Audience members who also match the policy's jurisdiction right now."""
    candidates = recipients_for(version, at=now)
    codes = list(version.jurisdiction_state_codes or [])
    if codes:
        candidates = candidates.filter(
            Q(license_state__in=codes) | Q(office__state__in=codes)
        )
    acked = PolicyAcknowledgement.objects.filter(policy_version=version).values_list(
        "user_id", flat=True
    )
    waived = PolicyAcknowledgementWaiver.objects.filter(
        policy_version=version
    ).values_list("user_id", flat=True)
    excluded = set(acked) | set(waived)
    return [
        user_id
        for user_id in candidates.values_list("pk", flat=True)
        if user_id not in excluded
    ]


def _publish_requests(
    version: PolicyVersion, envelope: EventEnvelope
) -> list[NotificationRequest]:
    if not version.is_mandatory or not _is_live(version):
        return []
    excluded = set()
    actor_id = _int_or_none(envelope.actor_id)
    if actor_id is not None:
        excluded.add(actor_id)
    recipient_ids = [
        user_id
        for user_id in _visible_recipient_ids(version)
        if user_id not in excluded
    ]
    if not recipient_ids:
        return []
    dedupe = f"{PUBLISH_DEDUPE}:{version.pk}:{version.version_number}"
    return [
        NotificationRequest(
            recipient_id=recipient_id,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key=PUBLISH_EVENT,
            title="A required policy was published",
            dedupe_key=dedupe,
            priority=NotificationPriority.HIGH,
            is_mandatory=True,
            source_module=SOURCE_MODULE,
            source_record_type=RECORD_TYPE,
            source_record_id=str(version.pk),
            action_key="open_policy_detail",
            action_args=(version.pk,),
        )
        for recipient_id in recipient_ids
    ]


def requests_for_event(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Build publish notices for a live mandatory policy."""
    if envelope.name != PUBLISH_EVENT:
        return []
    if envelope.payload.get("is_mandatory") is False:
        return []
    policy_id = _int_or_none(envelope.payload.get("policy_id"))
    if policy_id is None:
        return []
    version = PolicyVersion.objects.filter(pk=policy_id).first()
    if version is None:
        return []
    return _publish_requests(version, envelope)


def resolve_compliance_notifications(
    user, notifications: Sequence
) -> dict[UUID, SourceResolution]:
    """Whether each notice still points at a policy this reader may open."""
    wanted = {
        int(record_id)
        for notification in notifications
        if (record_id := str(notification.source_record_id)).isdigit()
    }
    if not wanted:
        return {}
    versions = {
        row.pk: row
        for row in apply_jurisdiction_visibility(
            visible_policies(user).filter(pk__in=wanted), user
        )
    }
    resolved: dict[UUID, SourceResolution] = {}
    for notification in notifications:
        raw = str(notification.source_record_id)
        version = versions.get(int(raw)) if raw.isdigit() else None
        if version is None:
            resolved[notification.public_id] = SourceResolution.unavailable()
            continue
        event_key = str(getattr(notification, "event_key", "") or "")
        if event_key == REMINDER_EVENT:
            status = user_ack_status(user, version)
            if not status["required"]:
                resolved[notification.public_id] = SourceResolution.unavailable()
                continue
        resolved[notification.public_id] = SourceResolution(
            available=True,
            detail=version.title,
            action_available=True,
        )
    return resolved


if SOURCE_MODULE not in registered_modules():
    register_resolver(SOURCE_MODULE, resolve_compliance_notifications)
