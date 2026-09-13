"""Release scheduled required training once its publish window opens.

``training.scheduled`` is explicit: nothing notifies yet. When ``publish_at``
arrives the row is already ``published``, so nothing in the workspace fires
again. This task emits the ``training.published`` event the first time the
window is open, and the existing producer fans out from there.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.audit.events import publish as publish_event
from apps.audit.models import DomainEvent
from apps.training.models import TrainingContent

logger = logging.getLogger("apps.training")


def release_scheduled_required_training(*, now=None) -> int:
    """Emit ``training.published`` for scheduled required rows now in window."""
    moment = now or timezone.now()
    scheduled_ids = {
        int(subject)
        for subject in DomainEvent.objects.filter(
            name="training.scheduled"
        ).values_list("subject", flat=True)
        if str(subject).isdigit()
    }
    already_published = {
        int(subject)
        for subject in DomainEvent.objects.filter(
            name="training.published"
        ).values_list("subject", flat=True)
        if str(subject).isdigit()
    }
    pending = scheduled_ids - already_published
    if not pending:
        return 0

    released = 0
    rows = (
        TrainingContent.objects.filter(pk__in=pending, is_required=True)
        .published()
        .within_window(now=moment)
        .select_related("owner_office")
        .order_by("pk")
    )
    for content in rows:
        publish_event(
            "training.published",
            actor_id="system",
            subject=str(content.pk),
            payload={
                "content_id": content.pk,
                "owner_office_id": content.owner_office.pk,
                "scope_level": content.scope_level,
                "status": content.status,
                "version_number": content.version_number,
                "version_family": str(content.version_family),
                "is_required": content.is_required,
                "occurred_at": moment.isoformat(),
            },
        )
        released += 1
    if released:
        logger.info("training.scheduled_released count=%s", released)
    return released
