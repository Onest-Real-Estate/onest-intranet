"""The in-app notification record.

One row is one delivery to one recipient. There is no shared "notification"
object fanned out by reference: per-recipient rows are what make read state,
archival, and the unread badge answerable with a single indexed query against
``recipient_id``, and what make "self-only" a database fact rather than a
convention every caller has to remember.

What the row deliberately does **not** hold: the client, property, document,
or person the notification is about. See :mod:`apps.notifications.contract`.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.notifications.categories import (
    CHANNEL_EMAIL,
    PREFERENCE_POLICY_VERSION,
)
from apps.notifications.contract import (
    MAX_DEDUPE_KEY_LENGTH,
    MAX_TITLE_LENGTH,
    NotificationPriority,
    NotificationType,
)

TYPE_CHOICES = [
    (NotificationType.CONTRACT, _("Contracts")),
    (NotificationType.TRANSACTION, _("Transactions")),
    (NotificationType.ANNOUNCEMENT, _("Announcements")),
    (NotificationType.TRAINING, _("Training")),
    (NotificationType.INVENTORY, _("Inventory")),
    (NotificationType.ROOM, _("Rooms")),
    (NotificationType.LEAD, _("Leads")),
    (NotificationType.ADMINISTRATIVE, _("Administration")),
    (NotificationType.ACCOUNT, _("Your account")),
]

PRIORITY_CHOICES = [
    (NotificationPriority.CRITICAL, _("Critical")),
    (NotificationPriority.HIGH, _("High")),
    (NotificationPriority.NORMAL, _("Normal")),
    (NotificationPriority.LOW, _("Low")),
]


class NotificationQuerySet(models.QuerySet["Notification"]):
    """Every reader-facing query starts at :meth:`for_recipient`.

    The recipient filter is applied first and is never optional. A helper that
    could be called without it would eventually be called without it.
    """

    def for_recipient(self, user) -> NotificationQuerySet:
        return self.filter(recipient=user)

    def released(self, *, now=None) -> NotificationQuerySet:
        """Rows whose scheduled availability has arrived."""
        return self.filter(available_at__lte=now or timezone.now())

    def unexpired(self, *, now=None) -> NotificationQuerySet:
        moment = now or timezone.now()
        return self.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=moment))

    def inbox(self, *, now=None) -> NotificationQuerySet:
        """What the notification centre shows by default: live, not archived."""
        return self.released(now=now).filter(archived_at__isnull=True)

    def unread(self, *, now=None) -> NotificationQuerySet:
        """What the badge counts.

        Expired rows are excluded: an expired notification cannot be acted on,
        so counting it would leave a badge the reader has no way to clear.
        """
        return self.inbox(now=now).unexpired(now=now).filter(read_at__isnull=True)


class Notification(models.Model):
    """One in-app notification delivered to one recipient."""

    #: Opaque, client-facing identity. The integer primary key is never
    #: exposed: sequential ids in a URL tell a reader how many notifications
    #: the brokerage sends, and invite guessing at somebody else's.
    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, unique=True, editable=False
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("recipient"),
        related_name="notifications",
        on_delete=models.CASCADE,
    )
    notification_type = models.CharField(
        _("type"), max_length=32, choices=TYPE_CHOICES, db_index=True
    )
    #: Producing domain event or producer identity, e.g.
    #: ``"user.onboarding.owner_assigned"``. Observability, not authorization.
    event_key = models.CharField(_("event"), max_length=120)
    title = models.CharField(_("title"), max_length=MAX_TITLE_LENGTH)
    priority = models.PositiveSmallIntegerField(
        _("priority"),
        choices=PRIORITY_CHOICES,
        default=NotificationPriority.NORMAL,
    )
    is_mandatory = models.BooleanField(
        _("mandatory"),
        default=False,
        help_text=_(
            "Must be acknowledged individually; excluded from mark-all-read "
            "and cannot be archived while unread."
        ),
    )
    #: Provenance of the related object. Read by the source resolver at view
    #: time; never trusted as proof that the reader may see that object.
    source_module = models.CharField(_("source module"), max_length=64, blank=True)
    source_record_type = models.CharField(_("source record"), max_length=64, blank=True)
    source_record_id = models.CharField(
        _("source record id"), max_length=64, blank=True
    )
    #: Key from ``apps.notifications.actions``; reversed at render time.
    action_key = models.CharField(_("action"), max_length=64, blank=True)
    action_args = models.JSONField(_("action arguments"), default=list, blank=True)
    dedupe_key = models.CharField(
        _("idempotency key"),
        max_length=MAX_DEDUPE_KEY_LENGTH,
        help_text=_("Unique per recipient; a replayed producer creates nothing."),
    )
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    available_at = models.DateTimeField(_("available from"), default=timezone.now)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)
    archived_at = models.DateTimeField(_("archived at"), null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    if TYPE_CHECKING:
        recipient_id: int

    class Meta:
        ordering = ["-available_at", "-pk"]
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        indexes = [
            # The badge: recipient + unread + not archived, newest first.
            models.Index(
                fields=["recipient", "read_at", "archived_at", "available_at"],
                name="notif_recipient_unread",
            ),
            # The centre's default page and its filtered variants.
            models.Index(
                fields=["recipient", "archived_at", "available_at"],
                name="notif_recipient_inbox",
            ),
            models.Index(
                fields=["recipient", "notification_type", "available_at"],
                name="notif_recipient_type",
            ),
            models.Index(
                fields=["recipient", "priority", "available_at"],
                name="notif_recipient_priority",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedupe_key"], name="notif_recipient_dedupe"
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(expires_at__gt=models.F("available_at")),
                name="notif_expiry_after_availability",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.notification_type}:{self.dedupe_key}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def is_expired(self, *, now=None) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= (now or timezone.now())


class NotificationPreference(models.Model):
    """One reader's channel choices, stored as choices — not as a full matrix.

    ``channels`` holds only what the reader has explicitly decided, shaped
    ``{channel: {category: bool}}``. Everything absent falls back to the
    registry default in :mod:`apps.notifications.categories` at read time.

    That is deliberate. A stored full matrix would freeze today's catalog into
    every row: adding a category later would leave every existing reader with
    no entry for it and no way to tell "never chose" apart from "chose off",
    and changing a default would silently not apply to anybody. Storing only
    decisions means a new category arrives at its documented default for
    everyone, and a reader's saved choices keep meaning exactly what they meant
    when they were made.

    Mandatory categories are never stored here. They are forced on when the
    map is resolved, so a hand-edited row cannot switch off a legal notice.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="notification_preference",
        on_delete=models.CASCADE,
    )
    channels = models.JSONField(
        _("channel choices"),
        default=dict,
        blank=True,
        help_text=_(
            "Explicit choices only, as {channel: {category: bool}}. Absent "
            "entries follow the category default."
        ),
    )
    #: The catalog version the reader was looking at when they last saved.
    #: Behind the current version means categories have been added or defaults
    #: changed since; the settings page says so rather than resetting anything.
    policy_version = models.PositiveSmallIntegerField(
        _("policy version"), default=PREFERENCE_POLICY_VERSION
    )
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    if TYPE_CHECKING:
        user_id: int

    class Meta:
        verbose_name = _("notification preference")
        verbose_name_plural = _("notification preferences")

    def __str__(self) -> str:
        return f"notification-preferences:{self.user_id}"


