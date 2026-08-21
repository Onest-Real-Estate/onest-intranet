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
