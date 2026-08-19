"""Domain-event registry, envelope, schema validation, and publisher.

Usage
-----
Publishing an event (inside a Django view/service — runs after commit):

    from apps.audit.events import publish

    publish(
        "user.onboarded",
        actor_id=str(user.pk),
        subject=f"user:{user.pk}",
        payload={"email": user.email, "office_id": user.office_id},
    )

Registering a new event:

    from apps.audit.events import registry

    registry.register(
        name="contract.created",
        version=1,
        required_payload_keys={"contract_id", "office_id"},
        description="Emitted when an agent creates a new contract draft.",
    )

Schema evolution
----------------
Increment ``version`` when removing/renaming required keys.  Additive changes
to optional keys do not require a version bump.  Old queued events carry their
original version and are validated against the schema for that version.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.audit.models import DomainEvent

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema / registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventSchema:
    name: str
    version: int
    required_payload_keys: frozenset[str]
    description: str = ""

    def validate(self, payload: dict[str, Any]) -> None:
        missing = self.required_payload_keys - payload.keys()
        if missing:
            raise EventSchemaError(
                f"Event '{self.name}' v{self.version} payload missing keys: {missing}"
            )
        _reject_sensitive(payload)


class EventSchemaError(ValueError):
    """Raised when a payload does not conform to its declared schema."""


class UnregisteredEventError(KeyError):
    """Raised when publishing or consuming an unregistered event name."""


# Sensitive key fragments — a payload key matching any of these is rejected.
_SENSITIVE_FRAGMENTS = frozenset(
    {"password", "token", "secret", "credential", "ssn", "credit_card", "cvv"}
)


def _reject_sensitive(payload: dict[str, Any], path: str = "") -> None:
    for key, value in payload.items():
        full_key = f"{path}.{key}" if path else key
        for frag in _SENSITIVE_FRAGMENTS:
            if frag in full_key.lower():
                raise EventSchemaError(
                    f"Payload key '{full_key}' looks sensitive "
                    "and must not be included in events."
                )
        if isinstance(value, dict):
            _reject_sensitive(value, path=full_key)


class EventRegistry:
    def __init__(self) -> None:
        # {name: {version: EventSchema}}
        self._schemas: dict[str, dict[int, EventSchema]] = {}

    def register(
        self,
        *,
        name: str,
        version: int = 1,
        required_payload_keys: set[str] | frozenset[str] = frozenset(),
        description: str = "",
    ) -> None:
        schema = EventSchema(
            name=name,
            version=version,
            required_payload_keys=frozenset(required_payload_keys),
            description=description,
        )
        self._schemas.setdefault(name, {})[version] = schema

    def get(self, name: str, version: int = 1) -> EventSchema:
        versions = self._schemas.get(name)
        if versions is None:
            raise UnregisteredEventError(
                f"Event '{name}' is not registered. Add it to apps/audit/catalog.py."
            )
        schema = versions.get(version)
        if schema is None:
            registered = sorted(versions.keys())
            raise UnregisteredEventError(
                f"Event '{name}' version {version} is not registered. "
                f"Registered versions: {registered}."
            )
        return schema

    def all_names(self) -> list[str]:
        return sorted(self._schemas.keys())


registry = EventRegistry()


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


@dataclass
class EventEnvelope:
    id: uuid.UUID
    name: str
    version: int
    occurred_at: Any  # datetime
    actor_id: str
    subject: str
    organization_id: str
    correlation_id: uuid.UUID | None
    causation_id: uuid.UUID | None
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "version": self.version,
            "occurred_at": self.occurred_at.isoformat(),
            "actor_id": self.actor_id,
            "subject": self.subject,
            "organization_id": self.organization_id,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "payload": self.payload,
        }


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------


def publish(
    name: str,
    *,
    actor_id: str = "",
    subject: str = "",
    organization_id: str = "",
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    version: int = 1,
) -> DomainEvent:
    """Validate and persist an event inside the current transaction.

    The dispatcher task is enqueued via ``on_commit`` so the event is only
    dispatched after the originating transaction commits.  A rollback leaves
    no event record.
    """
    from apps.audit.models import DomainEvent

    if payload is None:
        payload = {}

    schema = registry.get(name, version)
    schema.validate(payload)

    event = DomainEvent.objects.create(
        name=name,
        version=version,
        actor_id=actor_id,
        subject=subject,
        organization_id=organization_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=payload,
        occurred_at=timezone.now(),
    )

    event_id = str(event.id)

    def _dispatch():
        from apps.audit.tasks import dispatch_event

        dispatch_event.delay(event_id)
        logger.info("event.queued name=%s id=%s", name, event_id)

    transaction.on_commit(_dispatch)

    logger.debug("event.created name=%s id=%s version=%d", name, event_id, version)
    return event
