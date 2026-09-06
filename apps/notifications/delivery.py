"""Outbound delivery pipeline: queue after commit, claim, revalidate, send.

The in-app notification is the domain fact. This module is the *ledger* for
pushing a copy of it out over one or more channels (email today; Microsoft
Graph, Slack, … when enabled). Providers live in
:mod:`apps.notifications.providers`; this file owns the shared queue, claim,
retry, and recovery mechanics so a new channel never rewrites them.

Five guarantees live here:

* **After commit.** Rows are written inside the producing transaction and the
  worker is only told about them from ``transaction.on_commit``. A rolled-back
  workflow notifies nobody.
* **At most one send per channel.** ``(recipient, channel, delivery_key)`` is
  unique and ``delivery_key`` is the notification's own idempotency key, so a
  replayed event, a re-run fan-out chunk, and a duplicated task all converge on
  one row per channel. The row is then *claimed* with a compare-and-set before
  the provider call, so two workers racing produce one send and one no-op.
* **Revalidated at the last moment.** Preferences, account state, the channel
  address, the notification's lifecycle, and the source domain's willingness to
  vouch for the reader are all re-checked immediately before the message is
  built — never trusted from when it was queued.
* **Bounded retries.** Attempts are counted on the row, backed off, and end in
  a terminal ``dead`` status with an audit event, not in an infinite queue.
* **Recoverable without a broker.** Every state transition is on the row, so
  :func:`due_delivery_ids` can rebuild the work queue from the database after a
  broker outage or a worker restart.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import DateTimeField, F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, log_event, system_actor
from apps.notifications.models import Notification, NotificationEmail
from apps.notifications.preferences import stored_choices_map
from apps.notifications.providers.email import (
    SUPPRESSED_ALREADY_READ,
    SUPPRESSED_ARCHIVED,
    SUPPRESSED_EXPIRED,
    SUPPRESSED_INVALID_ADDRESS,
    SUPPRESSED_NO_ADDRESS,
    SUPPRESSED_RECIPIENT_INACTIVE,
    SUPPRESSED_SOURCE,
)
from apps.notifications.providers.registry import enabled_providers, get_provider
from apps.user.models import User

# Re-export email suppression codes so existing tests and callers keep working.
__all_suppressed__ = (
    SUPPRESSED_ALREADY_READ,
    SUPPRESSED_ARCHIVED,
    SUPPRESSED_EXPIRED,
    SUPPRESSED_INVALID_ADDRESS,
    SUPPRESSED_NO_ADDRESS,
    SUPPRESSED_RECIPIENT_INACTIVE,
    SUPPRESSED_SOURCE,
)

logger = logging.getLogger("apps.notifications")

#: Attempts before a delivery is given up on. Matches the domain-event
#: dispatcher so operators only have one retry story to remember.
MAX_ATTEMPTS = 5

#: Seconds to wait before attempt *n+1*. Longer than the event dispatcher's
#: because the failures this sees are remote API failures, which are measured
#: in minutes rather than seconds.
_BACKOFF = (60, 300, 900, 3600, 10800)

#: How long a row may sit in ``sending`` before it is assumed the worker holding
#: it died. Long enough to cover a slow SMTP / Graph conversation, short enough
#: that a restart does not strand the message for a working day.
STALE_CLAIM = timedelta(minutes=15)

#: How many deliveries one dispatch task hands to the queue before passing the
#: rest to a fresh task.
DISPATCH_CHUNK_SIZE = 200

SUPPRESSED_MISSING = "notification_missing"
SUPPRESSED_UNKNOWN_CHANNEL = "unknown_channel"


def _now(now: datetime | None = None) -> datetime:
    return now or timezone.now()


def _backoff(attempt: int) -> int:
    return _BACKOFF[min(max(attempt - 1, 0), len(_BACKOFF) - 1)]


# --------------------------------------------------------------------------- #
# Queueing
# --------------------------------------------------------------------------- #


def queue_emails(
    notifications: Sequence[Notification], *, now: datetime | None = None
) -> list[str]:
    """Backward-compatible alias for :func:`queue_deliveries`."""
    return queue_deliveries(notifications, now=now)


def queue_deliveries(
    notifications: Sequence[Notification], *, now: datetime | None = None
) -> list[str]:
    """Write ledger rows for every enabled push provider and schedule dispatch.

    Every notification × enabled channel gets a row, including one that is
    already refused: the ledger is how "we deliberately did not deliver this"
    is answerable later. Only the rows that survive the pre-flight check are
    handed to the queue.

    Returns the public ids queued for dispatch. Safe to call twice — the
    unique constraint absorbs the duplicate rows and the second call queues
    nothing new.
    """
    rows = [row for row in notifications if row.pk]
    providers = enabled_providers()
    if not rows or not providers:
        return []
    moment = _now(now)

    recipients = {
        user.pk: user
        for user in User.objects.filter(pk__in={row.recipient_id for row in rows}).only(
            "id", "email", "is_active"
        )
    }
    choices = stored_choices_map(recipients.keys())

    pending: list[NotificationEmail] = []
    for row in rows:
        recipient = recipients.get(row.recipient_id)
        for provider in providers:
            reason = provider.preflight_refusal(
                row, recipient, choices.get(row.recipient_id, {})
            )
            pending.append(
                NotificationEmail(
                    notification=row,
                    recipient_id=row.recipient_id,
                    channel=provider.channel,
                    delivery_key=row.dedupe_key,
                    status=NotificationEmail.Status.SUPPRESSED
                    if reason
                    else NotificationEmail.Status.PENDING,
                    suppression_reason=reason,
                    queued_at=moment,
                    resolved_at=moment if reason else None,
                    next_attempt_at=max(row.available_at, moment),
                )
            )

    NotificationEmail.objects.bulk_create(pending, ignore_conflicts=True)

    channel_keys = [provider.channel for provider in providers]
    queued = list(
        NotificationEmail.objects.filter(
            channel__in=channel_keys,
            status=NotificationEmail.Status.PENDING,
            notification_id__in=[row.pk for row in rows],
        ).values_list("public_id", flat=True)
    )
    if not queued:
        return []

    ids = [str(value) for value in queued]

    def _enqueue() -> None:
        from apps.notifications.tasks import dispatch_notification_emails

        try:
            dispatch_notification_emails.delay(ids)
        except Exception:
            logger.exception("notifications.delivery_queue_failed count=%d", len(ids))

    transaction.on_commit(_enqueue)
    return ids


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #


def send_reason(
    notification: Notification, recipient: User | None, *, now: datetime
) -> str:
    """Why the *email* channel must not go out now, or ``""`` when it may.

    Kept for tests and callers that still reason about email specifically.
    Provider-aware sending uses :meth:`DeliveryProvider.send_refusal`.
    """
    provider = get_provider("email")
    if provider is None:
        return SUPPRESSED_UNKNOWN_CHANNEL
    return provider.send_refusal(notification, recipient, now=now)


def _claim(public_id, *, now: datetime) -> bool:
    """Compare-and-set the row into ``sending``, counting the attempt."""
    updated = (
        NotificationEmail.objects.filter(public_id=public_id)
        .filter(
            status__in=(
                NotificationEmail.Status.PENDING,
                NotificationEmail.Status.FAILED,
            )
        )
        .update(
            status=NotificationEmail.Status.SENDING,
            attempts=F("attempts") + 1,
            last_attempt_at=now,
            first_attempt_at=Coalesce(
                F("first_attempt_at"), Value(now, output_field=DateTimeField())
            ),
            next_attempt_at=None,
        )
    )
    return updated == 1


def _resolve(public_id, *, now: datetime) -> str:
    """Mark a claimed row suppressed for ``reason``."""
    NotificationEmail.objects.filter(public_id=public_id).update(
        status=NotificationEmail.Status.SUPPRESSED, resolved_at=now
    )
    return NotificationEmail.Status.SUPPRESSED


def attempt_delivery(public_id, *, now: datetime | None = None) -> str:
    """Send one queued message via its channel provider. Returns final status.

    Never raises for an ordinary failure: the outcome is recorded on the row
    and the caller decides whether to reschedule. That is what keeps a remote
    outage from propagating back into the workflow that produced the
    notification.
    """
    moment = _now(now)
    email = NotificationEmail.objects.filter(public_id=public_id).first()
    if email is None:
        logger.warning("notifications.delivery_missing id=%s", public_id)
        return SUPPRESSED_MISSING
    if email.is_terminal:
        return email.status
    if email.next_attempt_at is not None and email.next_attempt_at > moment:
        return email.status
    if not _claim(public_id, now=moment):
        return (
            NotificationEmail.objects.filter(public_id=public_id)
            .values_list("status", flat=True)
            .first()
            or NotificationEmail.Status.SENDING
        )

    notification = Notification.objects.filter(pk=email.notification_id).first()
    recipient = User.objects.filter(pk=email.recipient_id).first()
    if notification is None:
        NotificationEmail.objects.filter(public_id=public_id).update(
            suppression_reason=SUPPRESSED_MISSING
        )
        return _resolve(public_id, now=moment)

    provider = get_provider(email.channel)
    if provider is None or not provider.is_enabled():
        NotificationEmail.objects.filter(public_id=public_id).update(
            suppression_reason=SUPPRESSED_UNKNOWN_CHANNEL
        )
        logger.info(
            "notifications.delivery_suppressed id=%s channel=%s reason=%s",
            public_id,
            email.channel,
            SUPPRESSED_UNKNOWN_CHANNEL,
        )
        return _resolve(public_id, now=moment)

    reason = provider.send_refusal(notification, recipient, now=moment)
    if reason:
        NotificationEmail.objects.filter(public_id=public_id).update(
            suppression_reason=reason
        )
        logger.info(
            "notifications.delivery_suppressed id=%s channel=%s event=%s reason=%s",
            public_id,
            email.channel,
            notification.event_key,
            reason,
        )
        return _resolve(public_id, now=moment)

    if recipient is None:  # pragma: no cover - send_refusal already refused
        return _resolve(public_id, now=moment)
    try:
        result = provider.send(notification, recipient)
    except Exception as exc:
        return _record_failure(public_id, notification, email.channel, exc, now=moment)

    NotificationEmail.objects.filter(public_id=public_id).update(
        status=NotificationEmail.Status.SENT,
        sent_at=moment,
        resolved_at=moment,
        to_email=result.address[:254],
        last_error="",
        suppression_reason="",
    )
    logger.info(
        "notifications.delivery_sent id=%s channel=%s event=%s type=%s",
        public_id,
        email.channel,
        notification.event_key,
        notification.notification_type,
    )
    return NotificationEmail.Status.SENT


def _record_failure(
    public_id,
    notification: Notification,
    channel: str,
    exc: Exception,
    *,
    now: datetime,
) -> str:
    attempts = (
        NotificationEmail.objects.filter(public_id=public_id)
        .values_list("attempts", flat=True)
        .first()
        or 0
    )
    error = str(exc)[:2000]
    if attempts >= MAX_ATTEMPTS:
        NotificationEmail.objects.filter(public_id=public_id).update(
            status=NotificationEmail.Status.DEAD,
            last_error=error,
            next_attempt_at=None,
            resolved_at=now,
        )
        logger.error(
            "notifications.delivery_dead id=%s channel=%s event=%s "
            "attempts=%d error=%s",
            public_id,
            channel,
            notification.event_key,
            attempts,
            error,
        )
        _audit_dead(
            public_id, notification, channel=channel, attempts=attempts, error=error
        )
        return NotificationEmail.Status.DEAD

    delay = _backoff(attempts)
    NotificationEmail.objects.filter(public_id=public_id).update(
        status=NotificationEmail.Status.FAILED,
        last_error=error,
        next_attempt_at=now + timedelta(seconds=delay),
    )
    logger.warning(
        "notifications.delivery_retry id=%s channel=%s event=%s "
        "attempt=%d delay=%ds error=%s",
        public_id,
        channel,
        notification.event_key,
        attempts,
        delay,
        error,
    )
    return NotificationEmail.Status.FAILED


def _audit_dead(
    public_id,
    notification: Notification,
    *,
    channel: str,
    attempts: int,
    error: str,
) -> None:
    """A terminal failure is an operational fact worth an audit row."""

    def _log() -> None:
        log_event(
            "notification.email.failed",
            actor=system_actor("notifications"),
            target=AuditTarget(
                target_type="notification.delivery",
                target_id=str(public_id),
                target_label=notification.event_key,
                target_snapshot={
                    "channel": channel,
                    "eventKey": notification.event_key,
                    "notificationType": notification.notification_type,
                    "attempts": attempts,
                },
            ),
            outcome=AuditEvent.Outcome.FAILURE,
            reason=error[:200],
            source="worker",
            channel="notifications",
        )

    transaction.on_commit(_log)


# --------------------------------------------------------------------------- #
# Recovery
# --------------------------------------------------------------------------- #


def reclaim_stalled(*, now: datetime | None = None) -> int:
    """Return rows abandoned mid-send to the retry queue."""
    moment = _now(now)
    return NotificationEmail.objects.filter(
        status=NotificationEmail.Status.SENDING,
        last_attempt_at__lte=moment - STALE_CLAIM,
    ).update(
        status=NotificationEmail.Status.FAILED,
        next_attempt_at=moment,
        last_error="Worker stopped before the send completed.",
    )


def due_delivery_ids(
    *, now: datetime | None = None, limit: int = DISPATCH_CHUNK_SIZE
) -> list[str]:
    """Deliveries the queue should be holding but may not be."""
    moment = _now(now)
    due = Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=moment)
    rows = (
        NotificationEmail.objects.filter(
            status__in=(
                NotificationEmail.Status.PENDING,
                NotificationEmail.Status.FAILED,
            )
        )
        .filter(due)
        .order_by("next_attempt_at", "pk")
        .values_list("public_id", flat=True)[:limit]
    )
    return [str(value) for value in rows]
