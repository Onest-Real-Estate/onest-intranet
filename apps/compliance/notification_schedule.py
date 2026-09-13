"""Release mandatory policy notices once the effective window opens.

Publish emits ``policy.published`` immediately. A future ``effective_at``
means the producer correctly delivers nobody. This task fans out the same
publish notice the first time the version is in window, using the same
dedupe key so a replay cannot double-notify.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.compliance.models import PolicyVersion
from apps.notifications.models import Notification
from apps.notifications.service import deliver_many

logger = logging.getLogger("apps.compliance")


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
