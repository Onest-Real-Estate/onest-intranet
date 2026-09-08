"""The only place an IT support ticket's lifecycle may change.

Every mutation here follows the same shape:

1. authorize the actor against the *stored* row, never a client-supplied one;
2. take a row lock and re-read, so two racing writers serialize;
3. check the caller's expected state, so the second of two racing writers is
   told it lost rather than silently overwriting the first;
4. write, stamp the timestamps that go with the move, and record an audit
   event with the before/after;
5. schedule notifications on commit, keyed so a retry cannot duplicate them.

Step 3 is what makes the API safe for a UI: a stale queue that still shows
"New" cannot drag a ticket somebody else already resolved.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.cache import cache
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
from apps.it_support.models import SupportTicket, TicketAttachment, TicketReply
from apps.it_support.taxonomy import (
    CATEGORY_CODES,
    CONTACT_METHOD_CODES,
    PRIORITY_CODES,
    ContactMethod,
    SupportPermission,
    SupportPriority,
    SupportStatus,
    Transition,
    find_transition,
    transitions_from,
)

logger = logging.getLogger("apps.it_support")

#: "No opinion", distinct from an explicit ``None`` meaning "I believe this is
#: unassigned". Both are real inputs, so they need different values.
UNSET: object = object()

#: Submissions one person may make inside the window. Generous on purpose: the
#: limit exists to stop a scripted flood, not to ration somebody whose morning
#: is going badly.
RATE_LIMIT_SUBMISSIONS = 10
RATE_LIMIT_WINDOW_SECONDS = 15 * 60

#: What may be attached, and what each one is served as. Stated here rather
#: than read from :mod:`mimetypes`, which consults the host's own MIME database
#: — macOS maps ``.log`` to ``text/plain`` and a bare Linux container does not.
#: A stored type that depends on which machine accepted the upload is a header
#: this hub would later serve back.
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
MAX_ATTACHMENTS_PER_TICKET = 5

#: Fields the audit trail snapshots. Deliberately excludes ``description`` and
#: reply bodies: an audit record states *what changed*, and copying free text
#: into it creates a second, unscoped copy of content the ticket's own
#: permissions were protecting.
AUDIT_FIELDS = [
    "reference",
    "category",
    "status",
    "priority",
    "office",
    "assignee",
    "about_user",
]


class TransitionError(ValidationError):
    """The requested move is not legal from the ticket's current state."""


class ConcurrentUpdate(ValidationError):
    """Somebody else moved the ticket since the caller last read it."""


class RateLimited(ValidationError):
    """Too many submissions inside the window."""


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

    @property
    def can_triage(self) -> bool:
        return self.holds(SupportPermission.TRIAGE)


def _require(actor: ActorContext, *codenames: str) -> None:
    if not actor.holds(*codenames):
        raise PermissionDenied("You do not have permission to do that.")


def next_reference(pk: int) -> str:
    return f"ITS-{pk:06d}"


def check_rate_limit(user, *, now: float | None = None) -> None:
    """Count this submission, refusing past the window's allowance.

    Keyed by user rather than IP: the hub is authenticated, so the person is
    the meaningful subject, and an office behind one NAT should not share a
    budget. Cache-backed, so a restart forgives.
    """
    key = f"it_support:rate:{getattr(user, 'pk', 'anon')}"
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
                    f"You have sent {RATE_LIMIT_SUBMISSIONS} requests recently. "
                    f"You can send another in about {minutes} minutes — or reply "
                    "on an existing ticket if this is about the same problem."
                ]
            }
        )
    window.append(moment)
    cache.set(key, window, RATE_LIMIT_WINDOW_SECONDS)


def available_transitions(
    ticket: SupportTicket, actor: ActorContext
) -> list[Transition]:
    """Legal moves this actor could make right now.

    The UI renders from this and :func:`transition` re-checks every element of
    it — the list is a convenience, never the authorization.
    """
    concerns = ticket.concerns(actor.user)
    allowed: list[Transition] = []
    for candidate in transitions_from(ticket.status):
        if actor.holds(*candidate.permissions) or (candidate.by_submitter and concerns):
            allowed.append(candidate)
    return allowed


