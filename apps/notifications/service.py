"""Producer and reader service for in-app notifications.

Nothing outside this module writes a :class:`~apps.notifications.models.
Notification`. Producers describe a delivery; this module decides whether it
may exist, and readers mutate only their own state through the helpers here.

Four guarantees live in this file:

* **Idempotency.** ``(recipient, dedupe_key)`` is unique in the database, and
  every write goes through ``get_or_create`` or ``bulk_create(ignore_conflicts)``.
  A replayed domain event, a retried Celery task, and a double-clicked button
  all converge on one row.
* **Self-only mutation.** Every mutation is filtered by recipient before it
  touches anything. An id belonging to somebody else is indistinguishable from
  an id that does not exist.
* **Correct counts under concurrency.** Read state is changed with a filtered
  ``UPDATE``, never a read-modify-write, and counts are always computed from
  the database. Two tabs marking the same row read cannot double-count.
* **Source authorization at delivery.** A notification is only created if the
  source domain will vouch for the recipient's access to the record *now*;
  :mod:`apps.notifications.sources` re-checks it on every later read.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, Count, Q, When
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, log_event, system_actor
from apps.notifications.actions import validate_action_args
from apps.notifications.contract import (
    NotificationRequest,
)
from apps.notifications.models import Notification
from apps.notifications.sources import SELF_CONTAINED, resolve_sources
from apps.user.models import User

logger = logging.getLogger("apps.notifications")

#: How many recipients one background fan-out task writes before handing the
#: rest to a fresh task. Bounded so no single worker holds thousands of rows
#: open, and no single request ever writes an audience at all.
FAN_OUT_CHUNK_SIZE = 250


class MandatoryAcknowledgementRequired(ValidationError):
    """A mandatory notification cannot be archived while it is unread."""


def _now(now: datetime | None = None) -> datetime:
    return now or timezone.now()


def _to_instance(request: NotificationRequest, *, now: datetime) -> Notification:
    return Notification(
        recipient_id=request.recipient_id,
        notification_type=request.notification_type,
        event_key=request.event_key.strip()[:120],
        title=request.clean_title,
        priority=request.priority,
        is_mandatory=request.is_mandatory,
        source_module=request.source_module[:64],
        source_record_type=request.source_record_type[:64],
        source_record_id=str(request.source_record_id)[:64],
        action_key=request.action_key,
        action_args=list(validate_action_args(request.action_key, request.action_args))
        if request.action_key
        else [],
        dedupe_key=request.clean_dedupe_key,
        created_at=now,
        available_at=request.available_at or now,
        expires_at=request.expires_at,
    )


def _dead_on_arrival(instance: Notification, moment: datetime) -> bool:
    """Whether a delivery would arrive already expired.

    Two ways to be born dead: an expiry that has passed, and an expiry that
    lands before the row is even scheduled to appear. Both are producer bugs
    worth dropping rather than storing.
    """
    if instance.expires_at is None:
        return False
    return instance.expires_at <= moment or instance.expires_at <= instance.available_at


def _source_permits(instance: Notification, recipient: User) -> bool:
    """Whether the source domain vouches for this recipient's access today.

    An unsaved instance is enough — resolvers read provenance fields only, and
    checking before the insert means an unauthorized delivery never exists.
    """
    if not instance.source_module:
        return SELF_CONTAINED.available
    resolution = resolve_sources(recipient, [instance]).get(instance.public_id)
    return bool(resolution and resolution.available)


def deliver(
    request: NotificationRequest, *, now: datetime | None = None
) -> Notification | None:
    """Create one notification, or return ``None`` if it must not exist.

    Returns the existing row unchanged when the idempotency key has already
    been delivered — a producer replay is a no-op, not an update.
    """
    moment = _now(now)
    recipient = User.objects.filter(pk=request.recipient_id, is_active=True).first()
    if recipient is None:
        logger.info(
            "notifications.rejected reason=recipient_unavailable event=%s",
            request.event_key,
        )
        return None
    instance = _to_instance(request, now=moment)
    if _dead_on_arrival(instance, moment):
        logger.info(
            "notifications.rejected reason=already_expired event=%s", request.event_key
        )
        return None
    if not _source_permits(instance, recipient):
        logger.info(
            "notifications.rejected reason=source_unauthorized event=%s module=%s",
            request.event_key,
            request.source_module,
        )
        return None

    notification, created = Notification.objects.get_or_create(
        recipient_id=request.recipient_id,
        dedupe_key=instance.dedupe_key,
        defaults={
            field.name: getattr(instance, field.name)
            for field in Notification._meta.fields
            if field.name not in {"id", "recipient", "dedupe_key"}
        },
    )
    if created:
        _audit_delivery(event_key=request.event_key, delivered=1, recipients=1)
    return notification


def deliver_many(
    requests: Sequence[NotificationRequest], *, now: datetime | None = None
) -> int:
    """Deliver a batch and return how many rows were newly created.

    One insert for the whole batch, conflicts ignored: re-running a fan-out
    chunk after a worker crash adds nobody twice. Already-delivered keys are
    filtered out first so the returned count is meaningful; a genuine race
    between the check and the insert is still absorbed by the unique
    constraint rather than raising.
    """
    if not requests:
        return 0
    moment = _now(now)
    recipients = {
        user.pk: user
        for user in User.objects.filter(
            pk__in={request.recipient_id for request in requests}, is_active=True
        )
    }
    instances: list[Notification] = []
    for request in requests:
        recipient = recipients.get(request.recipient_id)
        if recipient is None:
            continue
        instance = _to_instance(request, now=moment)
        if _dead_on_arrival(instance, moment):
            continue
        if not _source_permits(instance, recipient):
            continue
        instances.append(instance)
    if not instances:
        return 0

    already = set(
        Notification.objects.filter(
            recipient_id__in={instance.recipient_id for instance in instances},
            dedupe_key__in={instance.dedupe_key for instance in instances},
        ).values_list("recipient_id", "dedupe_key")
    )
    fresh = [
        instance
        for instance in instances
        if (instance.recipient_id, instance.dedupe_key) not in already
    ]
    if not fresh:
        return 0
    Notification.objects.bulk_create(fresh, ignore_conflicts=True)
    _audit_delivery(
        event_key=fresh[0].event_key,
        delivered=len(fresh),
        recipients=len(instances),
    )
    logger.info(
        "notifications.delivered event=%s attempted=%d created=%d",
        fresh[0].event_key,
        len(instances),
        len(fresh),
    )
    return len(fresh)


def deliver_to_audience(
    template: NotificationRequest, recipient_ids: Sequence[int]
) -> int:
    """Queue a bulk audience delivery in the background.

    Returns the number of recipients handed to the queue. The request that
    calls this writes nothing: an announcement to a thousand agents is a
    thousand rows, and no HTTP request should hold that transaction open.
    """
    unique_ids = sorted({int(item) for item in recipient_ids})
    if not unique_ids:
        return 0

    payload = {
        "notification_type": template.notification_type,
        "event_key": template.event_key,
        "title": template.title,
        "dedupe_key": template.dedupe_key,
        "priority": template.priority,
        "is_mandatory": template.is_mandatory,
        "source_module": template.source_module,
        "source_record_type": template.source_record_type,
        "source_record_id": template.source_record_id,
        "action_key": template.action_key,
        "action_args": list(template.action_args),
        "available_at": template.available_at.isoformat()
        if template.available_at
        else None,
        "expires_at": template.expires_at.isoformat() if template.expires_at else None,
    }

    def _enqueue() -> None:
        from apps.notifications.tasks import fan_out_notifications

        try:
            fan_out_notifications.delay(payload, unique_ids)
        except Exception:
            # Same outbox posture as apps.audit.events.publish: a broker
            # outage must not fail the originating request. Ops replays.
            logger.exception(
                "notifications.fan_out_queue_failed event=%s recipients=%d",
                template.event_key,
                len(unique_ids),
            )

    transaction.on_commit(_enqueue)
    return len(unique_ids)


def _audit_delivery(*, event_key: str, delivered: int, recipients: int) -> None:
    """Record the batch, never its contents.

    One row per batch with counts only. A row per notification would bury the
    audit trail under routine traffic, and notification titles are producer
    copy that the audit log has no reason to duplicate.
    """

    def _log() -> None:
        log_event(
            "notification.delivered",
            actor=system_actor("notifications"),
            target=AuditTarget(
                target_type="notification.batch",
                target_label=event_key,
                target_snapshot={
                    "event_key": event_key,
                    "delivered": delivered,
                    "recipients": recipients,
                },
            ),
            outcome=AuditEvent.Outcome.SUCCESS,
            source="service",
            channel="notifications",
        )

    transaction.on_commit(_log)


# --------------------------------------------------------------------------- #
# Reader state
# --------------------------------------------------------------------------- #


def _own(user: User, public_id) -> Notification | None:
    return Notification.objects.for_recipient(user).filter(public_id=public_id).first()


def mark_read(user: User, public_id, *, now: datetime | None = None) -> bool:
    """Idempotent. ``False`` only means "no such notification for you"."""
    notification = _own(user, public_id)
    if notification is None:
        return False
    Notification.objects.filter(pk=notification.pk, read_at__isnull=True).update(
        read_at=_now(now)
    )
    return True


def mark_unread(user: User, public_id) -> bool:
    notification = _own(user, public_id)
    if notification is None:
        return False
    Notification.objects.filter(pk=notification.pk, read_at__isnull=False).update(
        read_at=None
    )
    return True


def archive(user: User, public_id, *, now: datetime | None = None) -> bool:
    """Archive one notification. Mandatory work must be read first."""
    notification = _own(user, public_id)
    if notification is None:
        return False
    if notification.is_mandatory and notification.read_at is None:
        raise MandatoryAcknowledgementRequired(
            "Read this required notification before filing it away."
        )
    Notification.objects.filter(pk=notification.pk, archived_at__isnull=True).update(
        archived_at=_now(now)
    )
    return True


def mark_all_read(user: User, *, now: datetime | None = None) -> int:
    """Clear the badge, except for notifications that must be acknowledged.

    Mandatory rows survive on purpose: "mark everything read" is a sweep, and
    a compliance acknowledgement that a sweep can clear is not one.
    """
    moment = _now(now)
    return (
        Notification.objects.for_recipient(user)
        .unread(now=moment)
        .filter(is_mandatory=False)
        .update(read_at=moment)
    )


def unread_summary(user: User, *, now: datetime | None = None) -> dict[str, int]:
    """Counts for the header badge — one query, this reader only."""
    moment = _now(now)
    aggregate = (
        Notification.objects.for_recipient(user)
        .unread(now=moment)
        .aggregate(
            unread=Count("pk"),
            mandatory=Count(Case(When(is_mandatory=True, then=1))),
        )
    )
    return {
        "unreadCount": int(aggregate["unread"] or 0),
        "mandatoryCount": int(aggregate["mandatory"] or 0),
    }


def type_counts(user: User, *, now: datetime | None = None) -> dict[str, int]:
    """Unread totals per type, for the centre's filter labels."""
    moment = _now(now)
    rows = (
        Notification.objects.for_recipient(user)
        .unread(now=moment)
        .values("notification_type")
        .annotate(total=Count("pk"))
    )
    return {row["notification_type"]: int(row["total"]) for row in rows}


def purge_expired(*, before: datetime | None = None) -> int:
    """Delete rows whose expiry passed before ``before`` (default: now).

    Expired notifications cannot be acted on and are already hidden from the
    inbox; keeping them forever only grows the table.
    """
    moment = _now(before)
    deleted, _ = Notification.objects.filter(
        Q(expires_at__isnull=False) & Q(expires_at__lte=moment)
    ).delete()
    return deleted
