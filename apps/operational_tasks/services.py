"""The only place a task's lifecycle may change.

Every mutation here follows the same shape:

1. authorize the actor against the *stored* row, never a client-supplied one;
2. take a row lock and re-read, so two racing writers serialize;
3. check the caller's expected state, so the second of two racing writers is
   told it lost rather than silently overwriting the first;
4. write, stamp the timestamps that go with the move, and record an audit
   event with the before/after;
5. schedule notifications on commit, keyed so a retry cannot duplicate them.

Step 3 is what makes the API safe for a UI: a stale board that still shows
"Open" cannot drag a task that somebody else already resolved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit.service import (
    actor_from_user,
    log_on_commit,
    snapshot_model,
    target_from_instance,
)
from apps.operational_tasks.models import (
    OperationalTask,
    TaskAttachment,
    TaskComment,
)
from apps.operational_tasks.taxonomy import (
    CATEGORY_CODES,
    PRIORITY_CODES,
    SOURCE_CODES,
    TaskPermission,
    TaskSource,
    TaskStatus,
    Transition,
    find_transition,
    transitions_from,
)

logger = logging.getLogger("apps.operational_tasks")

#: "No opinion", distinct from an explicit ``None`` meaning "I believe this is
#: unassigned". Both are real inputs, so they need different values. Public
#: because an HTTP caller has to be able to say "the form sent no opinion".
UNSET: object = object()

#: What may be attached, and what each one is served as.
#:
#: Deliberately the same allowlist the office resource module uses: an
#: extension this hub refuses to serve anywhere else must not become servable
#: because it arrived through a support queue.
#:
#: The media type is stated here rather than read from :mod:`mimetypes`, which
#: consults the host's own MIME database — macOS maps ``.log`` to ``text/plain``
#: and a bare Linux container does not. A stored type that depends on which
#: machine accepted the upload is a header we would later serve back, so the
#: table is code-owned and the same everywhere.
ATTACHMENT_MEDIA_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".log": "text/plain",
    ".json": "application/json",
}

#: Derived, so the allowlist and the served type can never disagree.
ALLOWED_ATTACHMENT_EXTENSIONS: frozenset[str] = frozenset(ATTACHMENT_MEDIA_TYPES)
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
#: Per task, not per upload. A support queue collects evidence, not a document
#: library, and an unbounded count turns one task into a storage bill.
MAX_ATTACHMENTS_PER_TASK = 10

#: Fields the audit trail snapshots. Deliberately excludes ``description`` and
#: comment bodies: an audit record is a statement about *what changed*, and
#: copying free text into it creates a second, unscoped copy of content the
#: task's own permissions were protecting.
#: Field *names*, not column names: ``model_to_dict`` keys by the former, and
#: a relation is captured as its primary key.
AUDIT_FIELDS = [
    "reference",
    "category",
    "status",
    "priority",
    "source",
    "office",
    "assignee",
    "team",
    "due_at",
]


class TransitionError(ValidationError):
    """The requested move is not legal from the task's current state."""


class ConcurrentUpdate(ValidationError):
    """Somebody else moved the task since the caller last read it."""


@dataclass(frozen=True)
class ActorContext:
    """Who is acting, and what they hold.

    ``permissions`` is the effective set already resolved for the request, so
    the service never re-derives access and never has to hit the database to
    answer an authorization question mid-transaction.
    """

    user: Any
    permissions: frozenset[str]

    def holds(self, *codenames: str) -> bool:
        if getattr(self.user, "is_superuser", False):
            return True
        return any(code in self.permissions for code in codenames)


def _require(actor: ActorContext, *codenames: str) -> None:
    if not actor.holds(*codenames):
        raise PermissionDenied("You do not have permission to change this task.")


def next_reference(pk: int) -> str:
    return f"TSK-{pk:06d}"


def available_transitions(
    task: OperationalTask, actor: ActorContext
) -> list[Transition]:
    """Legal moves this actor could make right now.

    The UI renders from this, and :func:`transition` re-checks every element of
    it — the list is a convenience, never the authorization.
    """
    is_assignee = task.assignee_pk is not None and task.assignee_pk == getattr(
        actor.user, "pk", None
    )
    allowed: list[Transition] = []
    for candidate in transitions_from(task.status):
        if actor.holds(*candidate.permissions) or candidate.by_assignee and is_assignee:
            allowed.append(candidate)
    return allowed


