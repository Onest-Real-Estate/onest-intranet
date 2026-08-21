"""The email delivery pipeline: queue after commit, claim, revalidate, send.

The in-app notification is the domain fact. This module is the *ledger* for
pushing a copy of it out over email, and it is deliberately separate so that
nothing about a deferred, bounced, or abandoned email touches the notification
itself. A dead delivery leaves the reader's inbox exactly as it was.

Five guarantees live here:

* **After commit.** Rows are written inside the producing transaction and the
  worker is only told about them from ``transaction.on_commit``. A rolled-back
  workflow mails nobody.
* **At most one send.** ``(recipient, channel, delivery_key)`` is unique and
  ``delivery_key`` is the notification's own idempotency key, so a replayed
  event, a re-run fan-out chunk, and a duplicated task all converge on one row.
  The row is then *claimed* with a compare-and-set before the SMTP call, so two
  workers racing on the same row produce one send and one no-op.
* **Revalidated at the last moment.** Preferences, account state, the address
  itself, the notification's lifecycle, and the source domain's willingness to
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

from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import DateTimeField, F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, log_event, system_actor
from apps.notifications.categories import CHANNEL_EMAIL
from apps.notifications.emails import render_notification_email
from apps.notifications.models import Notification, NotificationEmail
from apps.notifications.preferences import channel_refusal, stored_choices_map
from apps.notifications.sources import resolve_sources
from apps.user.models import User

logger = logging.getLogger("apps.notifications")

#: Attempts before a delivery is given up on. Matches the domain-event
#: dispatcher so operators only have one retry story to remember.
MAX_ATTEMPTS = 5

#: Seconds to wait before attempt *n+1*. Longer than the event dispatcher's
#: because the failures this sees are mail-server failures, which are measured
#: in minutes rather than seconds.
_BACKOFF = (60, 300, 900, 3600, 10800)

#: How long a row may sit in ``sending`` before it is assumed the worker holding
#: it died. Long enough to cover a slow SMTP conversation, short enough that a
#: restart does not strand the message for a working day.
STALE_CLAIM = timedelta(minutes=15)

#: How many deliveries one dispatch task hands to the queue before passing the
#: rest to a fresh task.
DISPATCH_CHUNK_SIZE = 200

# Coarse, machine-readable reasons a message was never sent. None of them
# names a record: the ledger says *that* a delivery stopped, never what it
# would have been about.
SUPPRESSED_RECIPIENT_INACTIVE = "recipient_inactive"
SUPPRESSED_NO_ADDRESS = "no_email_address"
SUPPRESSED_INVALID_ADDRESS = "invalid_email_address"
SUPPRESSED_EXPIRED = "notification_expired"
SUPPRESSED_ARCHIVED = "notification_archived"
SUPPRESSED_ALREADY_READ = "already_read_in_app"
SUPPRESSED_SOURCE = "source_unavailable"
SUPPRESSED_MISSING = "notification_missing"


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
    """Write the ledger rows for a batch and schedule their dispatch.

    Every notification gets a row, including one that is already refused: the
    ledger is how "we deliberately did not email this person" is answerable
    later, and a silent skip is not. Only the rows that survive the pre-flight
    check are handed to the queue.

    Returns the public ids queued for dispatch. Safe to call twice — the
    unique constraint absorbs the duplicate rows and the second call queues
    nothing new.
    """
    rows = [row for row in notifications if row.pk]
    if not rows:
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
        reason = _preflight_reason(row, recipient, choices)
        pending.append(
            NotificationEmail(
                notification=row,
                recipient_id=row.recipient_id,
                channel=CHANNEL_EMAIL,
                delivery_key=row.dedupe_key,
                status=NotificationEmail.Status.SUPPRESSED
                if reason
                else NotificationEmail.Status.PENDING,
                suppression_reason=reason,
                queued_at=moment,
                resolved_at=moment if reason else None,
                # A notification scheduled for later is queued now and becomes
                # due then; nothing emails a reader about something their inbox
                # will not show for another week.
                next_attempt_at=max(row.available_at, moment),
            )
        )

    NotificationEmail.objects.bulk_create(pending, ignore_conflicts=True)

    # ``ignore_conflicts`` leaves the in-memory rows without primary keys, and
    # some of them may already have existed. Read back exactly the rows that
    # are ours to dispatch.
    queued = list(
        NotificationEmail.objects.filter(
            channel=CHANNEL_EMAIL,
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
            # Same outbox posture as the event publisher: a broker outage must
            # not fail the workflow that produced the notification. The rows
            # are committed as pending and the sweep picks them up.
            logger.exception("notifications.email_queue_failed count=%d", len(ids))

    transaction.on_commit(_enqueue)
    return ids


def _preflight_reason(
    notification: Notification,
    recipient: User | None,
    choices: dict[int, dict[str, dict[str, bool]]],
) -> str:
    """The cheap refusal, so a settled "no" never becomes a queued task.

    This is an optimisation, not the authority. :func:`send_reason` re-runs the
    same checks against fresh state immediately before the message is built.
    """
    if recipient is None or not recipient.is_active:
        return SUPPRESSED_RECIPIENT_INACTIVE
    if not recipient.email:
        return SUPPRESSED_NO_ADDRESS
    return channel_refusal(
        choices.get(recipient.pk, {}), notification, channel_key=CHANNEL_EMAIL
    )


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #


def send_reason(
    notification: Notification, recipient: User | None, *, now: datetime
) -> str:
    """Why this message must not go out now, or ``""`` when it may.

    Everything here can have changed since the row was queued, which is the
    whole point of checking it here rather than there: the account can have
    been disabled, the address changed, the notification read or archived in
    the hub, the preference switched off, or the source domain can have stopped
    vouching for the reader's access to the record it points at.
    """
    if recipient is None or not recipient.is_active:
        return SUPPRESSED_RECIPIENT_INACTIVE
    if not recipient.email:
        return SUPPRESSED_NO_ADDRESS
    try:
        validate_email(recipient.email)
    except ValidationError:
        return SUPPRESSED_INVALID_ADDRESS
    if notification.is_expired(now=now):
        return SUPPRESSED_EXPIRED
    if notification.archived_at is not None:
        return SUPPRESSED_ARCHIVED
    # A reminder about something the reader has already seen in the hub is
    # noise, and by the time a retry lands it is usually exactly that.
    if notification.read_at is not None:
        return SUPPRESSED_ALREADY_READ
    refusal = channel_refusal(
        stored_choices_map([recipient.pk]).get(recipient.pk, {}),
        notification,
        channel_key=CHANNEL_EMAIL,
    )
    if refusal:
        return refusal
    # The same authorization the notification centre applies on every read. A
    # grant withdrawn between queueing and sending stops the email too.
    resolution = resolve_sources(recipient, [notification]).get(notification.public_id)
    if resolution is None or not resolution.available:
        return SUPPRESSED_SOURCE
    return ""


def _claim(public_id, *, now: datetime) -> bool:
    """Compare-and-set the row into ``sending``, counting the attempt.

    The single write is what makes concurrent workers safe without holding a
    row lock across an SMTP conversation: exactly one of them updates a row,
    and the losers see zero rows affected and stop.
    """
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
    """Send one queued message. Returns the row's status afterwards.

    Never raises for an ordinary failure: the outcome is recorded on the row
    and the caller decides whether to reschedule. That is what keeps a mail
    outage from propagating back into the workflow that produced the
    notification.
    """
    moment = _now(now)
    email = NotificationEmail.objects.filter(public_id=public_id).first()
    if email is None:
        logger.warning("notifications.email_missing id=%s", public_id)
        return SUPPRESSED_MISSING
    if email.is_terminal:
        return email.status
    if email.next_attempt_at is not None and email.next_attempt_at > moment:
        # Scheduled for later, or backing off. The sweep will bring it back.
        return email.status
    if not _claim(public_id, now=moment):
        # Another worker holds it, or it settled between the read and the
        # claim. Either way this task is done.
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

    reason = send_reason(notification, recipient, now=moment)
    if reason:
        NotificationEmail.objects.filter(public_id=public_id).update(
            suppression_reason=reason
        )
        logger.info(
            "notifications.email_suppressed id=%s event=%s reason=%s",
            public_id,
            notification.event_key,
            reason,
        )
        return _resolve(public_id, now=moment)

    if recipient is None:  # pragma: no cover - send_reason already refused
        return _resolve(public_id, now=moment)
    try:
        _send_message(notification, recipient)
    except Exception as exc:
        return _record_failure(public_id, notification, exc, now=moment)

    NotificationEmail.objects.filter(public_id=public_id).update(
        status=NotificationEmail.Status.SENT,
        sent_at=moment,
        resolved_at=moment,
        to_email=recipient.email,
        last_error="",
        suppression_reason="",
    )
    logger.info(
        "notifications.email_sent id=%s event=%s type=%s",
        public_id,
        notification.event_key,
        notification.notification_type,
    )
    return NotificationEmail.Status.SENT


def _send_message(notification: Notification, recipient: User) -> None:
    rendered = render_notification_email(notification, recipient)
    message = EmailMultiAlternatives(
        subject=rendered.subject,
        body=rendered.text_body,
        to=[recipient.email],
        connection=get_connection(),
    )
    message.attach_alternative(rendered.html_body, "text/html")
    # ``fail_silently`` stays off: a send that quietly did nothing would settle
    # the row as sent and lose the message for good.
    message.send(fail_silently=False)


def _record_failure(
    public_id, notification: Notification, exc: Exception, *, now: datetime
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
            "notifications.email_dead id=%s event=%s attempts=%d error=%s",
            public_id,
            notification.event_key,
            attempts,
            error,
        )
        _audit_dead(public_id, notification, attempts=attempts, error=error)
        return NotificationEmail.Status.DEAD

    delay = _backoff(attempts)
    NotificationEmail.objects.filter(public_id=public_id).update(
        status=NotificationEmail.Status.FAILED,
        last_error=error,
        next_attempt_at=now + timedelta(seconds=delay),
    )
    logger.warning(
        "notifications.email_retry id=%s event=%s attempt=%d delay=%ds error=%s",
        public_id,
        notification.event_key,
        attempts,
        delay,
        error,
    )
    return NotificationEmail.Status.FAILED


def _audit_dead(
    public_id, notification: Notification, *, attempts: int, error: str
) -> None:
    """A terminal failure is an operational fact worth an audit row.

    Counts, keys, and the transport error only — never the address, the title,
    or anything the notification points at.
    """

    def _log() -> None:
        log_event(
            "notification.email.failed",
            actor=system_actor("notifications"),
            target=AuditTarget(
                target_type="notification.delivery",
                target_id=str(public_id),
                target_label=notification.event_key,
                target_snapshot={
                    "channel": CHANNEL_EMAIL,
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
    """Return rows abandoned mid-send to the retry queue.

    A worker killed between the claim and the outcome leaves the row in
    ``sending`` forever. The attempt it consumed still counts, so a repeatedly
    crashing worker exhausts the budget and the row dies rather than looping.
    """
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
    """Deliveries the queue should be holding but may not be.

    The database, not the broker, is the source of truth for outstanding work,
    so a lost task, a dropped queue, or a restarted worker costs a delay rather
    than a message.
    """
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
