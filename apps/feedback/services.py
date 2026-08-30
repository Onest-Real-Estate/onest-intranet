"""The only place a ticket is created or changed.

Submission and triage are two different jobs with two different threat models,
so they are separated here:

* **Submission** is open to every authenticated person and is therefore the
  attack surface. It is rate limited, idempotent on a client-supplied key, and
  everything it stores about the browser has been through
  :mod:`apps.feedback.diagnostics` first.
* **Triage** needs granted capability, takes a row lock and an expected state,
  and writes an audit event for every move.

Conversion to an operational task is deliberately one-directional and copies
no file. The task module (P1-079) owns the work; this module keeps the
conversation with the person who reported it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.announcements.media import HERO_EXTENSIONS, inspect_upload
from apps.audit.service import (
    actor_from_user,
    log_on_commit,
    snapshot_model,
    target_from_instance,
)
from apps.feedback.diagnostics import build_diagnostics
from apps.feedback.models import FeedbackNote, FeedbackScreenshot, FeedbackTicket
from apps.feedback.taxonomy import (
    CATEGORY_CODES,
    PRIORITY_CODES,
    URGENCY_CODES,
    URGENCY_TO_PRIORITY,
    FeedbackPermission,
    FeedbackStatus,
    Transition,
    find_transition,
    transitions_from,
)

logger = logging.getLogger("apps.feedback")

#: Submissions one person may make inside the window. Generous on purpose: the
#: limit exists to stop a scripted flood, not to ration a frustrated agent
#: reporting three genuine problems in a row.
RATE_LIMIT_SUBMISSIONS = 8
RATE_LIMIT_WINDOW_SECONDS = 15 * 60

#: One screenshot. More than one is a document set, and this is a support form.
MAX_SCREENSHOTS = 1

AUDIT_FIELDS = [
    "reference",
    "category",
    "status",
    "priority",
    "urgency",
    "office",
    "assignee",
    "converted_task_id",
]


class RateLimited(ValidationError):
    """Too many submissions inside the window."""


class ConcurrentUpdate(ValidationError):
    """Somebody else moved the ticket since the caller last read it."""


class TransitionError(ValidationError):
    """The requested move is not legal from the ticket's current state."""


@dataclass(frozen=True)
class ActorContext:
    user: Any
    permissions: frozenset[str]

    def holds(self, *codenames: str) -> bool:
        if getattr(self.user, "is_superuser", False):
            return True
        return any(code in self.permissions for code in codenames)

    @property
    def can_triage(self) -> bool:
        return self.holds(FeedbackPermission.TRIAGE)


def _require(actor: ActorContext, *codenames: str) -> None:
    if not actor.holds(*codenames):
        raise PermissionDenied("You do not have permission to do that.")


def next_reference(pk: int) -> str:
    return f"FB-{pk:06d}"