@transaction.atomic
def create_task(
    *,
    actor: ActorContext,
    office,
    category: str,
    title: str,
    description: str = "",
    priority: int,
    assignee=None,
    team: str = "",
    due_at=None,
    tags: list[str] | None = None,
    source: str = TaskSource.MANUAL,
    source_reference: str = "",
    related_object_type: str = "",
    related_object_id: str = "",
    reporter=None,
    visible_to: list | None = None,
) -> OperationalTask:
    """Create one task, idempotently for a converted source.

    A conversion carrying ``source_reference`` returns the existing task rather
    than making a second one. That is the acceptance criterion "duplicate
    conversion does not create duplicate tasks", and it is enforced here rather
    than at the call site so a retried Celery task, a double-clicked button,
    and a replayed event all land on the same row.
    """
    _require(actor, TaskPermission.MANAGE)

    if category not in CATEGORY_CODES:
        raise ValidationError({"category": ["Unknown task category."]})
    if priority not in PRIORITY_CODES:
        raise ValidationError({"priority": ["Unknown priority."]})
    if source not in SOURCE_CODES:
        raise ValidationError({"source": ["Unknown source."]})
    if not (title or "").strip():
        raise ValidationError({"title": ["A task needs a title."]})
    if assignee is not None:
        _require(actor, TaskPermission.ASSIGN, TaskPermission.MANAGE)

    if source_reference:
        existing = (
            OperationalTask.objects.select_for_update(of=("self",))
            .filter(source=source, source_reference=source_reference)
            .first()
        )
        if existing is not None:
            logger.info(
                "operational_tasks: conversion for %s/%s already exists as %s",
                source,
                source_reference,
                existing.reference,
            )
            return existing

    task = OperationalTask.objects.create(
        category=category,
        title=title.strip()[:200],
        description=description,
        priority=priority,
        office=office,
        assignee=assignee,
        team=team.strip()[:60],
        reporter=reporter if reporter is not None else actor.user,
        due_at=due_at,
        tags=[str(tag)[:40] for tag in (tags or [])][:12],
        source=source,
        source_reference=source_reference,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
        status=TaskStatus.OPEN,
    )
    # The reference needs the primary key, so it is a second write rather than
    # a second sequence to keep in step with the first.
    task.reference = next_reference(task.pk)
    task.save(update_fields=["reference", "updated_at"])
    if visible_to:
        task.visible_to.set(visible_to)

    log_on_commit(
        action="operational_task.created",
        actor=actor_from_user(actor.user),
        target=target_from_instance(task, label=task.reference),
        metadata={"category": category, "priority": priority, "source": source},
    )
    _notify_on_commit(task, "assigned" if task.assignee_pk else "created", actor)
    return task