@transaction.atomic
def submit(
    *,
    user,
    subject: str,
    description: str,
    category: str,
    submission_key: str,
    preferred_contact: str = ContactMethod.HUB,
    device_info: str = "",
    location: str = "",
    page_url: str = "",
    about_user=None,
) -> tuple[SupportTicket, bool]:
    """Raise a ticket. Returns ``(ticket, created)``.

    **No permission is required.** Every authenticated person may report that
    the tool they are told to use is broken; putting a grant in front of that
    means the people most likely to hit an access bug are the ones who cannot
    report it.

    Idempotent on ``submission_key``: a double-clicked button, a retried
    request, and a browser replaying the POST all return the first ticket, and
    ``created`` tells the caller whether to re-run side effects.

    The office is snapshotted from the *submitter*, never accepted from the
    client — a posted office id would be a way to file into another queue.
    """
    key = (submission_key or "").strip()[:64]
    if not key:
        raise ValidationError({"form": ["That submission could not be identified."]})

    existing = SupportTicket.objects.filter(submission_key=key).first()
    if existing is not None:
        return existing, False

    if category not in CATEGORY_CODES:
        raise ValidationError({"category": ["Choose what kind of problem this is."]})
    if preferred_contact not in CONTACT_METHOD_CODES:
        raise ValidationError({"preferredContact": ["Choose how to reach you."]})
    if not (subject or "").strip():
        raise ValidationError({"subject": ["Give the request a short subject."]})
    if not (description or "").strip():
        raise ValidationError({"description": ["Describe what is happening."]})

    check_rate_limit(user)

    ticket = SupportTicket.objects.create(
        subject=subject.strip()[:160],
        description=description.strip(),
        category=category,
        submitter=user,
        about_user=about_user,
        office=getattr(user, "office", None),
        location=location.strip()[:120],
        preferred_contact=preferred_contact,
        device_info=device_info.strip()[:300],
        page_url=(page_url or "")[:2000],
        submission_key=key,
        status=SupportStatus.NEW,
    )
    # The reference needs the primary key, so it is a second write rather than
    # a second sequence to keep in step with the first.
    ticket.reference = next_reference(ticket.pk)
    ticket.save(update_fields=["reference", "updated_at"])

    log_on_commit(
        action="it_support.created",
        actor=actor_from_user(user),
        target=target_from_instance(ticket, label=ticket.reference),
        metadata={"category": category, "priority": ticket.priority},
    )
    _notify_on_commit(ticket, "created", actor_user=user)
    return ticket, True


