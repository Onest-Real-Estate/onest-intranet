"""IT support tickets, replies, and attachments.

Storage only. Every status change, assignment, and reply goes through
:mod:`apps.it_support.services` — the model deliberately has no ``save()``
override and no signal that mutates lifecycle state, because a workflow that
needs an actor, an expected-state check, and an audit trail cannot be
reconstructed from "the row changed".

Two visibility rules are enforced in the queryset rather than in a serializer,
because a filter applied after the fact leaks through counts and totals even
when it hides the row:

* :meth:`TicketQuerySet.for_reader` decides who may see a ticket at all.
* ``TicketReply.internal`` is an authorization boundary, not a display hint.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.it_support.taxonomy import (
    CATEGORY_CHOICES,
    CONTACT_METHOD_CHOICES,
    OPEN_STATUSES,
    PRIORITY_CHOICES,
    STATUS_CHOICES,
    STATUS_LABELS,
    TERMINAL_STATUSES,
    ContactMethod,
    SupportPriority,
    SupportStatus,
)
from apps.user.models import Office
from apps.user.storage import private_storage

_TERMINAL: list[str] = sorted(TERMINAL_STATUSES)


def attachment_upload_to(instance: TicketAttachment, filename: str) -> str:
    """Private, unguessable, and namespaced by the ticket's public id.

    Never the primary key: an object key carrying a sequential id tells a
    holder of one URL how many tickets exist and what to try next.
    """
    suffix = filename.rsplit("/", 1)[-1][:120]
    return f"it-support/{instance.ticket.public_id}/{instance.public_id}/{suffix}"


class TicketQuerySet(models.QuerySet["SupportTicket"]):
    def open(self) -> TicketQuerySet:
        return self.filter(status__in=OPEN_STATUSES)

    def unassigned(self) -> TicketQuerySet:
        return self.open().filter(assignee__isnull=True)

    def for_reader(self, user, *, access, can_triage: bool = False) -> TicketQuerySet:
        """The tickets this reader may see, applied before anything else.

        Two audiences, deliberately different:

        * **Everybody** sees the tickets they raised and the tickets raised
          *about* them — a new agent should be able to watch their own account
          setup without holding an IT grant.
        * **A triager** additionally sees every ticket inside their office
          reach. Without the grant, office reach buys nothing: being a branch
          manager is not a reason to read a colleague's password problem.

        This is the only place ticket visibility is decided. Callers must never
        follow it with a Python-side filter.
        """
        if getattr(user, "is_anonymous", False):
            return self.none()

        mine = Q(submitter=user) | Q(about_user=user)
        if not can_triage:
            return self.filter(mine)
        if getattr(user, "is_superuser", False) or access.company_wide:
            return self.all()

        reach = Q(pk__in=[])
        if access.office_keys:
            reach |= Q(office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            reach |= Q(office__region__stable_key__in=sorted(access.region_keys))
        return self.filter(reach | mine).distinct()


class SupportTicket(models.Model):
    """One request for IT help."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    #: Human reference used in conversation and email subjects ("ITS-000412").
    #: Derived from the primary key after insert so it is stable and unique
    #: without a second sequence to keep in step.
    reference = models.CharField(_("reference"), max_length=16, unique=True, blank=True)

    subject = models.CharField(_("subject"), max_length=160)
    description = models.TextField(_("description"))
    category = models.CharField(_("category"), max_length=32, choices=CATEGORY_CHOICES)

    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="submitted_support_tickets",
        verbose_name=_("submitted by"),
    )
    #: Who the ticket is *about*, when that is not the submitter — a branch
    #: admin raising "set up Jane's accounts" is the common case. Nullable
    #: because most tickets are about the person filing them.
    about_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets_about_me",
        verbose_name=_("about"),
    )
    #: Snapshotted from the submitter at creation, never accepted from the
    #: client. Scope is read from it, so a posted office id would be a way to
    #: file into somebody else's queue.
    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="support_tickets",
        verbose_name=_("office"),
    )
    #: Free-text where the person actually is, when it matters ("Branford front
    #: desk"). Not a foreign key: a floor or a desk is not an authorization
    #: subject, and modelling one would invite somebody to authorize from it.
    location = models.CharField(_("location"), max_length=120, blank=True)

    status = models.CharField(
        _("status"), max_length=20, choices=STATUS_CHOICES, default=SupportStatus.NEW
    )
    priority = models.PositiveSmallIntegerField(
        _("priority"), choices=PRIORITY_CHOICES, default=SupportPriority.NORMAL
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
        verbose_name=_("assigned to"),
    )

    preferred_contact = models.CharField(
        _("preferred contact"),
        max_length=16,
        choices=CONTACT_METHOD_CHOICES,
        default=ContactMethod.HUB,
    )
    #: What the browser reported, plus anything the submitter typed about their
    #: device. Free text on purpose: "the laptop with the cracked lid" is more
    #: useful to IT than a parsed user-agent, and neither is trusted input.
    device_info = models.CharField(_("device / browser"), max_length=300, blank=True)
    page_url = models.CharField(_("page"), max_length=2000, blank=True)

    #: Collapses a double-submitted form to one ticket. Supplied by the client
    #: per form render, so a retry, a double click, and a replayed POST all
    #: land on the same row.
    submission_key = models.CharField(
        _("submission key"), max_length=64, blank=True, db_index=True
    )

    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = TicketQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("support ticket")
        verbose_name_plural = _("support tickets")
        constraints = [
            # A closed ticket has a closing timestamp and a live one does not.
            # Stated in the database because several call sites read
            # ``closed_at`` to decide whether the work is finished.
            models.CheckConstraint(
                condition=(
                    Q(status__in=_TERMINAL, closed_at__isnull=False)
                    | (~Q(status__in=_TERMINAL) & Q(closed_at__isnull=True))
                ),
                name="it_support_closed_at_matches_status",
            ),
            models.CheckConstraint(
                condition=~Q(subject=""), name="it_support_requires_subject"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "priority"], name="its_status_priority_idx"),
            models.Index(fields=["office", "status"], name="its_office_status_idx"),
            models.Index(fields=["assignee", "status"], name="its_assignee_status_idx"),
            models.Index(fields=["submitter", "status"], name="its_submitter_idx"),
            models.Index(fields=["category"], name="its_category_idx"),
            models.Index(fields=["submission_key"], name="its_submission_key_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.reference or 'ITS-?'} {self.subject}"

    # Django generates these ``*_id`` attributes at runtime, but the type
    # checker cannot see them through a string-referenced ``AUTH_USER_MODEL``
    # foreign key. These read the same column without dereferencing the
    # relation — comparing ids must never cost a query.
    @property
    def submitter_pk(self) -> int | None:
        return getattr(self, "submitter_id", None)

    @property
    def about_user_pk(self) -> int | None:
        return getattr(self, "about_user_id", None)

    @property
    def assignee_pk(self) -> int | None:
        return getattr(self, "assignee_id", None)

    @property
    def status_label(self) -> str:
        return str(STATUS_LABELS.get(self.status, self.status))

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def concerns(self, user) -> bool:
        """Whether this ticket is the given person's own business.

        Both halves matter: the submitter owns the conversation they started,
        and the person being set up owns the request made on their behalf.
        """
        pk = getattr(user, "pk", None)
        return pk is not None and pk in {self.submitter_pk, self.about_user_pk}


class TicketReply(models.Model):
    """One message on a ticket.

    ``internal`` is an authorization boundary, not a display hint. An internal
    note is never serialized to a reader who lacks the note grant — the filter
    is applied in the queryset, before the payload exists, so there is no shape
    of the response that could leak one.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="replies",
        verbose_name=_("ticket"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="support_ticket_replies",
        verbose_name=_("author"),
    )
    body = models.TextField(_("body"))
    internal = models.BooleanField(
        _("internal only"),
        default=False,
        help_text=_("IT-only. Never shown to the requester."),
    )
    #: Marks the reply that closed the loop, so the detail page can lead with
    #: "here is what was done" instead of making the reader scroll a thread.
    is_resolution = models.BooleanField(_("resolution note"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("ticket reply")
        verbose_name_plural = _("ticket replies")
        constraints = [
            models.CheckConstraint(
                condition=~Q(body=""), name="it_support_reply_requires_body"
            ),
            # A resolution note is what the requester is told; an internal note
            # is what they are not. One row cannot be both.
            models.CheckConstraint(
                condition=~(Q(internal=True) & Q(is_resolution=True)),
                name="it_support_resolution_is_not_internal",
            ),
        ]
        indexes = [
            models.Index(
                fields=["ticket", "internal", "created_at"], name="its_reply_scope_idx"
            )
        ]

    def __str__(self) -> str:
        return f"reply on ticket {getattr(self, 'ticket_id', None)}"


class TicketAttachment(models.Model):
    """A file on a ticket, in protected storage.

    The file field uses ``private_storage``, so the object has no public URL
    and is reachable only through the download view, which re-authorizes the
    reader against the parent ticket on every request.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("ticket"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="support_ticket_attachments",
        verbose_name=_("uploaded by"),
    )
    file = models.FileField(
        _("file"),
        upload_to=attachment_upload_to,
        storage=private_storage,
        # The generated key is two UUIDs and a prefix before the name even
        # starts, so Django's default of 100 leaves no room for a filename and
        # every upload fails at storage time.
        max_length=255,
    )
    display_name = models.CharField(_("display name"), max_length=200)
    media_type = models.CharField(_("media type"), max_length=100, blank=True)
    byte_size = models.PositiveBigIntegerField(_("size in bytes"), default=0)
    #: IT-only files follow the same rule as internal notes.
    internal = models.BooleanField(_("internal only"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("ticket attachment")
        verbose_name_plural = _("ticket attachments")
        indexes = [
            models.Index(fields=["ticket", "internal"], name="its_att_scope_idx")
        ]

    def __str__(self) -> str:
        return self.display_name
