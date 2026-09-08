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


class AuditEvent(models.Model):
    """Append-only audit trail for sensitive business and security actions."""

    class ActorType(models.TextChoices):
        USER = "user", _("User")
        SYSTEM = "system", _("System")
        SERVICE = "service", _("Service")
        ANONYMOUS = "anonymous", _("Anonymous")

    class Outcome(models.TextChoices):
        SUCCESS = "success", _("Success")
        DENIED = "denied", _("Denied")
        FAILURE = "failure", _("Failure")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payload_version = models.PositiveSmallIntegerField(
        _("payload version"), default=1, db_index=True
    )
    action = models.CharField(_("action"), max_length=120, db_index=True)

    actor_type = models.CharField(
        _("actor type"),
        max_length=16,
        choices=ActorType.choices,
        default=ActorType.USER,
        db_index=True,
    )
    actor_id = models.CharField(
        _("actor ID"), max_length=255, blank=True, db_index=True
    )
    actor_label = models.CharField(_("actor label"), max_length=255, blank=True)
    actor_snapshot = models.JSONField(_("actor snapshot"), default=dict)
    impersonated_by = models.JSONField(_("impersonated by"), default=dict, blank=True)

    target_type = models.CharField(_("target type"), max_length=120, db_index=True)
    target_id = models.CharField(
        _("target ID"), max_length=255, blank=True, db_index=True
    )
    target_label = models.CharField(_("target label"), max_length=255, blank=True)
    target_snapshot = models.JSONField(_("target snapshot"), default=dict)

    organization_id = models.CharField(
        _("organization ID"), max_length=255, blank=True, db_index=True
    )
    office_id = models.CharField(
        _("office ID"), max_length=255, blank=True, db_index=True
    )
    region_id = models.CharField(
        _("region ID"), max_length=255, blank=True, db_index=True
    )

    source = models.CharField(_("source"), max_length=64, default="app", db_index=True)
    channel = models.CharField(_("channel"), max_length=64, blank=True)
    request_id = models.CharField(
        _("request ID"), max_length=255, blank=True, db_index=True
    )
    correlation_id = models.UUIDField(_("correlation ID"), null=True, blank=True)
    remote_addr = models.CharField(_("remote address"), max_length=128, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=512, blank=True)

    outcome = models.CharField(
        _("outcome"),
        max_length=16,
        choices=Outcome.choices,
        default=Outcome.SUCCESS,
        db_index=True,
    )
    reason = models.TextField(_("reason"), blank=True)

    before = models.JSONField(_("before"), default=dict, blank=True)
    after = models.JSONField(_("after"), default=dict, blank=True)
    changes = models.JSONField(_("changes"), default=dict, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    occurred_at = models.DateTimeField(
        _("occurred at"), default=timezone.now, db_index=True
    )
    recorded_at = models.DateTimeField(_("recorded at"), auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-recorded_at"]
        verbose_name = _("audit event")
        verbose_name_plural = _("audit events")
        permissions = [
            ("can_view_audit_events", "Can view audit events"),
            ("can_export_audit_events", "Can export audit events"),
            (
                "can_view_activity_timeline",
                "Can view user-facing activity timelines",
            ),
        ]
        indexes = [
            models.Index(fields=["occurred_at"], name="audit_ae_occurred"),
            models.Index(fields=["actor_type", "actor_id"], name="audit_ae_actor"),
            models.Index(fields=["action", "occurred_at"], name="audit_ae_action"),
            models.Index(fields=["target_type", "target_id"], name="audit_ae_target"),
            models.Index(
                fields=["organization_id", "occurred_at"], name="audit_ae_org"
            ),
            models.Index(fields=["office_id", "occurred_at"], name="audit_ae_office"),
            models.Index(fields=["region_id", "occurred_at"], name="audit_ae_region"),
            models.Index(fields=["request_id"], name="audit_ae_request"),
        ]

    def __str__(self) -> str:
        return f"{self.action} [{self.outcome}] {self.target_type}:{self.target_id}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise RuntimeError("AuditEvent is append-only and cannot be updated.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditEvent is append-only and cannot be deleted.")
