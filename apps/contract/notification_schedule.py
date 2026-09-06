"""Scheduled contract reminders and stale-notification suppression.

Beat tasks re-check status, version, recipient, and permission immediately
before publishing. Lifecycle transitions that leave a contract unsignable
expire outstanding signature-reminder rows so the centre and email ledger stop
pushing them.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.audit.events import publish as publish_event
from apps.contract.models import AgentContract
from apps.contract.statuses import ContractStatus
from apps.notifications.models import Notification

logger = logging.getLogger("apps.contract")

SIGNABLE = frozenset({ContractStatus.SENT, ContractStatus.VIEWED})
_REMINDER_EVENTS = frozenset(
    {
        "contract.signature_reminder",
    }
)


def _reminder_days() -> tuple[int, ...]:
    raw = getattr(settings, "CONTRACT_SIGNATURE_REMINDER_DAYS", (3, 7, 14))
    return tuple(int(day) for day in raw if int(day) > 0)


def _warning_days() -> tuple[int, ...]:
    raw = getattr(settings, "CONTRACT_EXPIRATION_WARNING_DAYS", (30, 14, 7))
    return tuple(int(day) for day in raw if int(day) > 0)


def suppress_stale_reminders(contract: AgentContract, *, now=None) -> int:
    """Expire unread signature reminders once the contract is no longer signable."""
    if contract.status in SIGNABLE and contract.generated_pdf_id:
        return 0
    moment = now or timezone.now()
    contract_id = str(contract.public_id)
    return (
        Notification.objects.filter(
            source_module="contract",
            source_record_id=contract_id,
            event_key__in=_REMINDER_EVENTS,
            archived_at__isnull=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=moment))
        .update(expires_at=moment)
    )


def publish_signature_reminders(*, as_of=None) -> int:
    """Emit one reminder event per due cadence day for still-signable contracts."""
    moment = as_of or timezone.now()
    published = 0
    for day in _reminder_days():
        # Inclusive calendar-day window around the cadence mark.
        window_start = moment - timedelta(days=day, hours=12)
        window_end = moment - timedelta(days=day) + timedelta(hours=12)
        due = (
            AgentContract.objects.select_related("office", "recipient")
            .filter(
                status__in=SIGNABLE,
                generated_pdf_id__isnull=False,
                sent_at__gte=window_start,
                sent_at__lt=window_end,
            )
            .exclude(recipient_id=None)
            .order_by("pk")[:200]
        )
        for contract in due:
            if contract.status not in SIGNABLE or not contract.generated_pdf_id:
                continue
            publish_event(
                "contract.signature_reminder",
                actor_id="system",
                subject=str(contract.public_id),
                payload={
                    "contract_id": str(contract.public_id),
                    "office_id": str(contract.office_id),
                    "agent_id": str(contract.recipient_id),
                    "reminder_day": str(day),
                    "occurred_at": moment.isoformat(),
                },
            )
            published += 1
    if published:
        logger.info("contract.signature_reminders published=%s", published)
    return published


def publish_expiration_warnings(*, as_of: date | None = None) -> int:
    """Emit warnings for active contracts approaching ``expires_on``."""
    today = as_of or timezone.localdate()
    published = 0
    for day in _warning_days():
        target = today + timedelta(days=day)
        due = (
            AgentContract.objects.select_related("office", "recipient")
            .filter(
                status=ContractStatus.ACTIVE,
                expires_on=target,
            )
            .exclude(recipient_id=None)
            .order_by("pk")[:200]
        )
        for contract in due:
            if contract.status != ContractStatus.ACTIVE:
                continue
            publish_event(
                "contract.expiration_warning",
                actor_id="system",
                subject=str(contract.public_id),
                payload={
                    "contract_id": str(contract.public_id),
                    "office_id": str(contract.office_id),
                    "agent_id": str(contract.recipient_id),
                    "warning_day": str(day),
                    "occurred_at": timezone.now().isoformat(),
                },
            )
            published += 1
    if published:
        logger.info("contract.expiration_warnings published=%s", published)
    return published
