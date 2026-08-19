"""Consumer registry — maps event names to handler callables.

A consumer is a plain Python callable:

    def my_consumer(envelope: EventEnvelope) -> None:
        ...

Consumers are registered with a stable string identifier.  That identifier
is stored in EventDelivery rows and is the idempotency key: if a delivery
row for (event_id, consumer_id) already has status=delivered the consumer is
not called again.

Built-in consumers
------------------
``audit.log_event``  – Structured-logs every event.  Used as the mandatory
                       no-op/telemetry consumer that proves the pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from apps.audit.events import EventEnvelope

logger = logging.getLogger(__name__)

ConsumerFn = Callable[[EventEnvelope], None]

_registry: dict[str, ConsumerFn] = {}


def register_consumer(consumer_id: str, fn: ConsumerFn) -> None:
    if consumer_id in _registry:
        raise ValueError(f"Consumer '{consumer_id}' is already registered.")
    _registry[consumer_id] = fn


def get_consumer(consumer_id: str) -> ConsumerFn:
    if consumer_id not in _registry:
        raise KeyError(f"Consumer '{consumer_id}' is not registered.")
    return _registry[consumer_id]


def all_consumers_for(event_name: str) -> list[str]:
    """Return consumer IDs that handle this event name (or '*' wildcard)."""
    return [
        cid
        for cid, _ in _subscriptions
        if cid in _registry and _matches(event_name, cid)
    ]


# Subscription list: (consumer_id, event_name_or_wildcard)
_subscriptions: list[tuple[str, str]] = []


def subscribe(consumer_id: str, event_name: str) -> None:
    """Register that consumer_id wants to receive event_name events."""
    _subscriptions.append((consumer_id, event_name))


def consumers_for_event(event_name: str) -> list[str]:
    """Return all consumer IDs subscribed to an event name."""
    return [
        cid
        for cid, pattern in _subscriptions
        if pattern == event_name or pattern == "*"
    ]


def _matches(event_name: str, consumer_id: str) -> bool:
    for cid, pattern in _subscriptions:
        if cid == consumer_id and (pattern == event_name or pattern == "*"):
            return True
    return False


# ---------------------------------------------------------------------------
# Built-in consumer: audit.log_event
# ---------------------------------------------------------------------------


def _log_event(envelope: EventEnvelope) -> None:
    logger.info(
        "domain_event name=%s version=%d id=%s actor=%s subject=%s",
        envelope.name,
        envelope.version,
        envelope.id,
        envelope.actor_id,
        envelope.subject,
    )


register_consumer("audit.log_event", _log_event)
subscribe("audit.log_event", "*")
