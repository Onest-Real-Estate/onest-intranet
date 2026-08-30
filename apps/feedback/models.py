"""Feedback tickets, their replies, and their screenshots.

Storage only — every status change, assignment, and conversion goes through
:mod:`apps.feedback.services`.

Two things here are authorization boundaries rather than display hints, and
both are enforced in the queryset before a payload exists:

* ``FeedbackNote.internal`` — a staff-only note is never serialized to the
  submitter. The whole point of the internal channel is that a triager can
  write "this is the third time this week from this office" without it landing
  in the reporter's inbox.
* ``FeedbackScreenshot`` — private storage, no public URL, fetched through a
  view that re-authorizes against the parent ticket on every request. A
  screenshot of a broken page routinely contains somebody else's data.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.feedback.taxonomy import (
    CATEGORY_CHOICES,
    OPEN_STATUSES,
    PRIORITY_CHOICES,
    STATUS_CHOICES,
    STATUS_LABELS,
    TERMINAL_STATUSES,
    URGENCY_CHOICES,
    FeedbackPriority,
    FeedbackStatus,
)
from apps.user.models import Office
from apps.user.storage import private_storage

_OPEN = sorted(OPEN_STATUSES)
_TERMINAL = sorted(TERMINAL_STATUSES)


def screenshot_upload_to(instance: FeedbackScreenshot, filename: str) -> str:
    """Private, unguessable, namespaced by the ticket's public id."""
    suffix = filename.rsplit("/", 1)[-1][:120]
    return f"feedback/{instance.ticket.public_id}/{instance.public_id}/{suffix}"


