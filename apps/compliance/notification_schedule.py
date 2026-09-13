"""Scheduled compliance notification work.

Two jobs share this module:

* ``publish_ack_reminders`` emits ``policy.ack_reminder`` for overdue
  mandatory acknowledgements. The shared consumer turns those events into
  inbox rows.
* ``release_effective_mandatory_policies`` fans out the publish notice the
  first time a future ``effective_at`` window opens. Publish itself already
  emitted ``policy.published``; that producer correctly delivered nobody
  while the version was still invisible.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.audit.events import publish as publish_event
from apps.compliance.acknowledgements import (
    expire_ack_reminders,
    family_satisfaction_counts,
    overdue_requirements_for,
)
from apps.compliance.audience import recipients_for
from apps.compliance.models import PolicyRequirement, PolicyVersion
from apps.notifications.models import Notification
from apps.notifications.service import deliver_many

logger = logging.getLogger("apps.compliance")


def publish_ack_reminders(*, as_of=None) -> int:
    """Emit one reminder event per overdue mandatory acknowledgement."""
    moment = as_of or timezone.now()
    requirements = list(
        PolicyRequirement.objects.filter(
            is_active=True,
            due_at__isnull=False,
            due_at__lt=moment,
            policy_version__status=PolicyVersion.Status.PUBLISHED,
            policy_version__is_mandatory=True,
        )
        .select_related("policy_version")
        .order_by("pk")[:200]
    )
    published = 0
    for requirement in requirements:
        version = requirement.policy_version
        for user in (
            recipients_for(version).filter(is_active=True).iterator(chunk_size=100)
        ):
            if family_satisfaction_counts(user, version):
                expire_ack_reminders(user, version, now=moment)
                continue
            overdue = overdue_requirements_for(user, now=moment)
            if not any(row.pk == requirement.pk for row in overdue):
                continue
            publish_event(
                "policy.ack_reminder",
                actor_id="system",
                subject=f"policy:{version.pk}:{user.pk}",
                payload={
                    "policy_id": str(version.pk),
                    "recipient_id": str(user.pk),
                    "due_at": requirement.due_at.isoformat()
                    if requirement.due_at
                    else "",
                    "occurred_at": moment.isoformat(),
                },
            )
            published += 1
    if published:
        logger.info("compliance.ack_reminders published=%s", published)
    return published


def release_effective_mandatory_policies(*, now=None) -> int:
    """Deliver publish notices for mandatory policies that just became visible."""
    from apps.compliance.notifications import PUBLISH_EVENT, requests_for_event

    moment = now or timezone.now()
    already = set(
        Notification.objects.filter(
            event_key=PUBLISH_EVENT,
            source_module="compliance",
        ).values_list("source_record_id", flat=True)
    )
    versions = (
        PolicyVersion.objects.filter(
            status=PolicyVersion.Status.PUBLISHED,
            is_mandatory=True,
            effective_at__isnull=False,
            effective_at__lte=moment,
        )
        .within_window(now=moment)
        .exclude(pk__in=[int(pk) for pk in already if str(pk).isdigit()])
        .order_by("pk")[:200]
    )
    delivered = 0
    for version in versions:
        envelope = EventEnvelope(
            id=uuid4(),
            name=PUBLISH_EVENT,
            version=1,
            occurred_at=moment,
            actor_id="system",
            subject=str(version.pk),
            organization_id="",
            correlation_id=None,
            causation_id=None,
            payload={
                "policy_id": version.pk,
                "is_mandatory": True,
            },
        )
        created = deliver_many(requests_for_event(envelope), now=moment)
        delivered += created
    if delivered:
        logger.info("compliance.effective_released created=%s", delivered)
    return delivered
