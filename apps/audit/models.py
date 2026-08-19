"""Outbox and delivery-tracking models for the domain-event system.

Architecture
------------
DomainEvent
    Immutable record written inside the originating DB transaction.
    The dispatcher Celery task reads pending events after commit and
    dispatches them to registered consumers.

EventDelivery
    Per-consumer delivery record.  Used for idempotency (skip if already
    Delivered) and for tracking retry progress, failure state, and replay.

Retention
---------
Events move to status=archived (or are hard-deleted by a periodic task)
after a configurable retention window.  EventDelivery rows reference their
parent via a nullable FK so archival/deletion of old events does not cascade-
delete the delivery audit trail; do a separate scheduled purge.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class DomainEvent(models.Model):
    """Outbox record.  Written transactionally; never mutated after creation."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        DISPATCHED = "dispatched", _("Dispatched")
        FAILED = "failed", _("Failed")
        ARCHIVED = "archived", _("Archived")

    # --- Envelope (immutable after insert) ---
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("event name"), max_length=120, db_index=True)
    version = models.PositiveSmallIntegerField(_("schema version"), default=1)

    # Actor who triggered the event (user PK or system label).
    actor_id = models.CharField(_("actor"), max_length=255, blank=True)
    # Subject entity: "user:42", "contract:7", etc.
    subject = models.CharField(_("subject"), max_length=255, blank=True)
    # Optional org context for multi-tenancy.
    organization_id = models.CharField(_("organisation"), max_length=255, blank=True)
    # Correlation/causation chain.
    correlation_id = models.UUIDField(_("correlation ID"), null=True, blank=True)
    causation_id = models.UUIDField(_("causation ID"), null=True, blank=True)

    # Minimal, validated payload.  No secrets, no full mutable records.
    payload = models.JSONField(_("payload"), default=dict)

    occurred_at = models.DateTimeField(
        _("occurred at"), default=timezone.now, db_index=True
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    # --- Dispatch tracking ---
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    dispatched_at = models.DateTimeField(_("dispatched at"), null=True, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = _("domain event")
        verbose_name_plural = _("domain events")
        permissions = [
            ("can_replay_events", "Can replay / retry domain events"),
        ]
        indexes = [
            models.Index(
                fields=["status", "occurred_at"], name="audit_de_status_occurred"
            ),
            models.Index(fields=["name", "occurred_at"], name="audit_de_name_occurred"),
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version} [{self.id}]"


class EventDelivery(models.Model):
    """Per-consumer delivery record — idempotency key and retry state."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        DELIVERED = "delivered", _("Delivered")
        FAILED = "failed", _("Failed")
        # Exceeded max retries; requires operator action.
        DEAD = "dead", _("Dead")

    MAX_ATTEMPTS = 5

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        DomainEvent,
        on_delete=models.SET_NULL,
        null=True,
        related_name="deliveries",
        verbose_name=_("event"),
    )
    # Consumer identifier — stable string, e.g. "audit.log_event".
    consumer = models.CharField(_("consumer"), max_length=120, db_index=True)

    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    last_error = models.TextField(_("last error"), blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)
    next_attempt_at = models.DateTimeField(
        _("next attempt at"), null=True, blank=True, db_index=True
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("event delivery")
        verbose_name_plural = _("event deliveries")
        # Composite uniqueness: one delivery record per (event, consumer).
        constraints = [
            models.UniqueConstraint(
                fields=["event", "consumer"],
                name="audit_delivery_unique_event_consumer",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                name="audit_delivery_status_next",
            ),
        ]

    def __str__(self) -> str:
        event_pk = self.event.pk if self.event else None
        return f"{self.consumer} → {event_pk} [{self.status}]"

    @property
    def is_exhausted(self) -> bool:
        return self.attempts >= self.MAX_ATTEMPTS
