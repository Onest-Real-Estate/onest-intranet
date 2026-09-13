"""Scheduled policy acknowledgement reminders and stale-notification suppression."""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.audit.events import publish as publish_event
from apps.compliance.acknowledgements import (
    expire_ack_reminders,
    family_satisfaction_counts,
    overdue_requirements_for,
)
from apps.compliance.audience import recipients_for
from apps.compliance.models import PolicyRequirement, PolicyVersion

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