class FeedbackQuerySet(models.QuerySet["FeedbackTicket"]):
    def open(self) -> FeedbackQuerySet:
        return self.filter(status__in=_OPEN)

    def for_reader(self, user, *, access, can_triage: bool) -> FeedbackQuerySet:
        """The tickets this reader may see, applied before anything else.

        Two completely different audiences share this method:

        * **A submitter** sees their own tickets and nothing else, whatever
          office they are in. Feedback is personal — "who else complained" is
          not a question the reporter gets to ask.
        * **Support staff** see tickets inside their office reach. Company
          reach sees everything.

        The ``can_triage`` flag is what separates them, and it is passed in
        rather than derived here so the caller cannot forget that reading
        somebody else's ticket is a *granted* capability.

        This is the only place ticket visibility is decided. A later
        Python-side check would still leak existence through counts and
        pagination totals.
        """
        if getattr(user, "is_anonymous", False):
            return self.none()

        mine = Q(submitter=user)
        if not can_triage:
            return self.filter(mine)

        if getattr(user, "is_superuser", False) or access.company_wide:
            return self.all()

        reach = Q(pk__in=[])
        if access.office_keys:
            reach |= Q(office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            reach |= Q(office__region__stable_key__in=sorted(access.region_keys))
        # Assignment is a personal grant: being handed a ticket lets you read
        # it even when it sits outside your office reach.
        return self.filter(reach | mine | Q(assignee=user)).distinct()


class FeedbackTicket(models.Model):
    """One report from one person."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    #: Shown to the submitter and quoted in email subjects.
    reference = models.CharField(_("reference"), max_length=16, unique=True, blank=True)

    category = models.CharField(_("category"), max_length=32, choices=CATEGORY_CHOICES)
    summary = models.CharField(_("summary"), max_length=160)
    description = models.TextField(_("description"))
    urgency = models.CharField(_("urgency"), max_length=16, choices=URGENCY_CHOICES)

    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="feedback_tickets",
        verbose_name=_("submitter"),
    )
    #: Snapshotted at submission. The submitter may move office later, and the
    #: ticket belongs to the office it was raised from — re-reading it live
    #: would silently move old tickets between support queues.
    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="feedback_tickets",
        verbose_name=_("office at submission"),
    )

    status = models.CharField(
        _("status"), max_length=20, choices=STATUS_CHOICES, default=FeedbackStatus.NEW
    )
    priority = models.PositiveSmallIntegerField(
        _("priority"), choices=PRIORITY_CHOICES, default=FeedbackPriority.NORMAL
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_feedback",
        verbose_name=_("assignee"),
    )

    #: Scrubbed by `apps.feedback.diagnostics` before it ever reaches here.
    page_url = models.CharField(_("page"), max_length=2000, blank=True)
    browser_metadata = models.JSONField(_("browser metadata"), default=dict, blank=True)

    #: The client's idempotency key. Unique, so a double-submitted form or a
    #: retried request returns the first ticket instead of making a second.
    submission_key = models.CharField(
        _("submission key"), max_length=64, unique=True, editable=False
    )

    #: Set when a triager converts this into operational work. Held as the
    #: task's public id rather than a foreign key so the modules stay
    #: independently deployable and neither blocks the other's migrations.
    converted_task_id = models.CharField(
        _("converted task"), max_length=64, blank=True, db_index=True
    )

    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = FeedbackQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("feedback ticket")
        verbose_name_plural = _("feedback tickets")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status__in=_TERMINAL, closed_at__isnull=False)
                    | (~Q(status__in=_TERMINAL) & Q(closed_at__isnull=True))
                ),
                name="feedback_closed_at_matches_status",
            ),
            models.CheckConstraint(
                condition=~Q(summary="") & ~Q(description=""),
                name="feedback_requires_summary_and_description",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "priority"], name="fb_status_priority_idx"),
            models.Index(fields=["office", "status"], name="fb_office_status_idx"),
            models.Index(fields=["submitter", "-created_at"], name="fb_submitter_idx"),
            models.Index(fields=["assignee", "status"], name="fb_assignee_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.reference or 'FB-?'} {self.summary}"

    # Django generates these at runtime; the type checker cannot see them
    # through a string-referenced ``AUTH_USER_MODEL`` foreign key, and
    # comparing ids must never cost a query.
    @property
    def submitter_pk(self) -> int | None:
        return getattr(self, "submitter_id", None)

    @property
    def assignee_pk(self) -> int | None:
        return getattr(self, "assignee_id", None)

    @property
    def status_label(self) -> str:
        return str(STATUS_LABELS.get(self.status, self.status))

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class FeedbackNote(models.Model):
    """A message on a ticket.

    ``internal`` decides the audience, and the filter is applied in the
    queryset — see ``services.visible_notes`` — so no serializer change can
    turn a staff note into a response field.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    ticket = models.ForeignKey(
        FeedbackTicket,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name=_("ticket"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="feedback_notes",
        verbose_name=_("author"),
    )
    body = models.TextField(_("body"))
    internal = models.BooleanField(
        _("internal only"),
        default=False,
        help_text=_("Staff-only. Never shown to the submitter."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("feedback note")
        verbose_name_plural = _("feedback notes")
        constraints = [
            models.CheckConstraint(
                condition=~Q(body=""), name="feedback_note_requires_body"
            )
        ]
        indexes = [
            models.Index(
                fields=["ticket", "internal", "created_at"], name="fb_note_scope_idx"
            )
        ]

    def __str__(self) -> str:
        return f"note on {getattr(self, 'ticket_id', None)}"


class FeedbackScreenshot(models.Model):
    """An image the submitter attached, in protected storage.

    Screenshots are the most sensitive thing this module stores: a picture of a
    broken page routinely contains another person's record. There is no public
    URL and no signed link that could outlive the reader's access — the file is
    streamed by a view that re-checks the parent ticket every time.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    ticket = models.ForeignKey(
        FeedbackTicket,
        on_delete=models.CASCADE,
        related_name="screenshots",
        verbose_name=_("ticket"),
    )
    image = models.FileField(
        _("image"), upload_to=screenshot_upload_to, storage=private_storage
    )
    display_name = models.CharField(_("display name"), max_length=200)
    media_type = models.CharField(_("media type"), max_length=100)
    byte_size = models.PositiveBigIntegerField(_("size in bytes"), default=0)
    checksum = models.CharField(_("checksum"), max_length=64, blank=True)
    width = models.PositiveIntegerField(_("width"), null=True, blank=True)
    height = models.PositiveIntegerField(_("height"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("feedback screenshot")
        verbose_name_plural = _("feedback screenshots")
        indexes = [models.Index(fields=["ticket"], name="fb_shot_ticket_idx")]

    def __str__(self) -> str:
        return self.display_name
