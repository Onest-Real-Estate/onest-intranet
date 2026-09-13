"""Publish fan-out for mandatory policies.

Overdue reminders are built in ``apps.notifications.producers.policy_ack_reminder``.
Read-time detail lives in ``apps.notifications.resolvers.resolve_compliance_policies``.
"""

from __future__ import annotations

from django.db.models import Q

from apps.audit.events import EventEnvelope
from apps.compliance.acknowledgements import family_satisfied_user_ids
from apps.compliance.audience import recipients_for
from apps.compliance.models import PolicyVersion
from apps.notifications.contract import (
    NotificationPriority,
    NotificationRequest,
    NotificationType,
)

SOURCE_MODULE = "compliance"
RECORD_TYPE = "policy_version"
PUBLISH_DEDUPE = "policy.published"
PUBLISH_EVENT = "policy.published"


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
    excluded = family_satisfied_user_ids(version)
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
