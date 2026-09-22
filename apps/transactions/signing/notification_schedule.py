"""Scheduled signature reminders and stale-notification suppression.

Mirrors :mod:`apps.contract.notification_schedule`, but the cadence is keyed to
an individual ``SignaturePackageSigner`` rather than a contract: a package may
be waiting on one party while three others are already done. Beat tasks
re-check package status and signer eligibility immediately before publishing,
so a package that closed between runs stops nudging.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import Notification
from apps.transactions.models import SignaturePackage, SignaturePackageSigner
from apps.transactions.signing.lifecycle import (
    EVENT_SIGNATURE_REMINDER,
    is_signer_eligible,
    publish_package_event,
)
from apps.transactions.signing.tokens import issue_access_token
from apps.transactions.taxonomy import (
    ELIGIBLE_SIGNATURE_SIGNER_STATUSES,
    OPEN_SIGNATURE_PACKAGE_STATUSES,
    SignatureDeliveryMethod,
)

logger = logging.getLogger("apps.transactions")

SOURCE_MODULE = "transactions"
_REMINDER_EVENTS = frozenset({EVENT_SIGNATURE_REMINDER})

BATCH_LIMIT = 200


def _reminder_days() -> tuple[int, ...]:
    raw = getattr(settings, "TRANSACTION_SIGNATURE_REMINDER_DAYS", (3, 7, 14))
    return tuple(int(day) for day in raw if int(day) > 0)


def suppress_stale_reminders(package: SignaturePackage, *, now=None) -> int:
    """Expire unread reminders once a package stops accepting signatures."""
    if package.status in OPEN_SIGNATURE_PACKAGE_STATUSES:
        return 0
    moment = now or timezone.now()
    return (
        Notification.objects.filter(
            source_module=SOURCE_MODULE,
            source_record_id=str(package.public_id),
            event_key__in=_REMINDER_EVENTS,
            archived_at__isnull=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=moment))
        .update(expires_at=moment)
    )


def remind_signer(
    signer: SignaturePackageSigner, *, reminder_day: int = 0, notify: bool = True
) -> bool:
    """Publish one reminder for a signer who is still holding up a package.

    An email signer gets a freshly minted link, which retires the previous one:
    the newest message is always the working one. A ceremony already in flight
    on the old link has to be restarted from the new mail.
    """
    from apps.transactions.signing.emails import send_signer_reminder_email

    package = signer.package
    if package.status not in OPEN_SIGNATURE_PACKAGE_STATUSES:
        return False
    if signer.status not in ELIGIBLE_SIGNATURE_SIGNER_STATUSES:
        return False
    if not is_signer_eligible(package, signer):
        return False

    raw_token = ""
    if signer.delivery_method == SignatureDeliveryMethod.EMAIL:
        _token, raw_token = issue_access_token(signer)

    publish_package_event(
        EVENT_SIGNATURE_REMINDER,
        package,
        signer_id=str(signer.public_id),
        reminder_day=str(reminder_day),
    )
    if notify:
        send_signer_reminder_email(
            signer, raw_token=raw_token, reminder_day=reminder_day
        )
    return True


def publish_signature_reminders(*, as_of=None, notify: bool = True) -> int:
    """Emit one reminder per due cadence day for signers who owe a signature."""
    moment = as_of or timezone.now()
    published = 0
    for day in _reminder_days():
        # Inclusive calendar-day window around the cadence mark.
        window_start = moment - timedelta(days=day, hours=12)
        window_end = moment - timedelta(days=day) + timedelta(hours=12)
        due = (
            SignaturePackageSigner.objects.select_related(
                "package", "package__transaction"
            )
            .filter(
                status__in=ELIGIBLE_SIGNATURE_SIGNER_STATUSES,
                package__status__in=OPEN_SIGNATURE_PACKAGE_STATUSES,
                invited_at__gte=window_start,
                invited_at__lt=window_end,
            )
            .order_by("pk")[:BATCH_LIMIT]
        )
        for signer in due:
            if remind_signer(signer, reminder_day=day, notify=notify):
                published += 1
    if published:
        logger.info("transactions: signature reminders published=%s", published)
    return published


__all__ = [
    "publish_signature_reminders",
    "remind_signer",
    "suppress_stale_reminders",
]
