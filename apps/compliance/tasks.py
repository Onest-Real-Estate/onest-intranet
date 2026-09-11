"""Celery tasks for compliance acknowledgement reminders."""

from __future__ import annotations

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.notifications.contract import (
    NotificationPriority,
    NotificationRequest,
    NotificationType,
)
from apps.notifications.service import deliver


@shared_task
def send_policy_ack_reminders() -> int:
    """Remind users with overdue mandatory acknowledgements.

    Idempotent via notification ``dedupe_key`` per user+policy+due date.
    """
    from apps.compliance.acknowledgements import overdue_requirements_for
    from apps.compliance.audience import recipients_for
    from apps.compliance.models import (
        PolicyAcknowledgement,
        PolicyAcknowledgementWaiver,
        PolicyRequirement,
        PolicyVersion,
    )

    moment = timezone.now()
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
    delivered = 0
    for requirement in requirements:
        version = requirement.policy_version
        due_key = (
            requirement.due_at.date().isoformat() if requirement.due_at else "none"
        )
        candidates = recipients_for(version).filter(is_active=True)
        acked_ids = set(
            PolicyAcknowledgement.objects.filter(policy_version=version).values_list(
                "user_id", flat=True
            )
        )
        waived_ids = set(
            PolicyAcknowledgementWaiver.objects.filter(
                policy_version=version
            ).values_list("user_id", flat=True)
        )
        for user in candidates.exclude(
            Q(pk__in=acked_ids) | Q(pk__in=waived_ids)
        ).iterator(chunk_size=100):
            overdue = overdue_requirements_for(user, now=moment)
            if not any(row.pk == requirement.pk for row in overdue):
                continue
            row = deliver(
                NotificationRequest(
                    recipient_id=user.pk,
                    notification_type=NotificationType.ADMINISTRATIVE,
                    event_key="policy.ack_reminder",
                    title="A required policy acknowledgement is overdue",
                    dedupe_key=f"policy-ack-reminder:{version.pk}:{user.pk}:{due_key}",
                    priority=NotificationPriority.HIGH,
                    is_mandatory=True,
                    action_key="open_policy_detail",
                    action_args=(version.pk,),
                ),
                now=moment,
            )
            if row is not None:
                delivered += 1
    return delivered
