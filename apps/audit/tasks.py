"""Celery tasks for the domain-event dispatcher.

Retry strategy
--------------
Exponential backoff with jitter: 30s, 90s, 270s, 810s (≈13 min), 2430s (≈40 min).
After MAX_ATTEMPTS the EventDelivery row is marked dead and a structured-log
alert is emitted.  Operators can replay via the admin action or management command.

Idempotency
-----------
Before calling a consumer the task checks EventDelivery.status.  If it is
already ``delivered`` the consumer is skipped and the task succeeds immediately.
This handles the "consumer succeeded but ack failed" edge case.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Delays in seconds for attempt index 0..MAX-1.
_BACKOFF = [30, 90, 270, 810, 2430]
MAX_ATTEMPTS = 5


def _backoff_seconds(attempt: int) -> int:
    idx = min(attempt, len(_BACKOFF) - 1)
    return _BACKOFF[idx]


@shared_task(bind=True, max_retries=MAX_ATTEMPTS, ignore_result=True)
def dispatch_event(self, event_id: str) -> None:
    """Dispatch a single DomainEvent to all registered consumers."""
    from apps.audit.consumers import consumers_for_event
    from apps.audit.events import EventEnvelope, registry
    from apps.audit.models import DomainEvent, EventDelivery

    try:
        event = DomainEvent.objects.get(pk=event_id)
    except DomainEvent.DoesNotExist:
        logger.error("dispatch_event: DomainEvent %s not found", event_id)
        return

    schema = registry.get(event.name, event.version)

    envelope = EventEnvelope(
        id=event.id,
        name=event.name,
        version=event.version,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        subject=event.subject,
        organization_id=event.organization_id,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        payload=event.payload,
    )

    # Re-validate at consume boundary.
    schema.validate(envelope.payload)

    consumer_ids = consumers_for_event(event.name)
    all_ok = True

    for consumer_id in consumer_ids:
        delivery, _ = EventDelivery.objects.get_or_create(
            event=event,
            consumer=consumer_id,
        )

        if delivery.status == EventDelivery.Status.DELIVERED:
            logger.debug(
                "dispatch_event: skip already-delivered consumer=%s event=%s",
                consumer_id,
                event_id,
            )
            continue

        if delivery.status == EventDelivery.Status.DEAD:
            logger.warning(
                "dispatch_event: skip dead consumer=%s event=%s",
                consumer_id,
                event_id,
            )
            continue

        from apps.audit.consumers import get_consumer

        try:
            fn = get_consumer(consumer_id)
            fn(envelope)
        except Exception as exc:
            delivery.attempts += 1
            delivery.last_error = str(exc)[:2000]

            if delivery.is_exhausted:
                delivery.status = EventDelivery.Status.DEAD
                delivery.save(update_fields=["attempts", "last_error", "status"])
                logger.error(
                    "dispatch_event: dead consumer=%s event=%s error=%s",
                    consumer_id,
                    event_id,
                    exc,
                )
            else:
                delay = _backoff_seconds(delivery.attempts)
                delivery.next_attempt_at = timezone.now() + timedelta(seconds=delay)
                delivery.status = EventDelivery.Status.FAILED
                fields = ["attempts", "last_error", "status", "next_attempt_at"]
                delivery.save(update_fields=fields)
                all_ok = False
                logger.warning(
                    "dispatch_event: retry=%d delay=%ds consumer=%s event=%s error=%s",
                    delivery.attempts,
                    delay,
                    consumer_id,
                    event_id,
                    exc,
                )
        else:
            delivery.status = EventDelivery.Status.DELIVERED
            delivery.delivered_at = timezone.now()
            delivery.save(update_fields=["status", "delivered_at"])
            logger.info(
                "dispatch_event: delivered consumer=%s event=%s",
                consumer_id,
                event_id,
            )

    if all_ok:
        DomainEvent.objects.filter(pk=event_id).update(
            status=DomainEvent.Status.DISPATCHED,
            dispatched_at=timezone.now(),
        )
    else:
        # Celery retry for remaining failed deliveries.
        next_delay = _backoff_seconds(self.request.retries)
        raise self.retry(countdown=next_delay)


@shared_task(ignore_result=True)
def replay_event(event_id: str, consumer_id: str | None = None) -> None:
    """Operator-initiated replay.  Resets dead/failed deliveries and re-dispatches.

    Restricted to admin use via the Django admin action or management command.
    This task must only be enqueued through authorized code paths — it is not
    exposed via any API.
    """
    from apps.audit.models import DomainEvent, EventDelivery

    try:
        event = DomainEvent.objects.get(pk=event_id)
    except DomainEvent.DoesNotExist:
        logger.error("replay_event: DomainEvent %s not found", event_id)
        return

    qs = EventDelivery.objects.filter(event=event)
    if consumer_id:
        qs = qs.filter(consumer=consumer_id)

    reset_count = qs.filter(
        status__in=[EventDelivery.Status.DEAD, EventDelivery.Status.FAILED]
    ).update(
        status=EventDelivery.Status.PENDING,
        attempts=0,
        last_error="",
        next_attempt_at=None,
    )

    logger.info(
        "replay_event: reset %d delivery rows for event=%s consumer=%s",
        reset_count,
        event_id,
        consumer_id or "*",
    )

    # Re-dispatch the event.
    event.status = DomainEvent.Status.PENDING
    event.save(update_fields=["status"])
    dispatch_event.delay(event_id)