@transaction.atomic
def transition(
    *,
    actor: ActorContext,
    task: OperationalTask,
    to_status: str,
    expected_status: str | None = None,
    note: str = "",
) -> OperationalTask:
    """Move a task, or explain why it cannot move.

    ``expected_status`` is the caller's view of the world. When it disagrees
    with the row under lock, the caller is told it lost the race instead of
    overwriting a decision it never saw.
    """
    locked = (
        OperationalTask.objects.select_for_update(of=("self",))
        .filter(pk=task.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("This task no longer exists.")

    if expected_status is not None and locked.status != expected_status:
        raise ConcurrentUpdate(
            {
                "status": [
                    "Somebody else moved this task while you were working on it. "
                    f"It is now “{locked.status_label}”. Reload to continue."
                ]
            }
        )

    if locked.status == to_status:
        # Idempotent by design: a retried request or a double submit is not an
        # error, and must not write a second audit event or a second notice.
        return locked

    move = find_transition(locked.status, to_status)
    if move is None:
        raise TransitionError(
            {"status": [f"“{locked.status_label}” cannot move straight to that state."]}
        )

    is_assignee = locked.assignee_pk == getattr(actor.user, "pk", None)
    if not actor.holds(*move.permissions) and not (move.by_assignee and is_assignee):
        raise PermissionDenied("You do not have permission to make that change.")

    if move.requires_note and not (note or "").strip():
        raise ValidationError(
            {"note": ["Explain the change so the next reader knows what happened."]}
        )

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    now = timezone.now()
    updates = ["status", "updated_at"]
    locked.status = to_status

    if to_status == TaskStatus.IN_PROGRESS and locked.started_at is None:
        locked.started_at = now
        updates.append("started_at")
    if to_status == TaskStatus.RESOLVED:
        locked.resolved_at = now
        updates.append("resolved_at")
    if move.closes:
        locked.closed_at = now
        updates.append("closed_at")
    if move.reopens:
        locked.closed_at = None
        locked.resolved_at = None
        updates.extend(["closed_at", "resolved_at"])

    locked.save(update_fields=sorted(set(updates)))

    if note.strip():
        # The explanation belongs to staff: it is the reason for an internal
        # decision, and the reporter is told the outcome by notification.
        TaskComment.objects.create(
            task=locked, author=actor.user, body=note.strip(), internal=True
        )

    after = snapshot_model(locked, fields=AUDIT_FIELDS)
    log_on_commit(
        action="operational_task.status_changed",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        metadata={"from": before.get("status"), "to": after.get("status")},
        before=before,
        after=after,
    )
    _notify_on_commit(locked, f"status:{to_status}", actor)
    return locked


@transaction.atomic
def assign(
    *,
    actor: ActorContext,
    task: OperationalTask,
    assignee,
    expected_assignee_id: int | None | object = UNSET,
) -> OperationalTask:
    """Set or clear the assignee.

    ``expected_assignee_id`` defaults to ``UNSET`` meaning "do not check".
    An explicit ``None`` means "I believe this is unassigned", which is a real
    claim worth verifying — ``None`` cannot double as "no opinion".
    """
    _require(actor, TaskPermission.ASSIGN, TaskPermission.MANAGE)

    locked = (
        OperationalTask.objects.select_for_update(of=("self",))
        .filter(pk=task.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("This task no longer exists.")
    if locked.is_terminal:
        raise ValidationError(
            {"assignee": ["A closed task cannot be reassigned. Reopen it first."]}
        )
    if expected_assignee_id is not UNSET and locked.assignee_pk != expected_assignee_id:
        raise ConcurrentUpdate(
            {"assignee": ["Somebody else reassigned this task. Reload to continue."]}
        )

    new_id = getattr(assignee, "pk", None)
    if locked.assignee_pk == new_id:
        return locked

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    locked.assignee = assignee
    locked.save(update_fields=["assignee", "updated_at"])
    after = snapshot_model(locked, fields=AUDIT_FIELDS)

    log_on_commit(
        action="operational_task.assigned",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        metadata={"from": before.get("assignee"), "to": after.get("assignee")},
        before=before,
        after=after,
    )
    if new_id is not None:
        _notify_on_commit(locked, "assigned", actor)
    return locked


@transaction.atomic
def add_comment(
    *, actor: ActorContext, task: OperationalTask, body: str, internal: bool = False
) -> TaskComment:
    """Comment on a task.

    Writing an *internal* note needs the management grant; an ordinary comment
    needs only the comment grant. Somebody who can discuss a task with the
    reporter is not thereby allowed to write in the staff-only channel.
    """
    if internal:
        _require(actor, TaskPermission.MANAGE)
    else:
        _require(actor, TaskPermission.COMMENT, TaskPermission.MANAGE)

    text = (body or "").strip()
    if not text:
        raise ValidationError({"body": ["Write something before posting."]})

    comment = TaskComment.objects.create(
        task=task, author=actor.user, body=text, internal=internal
    )
    log_on_commit(
        action="operational_task.commented",
        actor=actor_from_user(actor.user),
        target=target_from_instance(task, label=task.reference),
        metadata={"internal": internal},
    )
    if not internal:
        _notify_on_commit(task, "commented", actor)
    return comment


def visible_comments(task: OperationalTask, actor: ActorContext):
    """Comments this actor may read — filtered in the queryset, not after.

    An internal note must never reach a payload builder that might serialize
    it by accident, so the exclusion happens here, once, and every caller goes
    through it.
    """
    queryset = (
        TaskComment.objects.filter(task=task)
        .select_related("author")
        .order_by("created_at", "pk")
    )
    if actor.holds(TaskPermission.MANAGE):
        return queryset
    return queryset.filter(internal=False)


@transaction.atomic
def attach_file(
    *,
    actor: ActorContext,
    task: OperationalTask,
    uploaded,
    internal: bool = False,
) -> TaskAttachment:
    """Store one file against a task, in protected storage.

    An *internal* file follows the internal-note rule exactly: writing one
    needs the management grant, and :func:`visible_attachments` excludes it
    from every reader who lacks that grant. An ordinary attachment needs the
    comment grant — somebody who may discuss a task may also show what they
    are talking about.

    The extension is judged against a closed allowlist and the size against a
    ceiling *before* anything is written, and the stored media type is derived
    from the name the server accepted rather than the ``Content-Type`` the
    client claimed: a header is the uploader's assertion, not a fact.
    """
    if internal:
        _require(actor, TaskPermission.MANAGE)
    else:
        _require(actor, TaskPermission.COMMENT, TaskPermission.MANAGE)

    if uploaded is None:
        raise ValidationError({"file": ["Choose a file to attach."]})
    if task.is_terminal:
        raise ValidationError(
            {"file": ["This task is closed. Reopen it before attaching anything."]}
        )

    name = Path(uploaded.name or "").name
    extension = Path(name).suffix.lower()
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValidationError(
            {"file": [f"File type “{extension or 'unknown'}” is not allowed."]}
        )
    if uploaded.size > MAX_ATTACHMENT_BYTES:
        raise ValidationError({"file": ["Files must be 10 MB or smaller."]})
    if TaskAttachment.objects.filter(task=task).count() >= MAX_ATTACHMENTS_PER_TASK:
        raise ValidationError(
            {
                "file": [
                    f"A task holds at most {MAX_ATTACHMENTS_PER_TASK} files. "
                    "Remove one before adding another."
                ]
            }
        )

    uploaded.seek(0)
    data = uploaded.read()
    attachment = TaskAttachment(
        task=task,
        uploaded_by=actor.user,
        display_name=name[:200],
        # From the extension the allowlist just accepted, so the stored type is
        # the same on every host and never the ``Content-Type`` the client
        # claimed — a header is the uploader's assertion, not a fact.
        media_type=ATTACHMENT_MEDIA_TYPES[extension],
        byte_size=len(data),
        internal=internal,
    )
    attachment.file.save(name, ContentFile(data), save=False)
    attachment.save()

    log_on_commit(
        action="operational_task.attachment_added",
        actor=actor_from_user(actor.user),
        target=target_from_instance(task, label=task.reference),
        # The file name only. The bytes stay where the task's own permissions
        # protect them, and an audit row is read by a wider audience.
        metadata={"fileName": attachment.display_name, "internal": internal},
    )
    return attachment


def load_attachment(
    *, task: OperationalTask, actor: ActorContext, public_id
) -> TaskAttachment | None:
    """One attachment, looked up *inside* what this actor may already read.

    Resolved through :func:`visible_attachments` rather than by bare id, so an
    internal file is indistinguishable from one that does not exist for a
    reader without the management grant. A later ``if attachment.internal``
    check would answer the same question with a different status code, and
    that difference is the disclosure.
    """
    return visible_attachments(task, actor).filter(public_id=public_id).first()


def visible_attachments(task: OperationalTask, actor: ActorContext):
    queryset = (
        TaskAttachment.objects.filter(task=task)
        .select_related("uploaded_by")
        .order_by("created_at")
    )
    if actor.holds(TaskPermission.MANAGE):
        return queryset
    return queryset.filter(internal=False)


def _notify_on_commit(task: OperationalTask, event: str, actor: ActorContext) -> None:
    """Hand the event to the notification module after the row is durable.

    Keyed by task, event, and the row's ``updated_at`` so a retried request
    that lands on an unchanged row produces the same key and is collapsed
    rather than delivered twice.
    """
    from apps.operational_tasks.notifications import queue_task_notice

    stamp = task.updated_at.isoformat()
    dedupe_key = f"operational_task:{task.public_id}:{event}:{stamp}"
    transaction.on_commit(
        lambda: queue_task_notice(
            task_id=task.pk,
            event=event,
            dedupe_key=dedupe_key,
            actor_id=getattr(actor.user, "pk", None),
        )
    )


def convert_from_feedback(
    *,
    actor: ActorContext,
    feedback_reference: str,
    office,
    category: str,
    title: str,
    description: str = "",
    priority: int,
    reporter=None,
) -> OperationalTask:
    """Create the task that a feedback ticket asked for.

    Idempotent on ``feedback_reference`` through :func:`create_task`, and it
    copies **no** attachment URL: a feedback screenshot lives in the feedback
    module's protected storage under the feedback module's policy, and a task
    reader is not automatically entitled to it. The link back is the reference,
    which the feedback module re-authorizes on its own side.

    The feedback module calls this seam through
    ``apps.feedback.services.convert_to_task``, which additionally records the
    resulting task id on the ticket so its own side is idempotent too.
    """
    return create_task(
        actor=actor,
        office=office,
        category=category,
        title=title,
        description=description,
        priority=priority,
        source=TaskSource.FEEDBACK,
        source_reference=feedback_reference,
        reporter=reporter,
    )