def check_rate_limit(user, *, now: float | None = None) -> None:
    """Count this submission, refusing past the window's allowance.

    Keyed by user rather than IP: the hub is authenticated, so the person is
    the meaningful subject, and an office behind one NAT should not share a
    budget. Cache-backed, so a restart forgives.

    The message names the wait rather than saying "try again later", because a
    rate-limit error the reader cannot act on just becomes a support ticket
    about the support form.
    """
    key = f"feedback:rate:{getattr(user, 'pk', 'anon')}"
    moment = now if now is not None else time.monotonic()
    window = [
        stamp
        for stamp in (cache.get(key) or [])
        if moment - stamp < RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(window) >= RATE_LIMIT_SUBMISSIONS:
        oldest = min(window)
        minutes = max(1, int((RATE_LIMIT_WINDOW_SECONDS - (moment - oldest)) // 60) + 1)
        raise RateLimited(
            {
                "form": [
                    f"You have sent {RATE_LIMIT_SUBMISSIONS} reports recently. "
                    f"You can send another in about {minutes} minutes — or reply "
                    "on an existing ticket if this is about the same problem."
                ]
            }
        )
    window.append(moment)
    cache.set(key, window, RATE_LIMIT_WINDOW_SECONDS)


def attach_screenshot(ticket: FeedbackTicket, uploaded) -> FeedbackScreenshot:
    """Store one image after the server has read and judged it itself.

    Reuses the announcement media inspector, which checks extension, sniffs the
    real type from the leading bytes, and applies the decompression-bomb
    ceiling before any decode. A ``.png`` whose bytes are a script never
    reaches storage.
    """
    inspected, data = inspect_upload(uploaded, field="screenshot")
    if inspected.extension not in HERO_EXTENSIONS:
        raise ValidationError({"screenshot": ["Attach an image — PNG, JPEG, or WebP."]})

    from django.core.files.base import ContentFile

    shot = FeedbackScreenshot(
        ticket=ticket,
        display_name=inspected.display_name,
        media_type=inspected.media_type,
        byte_size=inspected.byte_size,
        checksum=inspected.checksum,
        width=inspected.width,
        height=inspected.height,
    )
    shot.image.save(inspected.display_name, ContentFile(data), save=False)
    shot.save()
    return shot


@transaction.atomic
def submit(
    *,
    user,
    submission_key: str,
    category: str,
    summary: str,
    description: str,
    urgency: str,
    page_url: str = "",
    browser_metadata: object = None,
    screenshot=None,
    allowed_hosts: set[str] | None = None,
    skip_rate_limit: bool = False,
) -> tuple[FeedbackTicket, bool]:
    """Create one ticket. Returns ``(ticket, created)``.

    Idempotent on ``submission_key``: a double-clicked button, a retried
    request, or a browser replaying the POST all return the first ticket.
    ``created`` tells the caller whether anything actually happened, so the
    view can avoid re-running side effects on a replay.

    No permission is required. Every authenticated person may report a problem
    with the tool they are told to use, and putting a grant in front of that
    would mean the people most likely to hit a permission bug are the ones who
    cannot report it.
    """
    key = (submission_key or "").strip()[:64]
    if not key:
        raise ValidationError({"form": ["That submission could not be identified."]})

    existing = FeedbackTicket.objects.filter(submission_key=key).first()
    if existing is not None:
        return existing, False

    if category not in CATEGORY_CODES:
        raise ValidationError({"category": ["Choose what kind of report this is."]})
    if urgency not in URGENCY_CODES:
        raise ValidationError({"urgency": ["Choose how urgent this is for you."]})
    if not (summary or "").strip():
        raise ValidationError({"summary": ["Give this a one-line summary."]})
    if not (description or "").strip():
        raise ValidationError({"description": ["Describe what happened."]})

    if not skip_rate_limit:
        check_rate_limit(user)

    diagnostics = build_diagnostics(
        page_url=page_url,
        metadata=browser_metadata,
        allowed_hosts=allowed_hosts or set(),
    )

    try:
        ticket = FeedbackTicket.objects.create(
            submission_key=key,
            category=category,
            summary=summary.strip()[:160],
            description=description.strip(),
            urgency=urgency,
            priority=URGENCY_TO_PRIORITY[urgency],
            submitter=user,
            office=getattr(user, "office", None),
            page_url=diagnostics.page_url,
            browser_metadata=diagnostics.metadata,
            status=FeedbackStatus.NEW,
        )
    except IntegrityError:
        # Two requests raced on the same key. The unique constraint is the
        # arbiter; the loser reads the winner's row rather than failing.
        winner = FeedbackTicket.objects.filter(submission_key=key).first()
        if winner is None:
            raise
        return winner, False

    ticket.reference = next_reference(ticket.pk)
    ticket.save(update_fields=["reference", "updated_at"])

    if screenshot is not None:
        attach_screenshot(ticket, screenshot)

    log_on_commit(
        action="feedback.submitted",
        actor=actor_from_user(user),
        target=target_from_instance(ticket, label=ticket.reference),
        # Deliberately no summary or description: an audit row is a statement
        # about what happened, and copying the body here would make a second,
        # differently-scoped copy of content the ticket's own policy protects.
        metadata={"category": category, "urgency": urgency},
    )
    _notify(ticket, "submitted", actor_id=getattr(user, "pk", None))
    return ticket, True


def available_transitions(
    ticket: FeedbackTicket, actor: ActorContext
) -> list[Transition]:
    """Legal moves this actor could make now. The service re-checks each one."""
    if not actor.can_triage:
        return []
    return [t for t in transitions_from(ticket.status) if actor.holds(*t.permissions)]


@transaction.atomic
def transition(
    *,
    actor: ActorContext,
    ticket: FeedbackTicket,
    to_status: str,
    expected_status: str | None = None,
    reply: str = "",
) -> FeedbackTicket:
    """Move a ticket, or explain why it cannot move."""
    _require(actor, FeedbackPermission.TRIAGE)

    locked = (
        FeedbackTicket.objects.select_for_update(of=("self",))
        .filter(pk=ticket.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("This ticket no longer exists.")

    if expected_status is not None and locked.status != expected_status:
        raise ConcurrentUpdate(
            {
                "status": [
                    "Somebody else updated this ticket while you were working "
                    f"on it. It is now “{locked.status_label}”. Reload to continue."
                ]
            }
        )

    if locked.status == to_status:
        # A retried request is not an error and must not write a second audit
        # event or send the submitter a second notice.
        return locked

    move = find_transition(locked.status, to_status)
    if move is None:
        raise TransitionError(
            {"status": [f"“{locked.status_label}” cannot move straight to that state."]}
        )
    if move.requires_reply and not (reply or "").strip():
        raise ValidationError(
            {
                "reply": [
                    "Say what you need from them — a request for information "
                    "with no question is a ticket that stalls."
                ]
            }
        )

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    now = timezone.now()
    updates = ["status", "updated_at"]
    locked.status = to_status
    if to_status == FeedbackStatus.RESOLVED:
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

    if reply.strip():
        # A reply attached to a transition is *for the submitter*: it is the
        # question or the explanation. Staff-only reasoning goes through
        # `add_note(internal=True)` instead.
        FeedbackNote.objects.create(
            ticket=locked, author=actor.user, body=reply.strip(), internal=False
        )

    after = snapshot_model(locked, fields=AUDIT_FIELDS)
    log_on_commit(
        action="feedback.status_changed",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        metadata={"from": before.get("status"), "to": after.get("status")},
        before=before,
        after=after,
    )
    _notify(locked, f"status:{to_status}", actor_id=getattr(actor.user, "pk", None))
    return locked


@transaction.atomic
def assign(*, actor: ActorContext, ticket: FeedbackTicket, assignee) -> FeedbackTicket:
    _require(actor, FeedbackPermission.ASSIGN, FeedbackPermission.TRIAGE)
    locked = (
        FeedbackTicket.objects.select_for_update(of=("self",))
        .filter(pk=ticket.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("This ticket no longer exists.")

    new_id = getattr(assignee, "pk", None)
    if locked.assignee_pk == new_id:
        return locked

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    locked.assignee = assignee
    locked.save(update_fields=["assignee", "updated_at"])
    after = snapshot_model(locked, fields=AUDIT_FIELDS)
    log_on_commit(
        action="feedback.assigned",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        metadata={"from": before.get("assignee"), "to": after.get("assignee")},
        before=before,
        after=after,
    )
    if new_id is not None:
        _notify(locked, "assigned", actor_id=getattr(actor.user, "pk", None))
    return locked


@transaction.atomic
def set_priority(
    *, actor: ActorContext, ticket: FeedbackTicket, priority: int
) -> FeedbackTicket:
    """Staff queue order. Never changes the submitter's stated urgency, which
    stays on the row as what they actually said."""
    _require(actor, FeedbackPermission.TRIAGE)
    if priority not in PRIORITY_CODES:
        raise ValidationError({"priority": ["Unknown priority."]})
    locked = (
        FeedbackTicket.objects.select_for_update(of=("self",))
        .filter(pk=ticket.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("This ticket no longer exists.")
    if locked.priority == priority:
        return locked

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    locked.priority = priority
    locked.save(update_fields=["priority", "updated_at"])
    log_on_commit(
        action="feedback.prioritised",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        before=before,
        after=snapshot_model(locked, fields=AUDIT_FIELDS),
    )
    return locked


@transaction.atomic
def add_note(
    *, actor: ActorContext, ticket: FeedbackTicket, body: str, internal: bool
) -> FeedbackNote:
    """Write on a ticket.

    A **submitter** may reply on their own ticket without any grant — that is
    the conversation the form started. An **internal** note needs the note
    grant, and nobody can write one on a ticket they cannot triage.
    """
    text = (body or "").strip()
    if not text:
        raise ValidationError({"body": ["Write something before sending."]})

    if internal:
        _require(actor, FeedbackPermission.NOTE, FeedbackPermission.TRIAGE)
    else:
        is_submitter = ticket.submitter_pk == getattr(actor.user, "pk", None)
        if not is_submitter:
            _require(actor, FeedbackPermission.TRIAGE)

    note = FeedbackNote.objects.create(
        ticket=ticket, author=actor.user, body=text, internal=internal
    )
    log_on_commit(
        action="feedback.note_added",
        actor=actor_from_user(actor.user),
        target=target_from_instance(ticket, label=ticket.reference),
        metadata={"internal": internal},
    )
    if not internal:
        _notify(ticket, "replied", actor_id=getattr(actor.user, "pk", None))
    return note


def visible_notes(ticket: FeedbackTicket, actor: ActorContext):
    """Notes this actor may read — filtered in the queryset, not after.

    An internal note must never reach a payload builder that could serialize
    it by accident, so the exclusion happens here and every caller goes through
    it.
    """
    queryset = FeedbackNote.objects.filter(ticket=ticket).select_related("author")
    if actor.can_triage:
        return queryset.order_by("created_at", "pk")
    return queryset.filter(internal=False).order_by("created_at", "pk")


def can_read(ticket: FeedbackTicket, actor: ActorContext) -> bool:
    """Whether this actor may open this ticket at all.

    Used by the screenshot view, which re-authorizes on every request rather
    than trusting a link. Mirrors ``FeedbackQuerySet.for_reader``.
    """
    user_pk = getattr(actor.user, "pk", None)
    if ticket.submitter_pk == user_pk:
        return True
    if not actor.can_triage:
        return False
    if getattr(actor.user, "is_superuser", False):
        return True
    from apps.feedback.models import FeedbackTicket as Model
    from apps.web.capability import access_for

    return (
        Model.objects.for_reader(
            actor.user, access=access_for(actor.user), can_triage=True
        )
        .filter(pk=ticket.pk)
        .exists()
    )


@transaction.atomic
def convert_to_task(
    *, actor: ActorContext, ticket: FeedbackTicket, office=None
) -> tuple[str, bool]:
    """Raise the operational task this ticket is asking for.

    Returns ``(task_public_id, created)``. Idempotent twice over: this function
    returns early when the ticket already carries a task id, and the task
    module's own ``create_task`` is keyed on ``source_reference`` so a race
    still lands on one row.

    **No file crosses.** The screenshot stays in this module's protected
    storage under this module's policy; a task reader is not automatically
    entitled to it. The link is the reference, which each side re-authorizes
    on its own.
    """
    _require(actor, FeedbackPermission.TRIAGE)

    if ticket.converted_task_id:
        return ticket.converted_task_id, False

    from apps.operational_tasks import services as task_services
    from apps.operational_tasks.services import ActorContext as TaskActor
    from apps.operational_tasks.taxonomy import TaskCategory, TaskPriority

    target_office = office or ticket.office
    if target_office is None:
        raise ValidationError(
            {
                "form": [
                    "This ticket has no office, so there is nowhere to file the task."
                ]
            }
        )

    # The task module applies its own permission check against this actor —
    # holding feedback triage does not by itself let somebody create tasks.
    task = task_services.create_task(
        actor=TaskActor(user=actor.user, permissions=actor.permissions),
        office=target_office,
        category=_TASK_CATEGORY.get(ticket.category, TaskCategory.SUPPORT_FOLLOW_UP),
        title=ticket.summary,
        description=ticket.description,
        priority=_TASK_PRIORITY.get(ticket.priority, TaskPriority.NORMAL),
        source=_FEEDBACK_SOURCE,
        source_reference=str(ticket.public_id),
        reporter=ticket.submitter,
    )

    locked = (
        FeedbackTicket.objects.select_for_update(of=("self",))
        .filter(pk=ticket.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("This ticket no longer exists.")
    if locked.converted_task_id:
        return locked.converted_task_id, False

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    locked.converted_task_id = str(task.public_id)
    locked.save(update_fields=["converted_task_id", "updated_at"])
    log_on_commit(
        action="feedback.converted",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        metadata={"task": str(task.public_id), "reference": task.reference},
        before=before,
        after=snapshot_model(locked, fields=AUDIT_FIELDS),
    )
    return str(task.public_id), True


_FEEDBACK_SOURCE = "feedback"


#: Feedback category → task category. Both are closed sets, so the mapping is
#: written out rather than inferred from a shared string.
def _task_categories() -> dict[str, str]:
    from apps.feedback.taxonomy import FeedbackCategory
    from apps.operational_tasks.taxonomy import TaskCategory

    return {
        FeedbackCategory.BUG: TaskCategory.BUG,
        FeedbackCategory.IDEA: TaskCategory.SUPPORT_FOLLOW_UP,
        FeedbackCategory.CONTENT: TaskCategory.CONTENT_UPDATE,
        FeedbackCategory.ACCESS: TaskCategory.PERMISSION,
        FeedbackCategory.HELP: TaskCategory.SUPPORT_FOLLOW_UP,
    }


class _LazyMap(dict):
    """Deferred so importing this module never pulls the task app in at import
    time — the two modules must stay independently importable."""

    def __init__(self, builder):
        super().__init__()
        self._builder = builder

    def get(self, key, default=None):
        if not self:
            self.update(self._builder())
        return super().get(key, default)


_TASK_CATEGORY = _LazyMap(_task_categories)
_TASK_PRIORITY = _LazyMap(lambda: {1: 1, 2: 2, 3: 3, 4: 4})


def _notify(ticket: FeedbackTicket, event: str, *, actor_id: int | None) -> None:
    """Hand the event to the notification module once the row is durable.

    Keyed by ticket, event, and ``updated_at`` so a retried request that lands
    on an unchanged row produces the same key and is collapsed rather than
    delivered twice.
    """
    from apps.feedback.notifications import queue_feedback_notice

    stamp = ticket.updated_at.isoformat() if ticket.updated_at else "new"
    dedupe_key = f"feedback:{ticket.public_id}:{event}:{stamp}"
    transaction.on_commit(
        lambda: queue_feedback_notice(
            ticket_id=ticket.pk,
            event=event,
            dedupe_key=dedupe_key,
            actor_id=actor_id,
        )
    )