@transaction.atomic
def transition(
    *,
    actor: ActorContext,
    ticket: SupportTicket,
    to_status: str,
    expected_status: str | None = None,
    note: str = "",
    note_internal: bool = False,
) -> SupportTicket:
    """Move a ticket, or explain why it cannot move.

    ``expected_status`` is the caller's view of the world. When it disagrees
    with the row under lock, the caller is told it lost the race instead of
    overwriting a decision it never saw.
    """
    locked = (
        SupportTicket.objects.select_for_update(of=("self",))
        .filter(pk=ticket.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("This ticket no longer exists.")

    if expected_status is not None and locked.status != expected_status:
        raise ConcurrentUpdate(
            {
                "status": [
                    "Somebody else moved this ticket while you were working on "
                    f"it. It is now “{locked.status_label}”. Reload to continue."
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

    concerns = locked.concerns(actor.user)
    if not actor.holds(*move.permissions) and not (move.by_submitter and concerns):
        raise PermissionDenied("You do not have permission to make that change.")

    text = (note or "").strip()
    if move.requires_note and not text:
        raise ValidationError(
            {"note": ["Explain the change so the next reader knows what happened."]}
        )

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    now = timezone.now()
    updates = ["status", "updated_at"]
    locked.status = to_status

    if move.resolves:
        locked.resolved_at = now
        updates.append("resolved_at")
    if move.closes:
        locked.closed_at = now
        updates.append("closed_at")
    if move.reopens:
        locked.resolved_at = None
        locked.closed_at = None
        updates.extend(["resolved_at", "closed_at"])

    locked.save(update_fields=sorted(set(updates)))

    if text:
        # A resolution note is the thing the requester is actually told, so it
        # is recorded as one rather than as an ordinary line in the thread.
        TicketReply.objects.create(
            ticket=locked,
            author=actor.user,
            body=text,
            internal=note_internal and not move.resolves,
            is_resolution=move.resolves and not note_internal,
        )

    after = snapshot_model(locked, fields=AUDIT_FIELDS)
    log_on_commit(
        action="it_support.status_changed",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        metadata={"from": before.get("status"), "to": after.get("status")},
        before=before,
        after=after,
    )
    _notify_on_commit(locked, f"status:{to_status}", actor_user=actor.user)
    return locked


@transaction.atomic
def assign(
    *,
    actor: ActorContext,
    ticket: SupportTicket,
    assignee,
    expected_assignee_id: int | None | object = UNSET,
) -> SupportTicket:
    """Set or clear the assignee.

    ``expected_assignee_id`` defaults to ``UNSET`` meaning "do not check". An
    explicit ``None`` means "I believe this is unassigned", which is a real
    claim worth verifying — ``None`` cannot double as "no opinion".
    """
    _require(actor, SupportPermission.ASSIGN, SupportPermission.TRIAGE)

    locked = (
        SupportTicket.objects.select_for_update(of=("self",))
        .filter(pk=ticket.pk)
        .first()
    )
    if locked is None:
        raise ValidationError("This ticket no longer exists.")
    if expected_assignee_id is not UNSET and locked.assignee_pk != expected_assignee_id:
        raise ConcurrentUpdate(
            {"assignee": ["Somebody else reassigned this ticket. Reload to continue."]}
        )

    new_id = getattr(assignee, "pk", None)
    if locked.assignee_pk == new_id:
        return locked

    before = snapshot_model(locked, fields=AUDIT_FIELDS)
    locked.assignee = assignee
    locked.save(update_fields=["assignee", "updated_at"])
    after = snapshot_model(locked, fields=AUDIT_FIELDS)

    log_on_commit(
        action="it_support.assigned",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        metadata={"from": before.get("assignee"), "to": after.get("assignee")},
        before=before,
        after=after,
    )
    if new_id is not None:
        _notify_on_commit(locked, "assigned", actor_user=actor.user)
    return locked


@transaction.atomic
def set_priority(
    *, actor: ActorContext, ticket: SupportTicket, priority: int
) -> SupportTicket:
    """Set the queue order. Staff-only: a submitter marking their own ticket
    urgent would make the field meaningless within a week."""
    _require(actor, SupportPermission.TRIAGE)
    if priority not in PRIORITY_CODES:
        raise ValidationError({"priority": ["Unknown priority."]})

    locked = (
        SupportTicket.objects.select_for_update(of=("self",))
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
    after = snapshot_model(locked, fields=AUDIT_FIELDS)

    log_on_commit(
        action="it_support.priority_changed",
        actor=actor_from_user(actor.user),
        target=target_from_instance(locked, label=locked.reference),
        metadata={"from": before.get("priority"), "to": after.get("priority")},
        before=before,
        after=after,
    )
    if priority == SupportPriority.URGENT:
        _notify_on_commit(locked, "escalated", actor_user=actor.user)
    return locked


@transaction.atomic
def add_reply(
    *, actor: ActorContext, ticket: SupportTicket, body: str, internal: bool = False
) -> TicketReply:
    """Write on a ticket.

    The person the ticket **concerns** — its submitter, or the agent it was
    raised about — may reply without any grant: that is the conversation the
    form started. An **internal** note needs the note grant, and nobody can
    write one on a ticket they cannot triage.
    """
    text = (body or "").strip()
    if not text:
        raise ValidationError({"body": ["Write something before sending."]})

    if internal:
        _require(actor, SupportPermission.NOTE, SupportPermission.TRIAGE)
    elif not ticket.concerns(actor.user):
        _require(actor, SupportPermission.TRIAGE)

    reply = TicketReply.objects.create(
        ticket=ticket, author=actor.user, body=text, internal=internal
    )
    log_on_commit(
        action="it_support.replied",
        actor=actor_from_user(actor.user),
        target=target_from_instance(ticket, label=ticket.reference),
        metadata={"internal": internal},
    )
    if not internal:
        event = "user_replied" if ticket.concerns(actor.user) else "staff_replied"
        _notify_on_commit(ticket, event, actor_user=actor.user)
    return reply


@transaction.atomic
def attach_file(
    *,
    actor: ActorContext,
    ticket: SupportTicket,
    uploaded,
    internal: bool = False,
) -> TicketAttachment:
    """Store one file against a ticket, in protected storage.

    An *internal* file follows the internal-note rule exactly. An ordinary
    attachment may be added by anybody the ticket concerns — evidence is the
    most useful thing a requester can supply — or by a triager.

    The extension is judged against a closed allowlist and the size against a
    ceiling *before* anything is written, and the stored media type comes from
    the name the server accepted rather than the ``Content-Type`` the client
    claimed: a header is the uploader's assertion, not a fact.
    """
    if internal:
        _require(actor, SupportPermission.NOTE, SupportPermission.TRIAGE)
    elif not ticket.concerns(actor.user):
        _require(actor, SupportPermission.TRIAGE)

    if uploaded is None:
        raise ValidationError({"file": ["Choose a file to attach."]})
    if ticket.status in {SupportStatus.CLOSED}:
        raise ValidationError(
            {"file": ["This ticket is closed. Reopen it before attaching anything."]}
        )

    name = Path(uploaded.name or "").name
    extension = Path(name).suffix.lower()
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValidationError(
            {"file": [f"File type “{extension or 'unknown'}” is not allowed."]}
        )
    if uploaded.size > MAX_ATTACHMENT_BYTES:
        raise ValidationError({"file": ["Files must be 10 MB or smaller."]})
    if (
        TicketAttachment.objects.filter(ticket=ticket).count()
        >= MAX_ATTACHMENTS_PER_TICKET
    ):
        raise ValidationError(
            {
                "file": [
                    f"A ticket holds at most {MAX_ATTACHMENTS_PER_TICKET} files. "
                    "Remove one before adding another."
                ]
            }
        )

    uploaded.seek(0)
    data = uploaded.read()
    attachment = TicketAttachment(
        ticket=ticket,
        uploaded_by=actor.user,
        display_name=name[:200],
        media_type=ATTACHMENT_MEDIA_TYPES[extension],
        byte_size=len(data),
        internal=internal,
    )
    attachment.file.save(name, ContentFile(data), save=False)
    attachment.save()

    log_on_commit(
        action="it_support.attachment_added",
        actor=actor_from_user(actor.user),
        target=target_from_instance(ticket, label=ticket.reference),
        # The file name only. The bytes stay where the ticket's own permissions
        # protect them, and an audit row is read by a wider audience.
        metadata={"fileName": attachment.display_name, "internal": internal},
    )
    return attachment


def visible_replies(ticket: SupportTicket, actor: ActorContext):
    """Replies this actor may read — filtered in the queryset, not after.

    An internal note must never reach a payload builder that might serialize
    it by accident, so the exclusion happens here, once, and every caller goes
    through it.
    """
    queryset = (
        TicketReply.objects.filter(ticket=ticket)
        .select_related("author")
        .order_by("created_at", "pk")
    )
    if actor.holds(SupportPermission.NOTE, SupportPermission.TRIAGE):
        return queryset
    return queryset.filter(internal=False)


def visible_attachments(ticket: SupportTicket, actor: ActorContext):
    queryset = (
        TicketAttachment.objects.filter(ticket=ticket)
        .select_related("uploaded_by")
        .order_by("created_at", "pk")
    )
    if actor.holds(SupportPermission.NOTE, SupportPermission.TRIAGE):
        return queryset
    return queryset.filter(internal=False)


def load_attachment(*, ticket: SupportTicket, actor: ActorContext, public_id):
    """One attachment, looked up *inside* what this actor may already read.

    Resolved through :func:`visible_attachments` rather than by bare id, so an
    internal file is indistinguishable from one that does not exist for a
    reader without the grant. A later ``if attachment.internal`` check would
    answer the same question with a different status code, and that difference
    is the disclosure.
    """
    return visible_attachments(ticket, actor).filter(public_id=public_id).first()


def _notify_on_commit(ticket: SupportTicket, event: str, *, actor_user) -> None:
    """Hand the event to the notification module after the row is durable.

    Keyed by ticket, event, and the row's ``updated_at`` so a retried request
    that lands on an unchanged row produces the same key and is collapsed
    rather than delivered twice.
    """
    from apps.it_support.notifications import queue_ticket_notice

    stamp = ticket.updated_at.isoformat()
    dedupe_key = f"it_support:{ticket.public_id}:{event}:{stamp}"
    actor_id = getattr(actor_user, "pk", None)
    transaction.on_commit(
        lambda: queue_ticket_notice(
            ticket_id=ticket.pk,
            event=event,
            dedupe_key=dedupe_key,
            actor_id=actor_id,
        )
    )
