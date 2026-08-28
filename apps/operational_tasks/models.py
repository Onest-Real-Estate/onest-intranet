"""Operational task records, comments, and attachments.

Storage only. Every status change, assignment, and closure goes through
:mod:`apps.operational_tasks.services` — the model deliberately has no
``save()`` override and no signal that mutates lifecycle state, because a
workflow that needs an actor, an expected-state check, and an audit trail
cannot be reconstructed from "the row changed".

Scope follows the office tree the same way announcements and office resources
do: ``office`` is the owning node, and a reader with region or company reach
sees the nodes beneath theirs. ``visible_to`` is the narrow escape hatch for
letting one named person see a task outside their office scope — an agent who
reported it, typically — without widening their reach to anything else.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.operational_tasks.taxonomy import (
    ACTIVE_STATUSES,
    CATEGORY_CHOICES,
    PRIORITY_CHOICES,
    SOURCE_CHOICES,
    STATUS_CHOICES,
    STATUS_LABELS,
    TERMINAL_STATUSES,
    TaskPriority,
    TaskSource,
    TaskStatus,
)
from apps.user.models import Office
from apps.user.storage import private_storage

#: Sorted once so the generated constraint SQL is stable across runs; an
#: unordered set here would rewrite the migration on every makemigrations.
_TERMINAL: list[str] = sorted(TERMINAL_STATUSES)


def attachment_upload_to(instance: TaskAttachment, filename: str) -> str:
    """Private, unguessable, and namespaced by the task's public id.

    Never the primary key: an object key that leaks a sequential id tells a
    holder of one URL how many tasks exist and what to try next.
    """
    suffix = filename.rsplit("/", 1)[-1][:120]
    return f"operational-tasks/{instance.task.public_id}/{instance.public_id}/{suffix}"


class TaskQuerySet(models.QuerySet["OperationalTask"]):
    def active(self) -> TaskQuerySet:
        return self.filter(status__in=ACTIVE_STATUSES)

    def terminal(self) -> TaskQuerySet:
        return self.filter(status__in=TERMINAL_STATUSES)

    def overdue(self, *, at=None) -> TaskQuerySet:
        """Past due *and* still live.

        A closed task that missed its date is history, not a problem: counting
        it would make every overdue figure grow forever.
        """
        return self.active().filter(due_at__lt=at or timezone.now())

    def for_reader(self, user, *, access) -> TaskQuerySet:
        """The rows this reader may see, applied before anything else.

        Ordered widest-wins: company reach short-circuits, then the office
        tree, then the two personal grants that never widen org reach —
        reported by me, assigned to me, or explicitly shared with me.

        This is the only place task visibility is decided. Callers must never
        follow it with a Python-side filter: a later check leaks existence
        through counts, pagination totals, and search results.
        """
        if getattr(user, "is_anonymous", False):
            return self.none()

        personal = Q(reporter=user) | Q(assignee=user) | Q(visible_to=user)
        if getattr(user, "is_superuser", False) or access.company_wide:
            return self.all()

        reach = Q(pk__in=[])
        if access.office_keys:
            reach |= Q(office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            reach |= Q(office__region__stable_key__in=sorted(access.region_keys))
        return self.filter(reach | personal).distinct()


class OperationalTask(models.Model):
    """One piece of internal operational work."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    #: Human reference used in conversation and email subjects ("TSK-000412").
    #: Derived from the primary key after insert so it is stable and unique
    #: without a second sequence to keep in step.
    reference = models.CharField(_("reference"), max_length=16, unique=True, blank=True)

    category = models.CharField(_("category"), max_length=40, choices=CATEGORY_CHOICES)
    title = models.CharField(_("title"), max_length=200)
    description = models.TextField(_("description"), blank=True)

    source = models.CharField(
        _("source"),
        max_length=20,
        choices=SOURCE_CHOICES,
        default=TaskSource.MANUAL,
    )
    #: Stable identity of the originating record, e.g. a feedback ticket's
    #: public id. Held as an opaque string so converting from a module that
    #: does not exist yet needs no schema change and no foreign key to it.
    source_reference = models.CharField(
        _("source reference"), max_length=64, blank=True, db_index=True
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="operational_tasks",
        verbose_name=_("owning office"),
        help_text=_("The node that owns this work. Scope is read from it."),
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_operational_tasks",
        verbose_name=_("assignee"),
    )
    #: Free-text team label. Deliberately not a foreign key: teams here are an
    #: operational grouping ("IT", "Onboarding"), not an authorization subject,
    #: and modelling them as one would invite somebody to authorize from it.
    team = models.CharField(_("team"), max_length=60, blank=True)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_operational_tasks",
        verbose_name=_("reporter"),
    )
    visible_to = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="visible_operational_tasks",
        verbose_name=_("explicitly visible to"),
        help_text=_(
            "People who may read this task regardless of office scope. Grants "
            "read access to this record only and widens nothing else."
        ),
    )

    priority = models.PositiveSmallIntegerField(
        _("priority"), choices=PRIORITY_CHOICES, default=TaskPriority.NORMAL
    )
    status = models.CharField(
        _("status"), max_length=20, choices=STATUS_CHOICES, default=TaskStatus.OPEN
    )
    due_at = models.DateTimeField(_("due at"), null=True, blank=True)

    #: Opaque pointer to whatever the task is about. Never dereferenced for
    #: authorization: the related record's own policy decides who may open it.
    related_object_type = models.CharField(
        _("related object type"), max_length=60, blank=True
    )
    related_object_id = models.CharField(
        _("related object id"), max_length=64, blank=True
    )

    tags = models.JSONField(_("tags"), default=list, blank=True)

    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("operational task")
        verbose_name_plural = _("operational tasks")
        permissions = ()
        constraints = [
            # A terminal task has a closing timestamp and a live one does not.
            # Stated in the database because three different call sites read
            # ``closed_at`` to decide whether work is finished.
            models.CheckConstraint(
                condition=(
                    Q(status__in=_TERMINAL, closed_at__isnull=False)
                    | (~Q(status__in=_TERMINAL) & Q(closed_at__isnull=True))
                ),
                name="operational_task_closed_at_matches_status",
            ),
            models.CheckConstraint(
                condition=~Q(title=""),
                name="operational_task_requires_title",
            ),
            # Both halves of the related pointer, or neither. A type with no id
            # is not something any surface can resolve.
            models.CheckConstraint(
                condition=(
                    (Q(related_object_type="") & Q(related_object_id=""))
                    | (~Q(related_object_type="") & ~Q(related_object_id=""))
                ),
                name="operational_task_related_pointer_is_complete",
            ),
        ]
        indexes = [
            models.Index(fields=["office", "status"], name="optask_office_status_idx"),
            models.Index(
                fields=["assignee", "status"], name="optask_assignee_status_idx"
            ),
            models.Index(fields=["status", "due_at"], name="optask_status_due_idx"),
            models.Index(fields=["category"], name="optask_category_idx"),
            models.Index(
                fields=["source", "source_reference"], name="optask_source_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reference or 'TSK-?'} {self.title}"

    # Django generates ``assignee_id``/``reporter_id`` at runtime, but the
    # type checker cannot see them through a string-referenced
    # ``AUTH_USER_MODEL`` foreign key. These read the same column without
    # dereferencing the relation — comparing ids must never cost a query.
    @property
    def assignee_pk(self) -> int | None:
        return getattr(self, "assignee_id", None)

    @property
    def reporter_pk(self) -> int | None:
        return getattr(self, "reporter_id", None)

    @property
    def status_label(self) -> str:
        return str(STATUS_LABELS.get(self.status, self.status))

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def is_overdue(self, *, at=None) -> bool:
        if self.due_at is None or self.is_terminal:
            return False
        return self.due_at < (at or timezone.now())


class TaskComment(models.Model):
    """A comment on a task.

    ``internal`` is an authorization boundary, not a display hint. An internal
    note is never serialized to a reader who lacks the management grant — the
    filter is applied in the queryset, before the payload exists, so there is
    no shape of the response that could leak one.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    task = models.ForeignKey(
        OperationalTask,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("task"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="operational_task_comments",
        verbose_name=_("author"),
    )
    body = models.TextField(_("body"))
    internal = models.BooleanField(
        _("internal only"),
        default=False,
        help_text=_("Staff-only. Never shown to the reporter or a shared reader."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("task comment")
        verbose_name_plural = _("task comments")
        constraints = [
            models.CheckConstraint(
                condition=~Q(body=""), name="operational_task_comment_requires_body"
            )
        ]
        indexes = [
            models.Index(
                fields=["task", "internal", "created_at"], name="optask_cmt_scope_idx"
            )
        ]

    def __str__(self) -> str:
        return f"comment on task {getattr(self, 'task_id', None)}"


class TaskAttachment(models.Model):
    """A file on a task, in protected storage.

    The file field uses ``private_storage``, so the object has no public URL
    and is reachable only through the download view, which re-authorizes the
    reader against the parent task on every request.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    task = models.ForeignKey(
        OperationalTask,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("task"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="operational_task_attachments",
        verbose_name=_("uploaded by"),
    )
    file = models.FileField(
        _("file"), upload_to=attachment_upload_to, storage=private_storage
    )
    display_name = models.CharField(_("display name"), max_length=200)
    media_type = models.CharField(_("media type"), max_length=100, blank=True)
    byte_size = models.PositiveBigIntegerField(_("size in bytes"), default=0)
    #: Staff-only files follow the same rule as internal notes.
    internal = models.BooleanField(_("internal only"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("task attachment")
        verbose_name_plural = _("task attachments")
        indexes = [
            models.Index(fields=["task", "internal"], name="optask_att_scope_idx")
        ]

    def __str__(self) -> str:
        return self.display_name