class NotificationEmail(models.Model):
    """One attempt to push one notification out over one channel.

    The row is the delivery ledger. It exists so a failure is *observable and
    retryable without touching domain state*: the notification itself is
    already committed and visible in the hub, and nothing about a bounced or
    deferred email rolls that back.

    ``(recipient, channel, delivery_key)`` is unique, and ``delivery_key`` is
    the notification's own idempotency key. One logical event therefore yields
    at most one delivery per recipient per channel however many times the
    producing event is replayed, the fan-out chunk is re-run, or a worker
    restarts mid-flight.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Queued")
        SENDING = "sending", _("Sending")
        SENT = "sent", _("Sent")
        SUPPRESSED = "suppressed", _("Suppressed")
        FAILED = "failed", _("Failed — will retry")
        DEAD = "dead", _("Failed — gave up")

    #: Statuses nothing re-attempts. ``SUPPRESSED`` is terminal on purpose: the
    #: reason it was suppressed (unsubscribed, already read, source withdrawn)
    #: does not become untrue later in a way that should resurrect the email.
    TERMINAL_STATUSES = frozenset({Status.SENT, Status.SUPPRESSED, Status.DEAD})

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, unique=True, editable=False
    )
    notification = models.ForeignKey(
        "notifications.Notification",
        verbose_name=_("notification"),
        related_name="deliveries",
        on_delete=models.CASCADE,
    )
    #: Denormalized from the notification so the uniqueness constraint and
    #: every operational query are answerable without a join.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("recipient"),
        related_name="notification_deliveries",
        on_delete=models.CASCADE,
    )
    channel = models.CharField(_("channel"), max_length=16, default=CHANNEL_EMAIL)
    delivery_key = models.CharField(
        _("delivery key"),
        max_length=MAX_DEDUPE_KEY_LENGTH,
        help_text=_("The notification's idempotency key; unique per channel."),
    )
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    last_error = models.TextField(_("last error"), blank=True)
    #: Why the send was abandoned before it was attempted. Machine-readable and
    #: deliberately coarse — never the record detail that caused it.
    suppression_reason = models.CharField(
        _("suppression reason"), max_length=64, blank=True
    )
    #: The address revalidated at send time, not at queue time. Recorded so an
    #: operator can see where a message actually went after an address change.
    to_email = models.EmailField(_("sent to"), blank=True)
    queued_at = models.DateTimeField(_("queued at"), default=timezone.now)
    first_attempt_at = models.DateTimeField(
        _("first attempt at"), null=True, blank=True
    )
    last_attempt_at = models.DateTimeField(_("last attempt at"), null=True, blank=True)
    next_attempt_at = models.DateTimeField(_("next attempt at"), null=True, blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)

    if TYPE_CHECKING:
        notification_id: int
        recipient_id: int

    class Meta:
        ordering = ["-queued_at", "-pk"]
        verbose_name = _("notification delivery")
        verbose_name_plural = _("notification deliveries")
        indexes = [
            # The worker sweep: what is due, oldest first.
            models.Index(fields=["status", "next_attempt_at"], name="notif_email_due"),
            models.Index(fields=["status", "queued_at"], name="notif_email_backlog"),
            models.Index(fields=["recipient", "status"], name="notif_email_recipient"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "channel", "delivery_key"],
                name="notif_email_recipient_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.channel}:{self.delivery_key}:{self.status}"

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES
