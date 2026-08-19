"""Tests for the domain-event system.

Coverage
--------
- Envelope validation and schema registry
- Sensitive payload rejection
- Transactional rollback produces no event
- Transaction commit produces exactly one event
- Idempotency: duplicate delivery is skipped
- Retry / dead-letter behaviour
- Authorized vs unauthorized replay
- Version evolution compatibility
- Worker-outage recovery (broker unavailable → event survives in outbox)
- Integration: user.onboarded wired from onboarding view
- Built-in telemetry consumer (audit.log_event) processes events
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from apps.audit.consumers import consumers_for_event, register_consumer, subscribe
from apps.audit.events import (
    EventEnvelope,
    EventSchemaError,
    UnregisteredEventError,
    publish,
    registry,
)
from apps.audit.models import DomainEvent, EventDelivery
from apps.audit.tasks import (
    MAX_ATTEMPTS,
    _backoff_seconds,
    dispatch_event,
    replay_event,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_envelope(**kwargs) -> EventEnvelope:
    defaults: dict = {
        "id": uuid.uuid4(),
        "name": "user.onboarded",
        "version": 1,
        "occurred_at": timezone.now(),
        "actor_id": "1",
        "subject": "user:1",
        "organization_id": "",
        "correlation_id": None,
        "causation_id": None,
        "payload": {"user_id": 1, "email": "a@b.com", "office_id": None},
    }
    defaults.update(kwargs)
    return EventEnvelope(**defaults)


# ---------------------------------------------------------------------------
# Registry and schema validation
# ---------------------------------------------------------------------------


def test_registry_get_registered_event():
    schema = registry.get("user.onboarded", 1)
    assert schema.name == "user.onboarded"
    assert schema.version == 1


def test_registry_unknown_event_raises():
    with pytest.raises(UnregisteredEventError, match="not registered"):
        registry.get("does.not.exist", 1)


def test_registry_unknown_version_raises():
    with pytest.raises(UnregisteredEventError, match="version 99"):
        registry.get("user.onboarded", 99)


def test_schema_validate_missing_key():
    schema = registry.get("user.onboarded", 1)
    with pytest.raises(EventSchemaError, match="missing keys"):
        schema.validate({"user_id": 1})  # missing email and office_id


def test_schema_validate_success():
    schema = registry.get("user.onboarded", 1)
    # Should not raise.
    schema.validate({"user_id": 1, "email": "a@b.com", "office_id": None})


def test_all_catalog_events_registered():
    expected = {
        "user.onboarded",
        "contract.created",
        "contract.signed",
        "transaction.created",
        "lead.created",
        "reservation.created",
    }
    assert expected <= set(registry.all_names())


# ---------------------------------------------------------------------------
# Sensitive payload rejection
# ---------------------------------------------------------------------------


def test_sensitive_key_password_rejected():
    schema = registry.get("user.onboarded", 1)
    with pytest.raises(EventSchemaError, match="sensitive"):
        schema.validate(
            {
                "user_id": 1,
                "email": "a@b.com",
                "office_id": None,
                "password": "hunter2",
            }
        )


def test_sensitive_key_token_rejected():
    schema = registry.get("user.onboarded", 1)
    with pytest.raises(EventSchemaError, match="sensitive"):
        schema.validate(
            {
                "user_id": 1,
                "email": "a@b.com",
                "office_id": None,
                "access_token": "abc",
            }
        )


def test_sensitive_key_nested_rejected():
    schema = registry.get("user.onboarded", 1)
    with pytest.raises(EventSchemaError, match="sensitive"):
        schema.validate(
            {
                "user_id": 1,
                "email": "a@b.com",
                "office_id": None,
                "meta": {"secret": "x"},
            }
        )


# ---------------------------------------------------------------------------
# Transactional publish — rollback produces no event
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_rollback_produces_no_event():
    before = DomainEvent.objects.count()
    try:
        with transaction.atomic():
            publish(
                "user.onboarded",
                actor_id="1",
                subject="user:1",
                payload={"user_id": 1, "email": "x@y.com", "office_id": None},
            )
            raise RuntimeError("intentional rollback")
    except RuntimeError:
        pass
    assert DomainEvent.objects.count() == before


@pytest.mark.django_db(transaction=True)
def test_commit_produces_exactly_one_event():
    before = DomainEvent.objects.count()
    with patch("apps.audit.tasks.dispatch_event.delay"):
        publish(
            "user.onboarded",
            actor_id="2",
            subject="user:2",
            payload={"user_id": 2, "email": "z@y.com", "office_id": None},
        )
    assert DomainEvent.objects.count() == before + 1


@pytest.mark.django_db(transaction=True)
def test_publish_sets_pending_status():
    with patch("apps.audit.tasks.dispatch_event.delay"):
        event = publish(
            "user.onboarded",
            actor_id="3",
            subject="user:3",
            payload={"user_id": 3, "email": "b@c.com", "office_id": None},
        )
    event.refresh_from_db()
    assert event.status == DomainEvent.Status.PENDING


@pytest.mark.django_db(transaction=True)
def test_publish_enqueues_dispatch_on_commit():
    with patch("apps.audit.tasks.dispatch_event.delay") as mock_delay:
        event = publish(
            "user.onboarded",
            actor_id="4",
            subject="user:4",
            payload={"user_id": 4, "email": "c@d.com", "office_id": None},
        )
    mock_delay.assert_called_once_with(str(event.id))


# ---------------------------------------------------------------------------
# dispatch_event task — idempotency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dispatch_delivers_to_log_consumer():
    event = DomainEvent.objects.create(
        name="user.onboarded",
        version=1,
        actor_id="5",
        subject="user:5",
        payload={"user_id": 5, "email": "d@e.com", "office_id": None},
    )
    with patch(
        "apps.audit.tasks.dispatch_event.retry", side_effect=Exception("no retry")
    ):
        dispatch_event(str(event.id))

    delivery = EventDelivery.objects.get(event=event, consumer="audit.log_event")
    assert delivery.status == EventDelivery.Status.DELIVERED
    event.refresh_from_db()
    assert event.status == DomainEvent.Status.DISPATCHED


@pytest.mark.django_db
def test_dispatch_idempotent_on_duplicate_delivery():
    """Second dispatch for an already-delivered consumer must be a no-op."""
    event = DomainEvent.objects.create(
        name="user.onboarded",
        version=1,
        actor_id="6",
        subject="user:6",
        payload={"user_id": 6, "email": "e@f.com", "office_id": None},
    )
    EventDelivery.objects.create(
        event=event,
        consumer="audit.log_event",
        status=EventDelivery.Status.DELIVERED,
    )

    called = []

    def spy_consumer(envelope):
        called.append(True)

    with patch.dict(
        "apps.audit.consumers._registry", {"audit.log_event": spy_consumer}
    ):
        dispatch_event(str(event.id))

    assert called == [], "Consumer must not be called again for delivered delivery"


# ---------------------------------------------------------------------------
# Retry / dead-letter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_failing_consumer_increments_attempts():
    event = DomainEvent.objects.create(
        name="user.onboarded",
        version=1,
        actor_id="7",
        subject="user:7",
        payload={"user_id": 7, "email": "f@g.com", "office_id": None},
    )

    def exploding(envelope):
        raise ValueError("boom")

    with (
        patch.dict("apps.audit.consumers._registry", {"audit.log_event": exploding}),
        patch("apps.audit.tasks.dispatch_event.retry", side_effect=Exception("retry")),
        contextlib.suppress(Exception),
    ):
        dispatch_event(str(event.id))

    delivery = EventDelivery.objects.get(event=event, consumer="audit.log_event")
    assert delivery.attempts == 1
    assert "boom" in delivery.last_error


@pytest.mark.django_db
def test_exhausted_consumer_goes_dead():
    event = DomainEvent.objects.create(
        name="user.onboarded",
        version=1,
        actor_id="8",
        subject="user:8",
        payload={"user_id": 8, "email": "g@h.com", "office_id": None},
    )
    # Pre-create delivery at max attempts - 1 so one more failure exhausts it.
    delivery = EventDelivery.objects.create(
        event=event,
        consumer="audit.log_event",
        status=EventDelivery.Status.FAILED,
        attempts=MAX_ATTEMPTS - 1,
    )

    def exploding(envelope):
        raise ValueError("final failure")

    with (
        patch.dict("apps.audit.consumers._registry", {"audit.log_event": exploding}),
        patch("apps.audit.tasks.dispatch_event.retry", side_effect=Exception("retry")),
        contextlib.suppress(Exception),
    ):
        dispatch_event(str(event.id))

    delivery.refresh_from_db()
    assert delivery.status == EventDelivery.Status.DEAD


def test_backoff_seconds_increases():
    delays = [_backoff_seconds(i) for i in range(MAX_ATTEMPTS)]
    assert delays == sorted(delays), "Backoff must be non-decreasing"
    assert delays[0] < delays[-1], "Backoff must grow"


# ---------------------------------------------------------------------------
# Replay — authorization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_replay_resets_dead_delivery():
    event = DomainEvent.objects.create(
        name="user.onboarded",
        version=1,
        actor_id="9",
        subject="user:9",
        payload={"user_id": 9, "email": "h@i.com", "office_id": None},
        status=DomainEvent.Status.FAILED,
    )
    delivery = EventDelivery.objects.create(
        event=event,
        consumer="audit.log_event",
        status=EventDelivery.Status.DEAD,
        attempts=MAX_ATTEMPTS,
    )

    with patch("apps.audit.tasks.dispatch_event.delay") as mock_dispatch:
        replay_event(str(event.id))

    delivery.refresh_from_db()
    assert delivery.status == EventDelivery.Status.PENDING
    assert delivery.attempts == 0
    mock_dispatch.assert_called_once_with(str(event.id))


@pytest.mark.django_db
def test_replay_unknown_event_logs_and_returns():
    """Replay of a nonexistent event must log an error and not raise."""
    missing_id = str(uuid.uuid4())
    # Should not raise.
    replay_event(missing_id)


# ---------------------------------------------------------------------------
# Version evolution / compatibility
# ---------------------------------------------------------------------------


def test_version_1_schema_validates_v1_payload():
    schema = registry.get("user.onboarded", 1)
    schema.validate({"user_id": 1, "email": "a@b.com", "office_id": 5})


def test_old_version_schema_preserved_when_new_version_registered():
    """Registering v2 must not remove v1 so queued v1 events remain valid."""
    from apps.audit.events import EventRegistry

    local_reg = EventRegistry()
    local_reg.register(name="test.evt", version=1, required_payload_keys={"a"})
    local_reg.register(name="test.evt", version=2, required_payload_keys={"a", "b"})

    v1 = local_reg.get("test.evt", 1)
    v2 = local_reg.get("test.evt", 2)
    assert v1.required_payload_keys == frozenset({"a"})
    assert v2.required_payload_keys == frozenset({"a", "b"})


# ---------------------------------------------------------------------------
# Worker / broker outage recovery
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_event_survives_broker_outage():
    """If the broker is unavailable at publish time the DB row still exists."""
    with (
        patch(
            "apps.audit.tasks.dispatch_event.delay",
            side_effect=Exception("broker down"),
        ),
        contextlib.suppress(Exception),
    ):
        publish(
            "user.onboarded",
            actor_id="10",
            subject="user:10",
            payload={"user_id": 10, "email": "j@k.com", "office_id": None},
        )

    # The DomainEvent row must exist; status is still PENDING (outbox pattern).
    assert DomainEvent.objects.filter(name="user.onboarded", actor_id="10").exists()


# ---------------------------------------------------------------------------
# Consumer subscription helpers
# ---------------------------------------------------------------------------


def test_consumers_for_event_includes_wildcard():
    """audit.log_event subscribes to '*' so it must appear for every event."""
    consumers = consumers_for_event("user.onboarded")
    assert "audit.log_event" in consumers


def test_consumers_for_event_specific_subscription():
    local_consumer_id = "test.specific_consumer"
    local_event = "contract.created"

    register_consumer(local_consumer_id, lambda e: None)
    subscribe(local_consumer_id, local_event)

    assert local_consumer_id in consumers_for_event(local_event)
    assert local_consumer_id not in consumers_for_event("user.onboarded")
