"""The domain-event consumer that turns events into notifications.

Registered once at app startup and subscribed only to the events that have a
builder in :mod:`apps.notifications.producers`. Running as a consumer rather
than an inline call is what gives the delivery its after-commit, retried,
idempotent behaviour for free — see ``apps/audit/tasks.dispatch_event``.
"""

from __future__ import annotations

import logging

from apps.audit.events import EventEnvelope

logger = logging.getLogger("apps.notifications")

CONSUMER_ID = "notifications.deliver"


def deliver_for_event(envelope: EventEnvelope) -> None:
    from apps.notifications.producers import notifications_for_event
    from apps.notifications.service import deliver_many

    requests = notifications_for_event(envelope)
    if not requests:
        return
    created = deliver_many(requests)
    logger.info(
        "notifications.event_consumed event=%s id=%s created=%d",
        envelope.name,
        envelope.id,
        created,
    )


def register_notification_consumer() -> None:
    """Idempotent registration — app startup may run more than once in tests."""
    from apps.audit.consumers import (
        consumers_for_event,
        is_registered,
        register_consumer,
        subscribe,
    )
    from apps.notifications.producers import EVENT_PRODUCERS

    if not is_registered(CONSUMER_ID):
        register_consumer(CONSUMER_ID, deliver_for_event)
    for name in EVENT_PRODUCERS:
        if CONSUMER_ID not in consumers_for_event(name):
            subscribe(CONSUMER_ID, name)
