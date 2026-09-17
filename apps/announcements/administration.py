"""The announcement workspace: authority, lifecycle, concurrency, and history.

Everything a publisher can do to an announcement passes through this module, and
it answers four questions that no view is allowed to re-derive:

* **Who may act** — three separate grants. ``manage_announcements`` writes
  drafts, ``publish_announcements`` moves the row between lifecycle states, and
  ``pin_announcements`` changes feed order. A draft reaches nobody, so authoring
  is deliberately the cheap grant; publication is the expensive one.
* **What they may aim at** — the owning office must sit inside the actor's own
  grant, and every audience selector is re-authorized by
  :func:`apps.announcements.audience.assert_can_target`. Neither is ever read
  from the request.
* **What happens when two people edit at once** — every write takes the row
  under ``select_for_update`` and compares an opaque version token. A stale
  token is a ``409``, not a silent overwrite.
* **What is left behind** — an audit row for every transition and every denial,
  and a domain event published only after the transaction commits.

Lifecycle
---------
``draft`` → ``published`` → ``archived``, with two shapes of publication and
two ways back:

=============  =========================================================
publish        Live immediately. ``publish_at`` must be empty or past.
schedule       Live at a future ``publish_at``. Stored as ``published``
               with a future window start, which is the same row shape the
               feed already filters on — there is no fourth status to keep
               in step with :meth:`AnnouncementQuerySet.within_window`.
unpublish      Back to ``draft``. The publication stamp is cleared so a
               later publish dates itself honestly.
archive        Out of the feed for good, retaining the row, its media, and
               its history. Un-pins on the way out.
restore        ``archived`` → ``draft``. Never straight back to live: a
               restored notice is republished deliberately or not at all.
=============  =========================================================

The *displayed* state is richer than the stored one — "Scheduled", "Live",
"Expired" are all ``status="published"`` — and is derived in
:func:`lifecycle_state` rather than stored, so it can never disagree with what
the feed actually shows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.announcements.audience import (
    AudienceContext,
    AudienceSelector,
    describe_audience,
    replace_audience,
    selector_q,
    selectors_for,
    targetable_office_ids,
    targetable_role_codes,
)
from apps.announcements.media_service import attachments_payload, hero_payload
from apps.announcements.models import Announcement, AnnouncementCategory
from apps.announcements.services import (
    MANAGE_PERMISSION,
    feed_row,
    publish_announcement,
    validation_debt_payload,
)
from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import Office, User
from apps.user.services.hierarchy import ancestors
from apps.user.services.role_assignments import has_effective_permission

PUBLISH_PERMISSION = "web.publish_announcements"
PIN_PERMISSION = "web.pin_announcements"

#: Fields the workspace form owns. Lifecycle, pinning, ownership, and audience
#: all move through their own entry points, so a routine copy edit can never be
#: the thing that publishes a notice or widens who receives it.
EDITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "summary",
    "body",
    "category",
    "priority",
    "publish_at",
    "expires_at",
    "cta_label",
    "cta_url",
    "source_url",
    "source_publisher",
    "source_retrieved_at",
    "ai_assisted_summary",
    "ai_assisted_body",
)

#: Audit actions that make up the publication history panel, in the order the
#: timeline explains them. Anything not listed is a denial or an unrelated
#: event and stays out of the author-facing story.
HISTORY_ACTIONS: dict[str, tuple[str, str]] = {
    "announcement.created": ("Draft created", "neutral"),
    "announcement.updated": ("Draft edited", "neutral"),
    "announcement.audience_changed": ("Audience changed", "info"),
    "announcement.scheduled": ("Scheduled", "info"),
    "announcement.published": ("Published", "success"),
    "announcement.unpublished": ("Returned to draft", "warning"),
    "announcement.archived": ("Archived", "neutral"),
    "announcement.restored": ("Restored as draft", "info"),
    "announcement.pinned": ("Pinned", "info"),
    "announcement.unpinned": ("Unpinned", "neutral"),
}

TRANSITIONS: tuple[str, ...] = (
    "publish",
    "schedule",
    "unpublish",
    "archive",
    "restore",
)

PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
HISTORY_LIMIT = 25


class StaleAnnouncementVersion(ValidationError):
    """The row moved between the form being rendered and being submitted."""

    message: str

    def __init__(self):
        self.message = str(
            _(
                "Somebody else saved this announcement while you were writing. "
                "Review their version before applying your changes."
            )
        )
        super().__init__(self.message)


class TransitionRefused(ValidationError):
    """A lifecycle action that does not apply to the row's current state."""

    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Authority
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Capabilities:
    """One resolution of what this actor may do, shared across a whole page.

    Each answer costs a permission lookup that walks role assignments, and a
    list page needs the same three answers for every row. Resolving once here
    keeps the row count off the query count.
    """

    can_author: bool
    can_publish: bool
    can_pin: bool

    def payload(self) -> dict[str, bool]:
        return {
            "canAuthor": self.can_author,
            "canPublish": self.can_publish,
            "canPin": self.can_pin,
        }


def capabilities(actor: User) -> Capabilities:
    return Capabilities(
        can_author=has_effective_permission(actor, MANAGE_PERMISSION),
        can_publish=has_effective_permission(actor, PUBLISH_PERMISSION),
        can_pin=has_effective_permission(actor, PIN_PERMISSION),
    )


def _deny(actor: User, announcement: Announcement | None, *, reason: str) -> None:
    log_event(
        "security.announcement.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=Announcement._meta.label_lower,
            target_id=str(announcement.pk) if announcement and announcement.pk else "",
            target_label=announcement.slug if announcement else "",
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def manageable_office_ids(actor: User) -> frozenset[int]:
    """Offices whose announcements this actor may open and own.

    Built from the actor's own grant through the shared office-scope helper,
    never from anything the client sent.
    """
    from apps.web.authorization import scope_queryset_for_offices

    return frozenset(
        scope_queryset_for_offices(actor, Office.objects.all()).values_list(
            "pk", flat=True
        )
    )


def publishable_office_queryset(actor: User) -> QuerySet[Office]:
    """Offices offered as the owning node, in tree order.

    The parent chain is joined so the picker can label each option with its
    path; the org tree is head office → region → regional office → branch, so
    three levels covers the deepest node.
    """
    base = Office.objects.filter(is_active=True).select_related(
        "parent", "parent__parent", "parent__parent__parent", "region"
    )
    return base.filter(pk__in=manageable_office_ids(actor)).order_by(
        "sort_order", "name"
    )


def manageable_queryset(actor: User) -> QuerySet[Announcement]:
    """Announcements this actor may see in the workspace.

    Scope is the owning office, resolved from the actor's grant. A row outside
    it is absent rather than shown read-only: confirming that an id exists is
    itself a disclosure across a scope boundary, which is why every view loads
    through this queryset instead of by bare primary key.
    """
    base = Announcement.objects.select_related(
        "owner_office", "category", "created_by", "updated_by"
    )
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        return base.none()
    office_ids = manageable_office_ids(actor)
    if not office_ids:
        return base.none()
    return base.filter(owner_office_id__in=office_ids)


def assert_can_author(actor: User, office: Office) -> None:
    """Write a draft for this owning office."""
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _deny(actor, None, reason="missing_permission")
        raise PermissionDenied("You cannot manage announcements.")
    if office.pk not in manageable_office_ids(actor):
        _deny(actor, None, reason="out_of_scope_office")
        raise PermissionDenied("That office is outside your announcement scope.")


def assert_can_publish(actor: User, announcement: Announcement) -> None:
    """Change the lifecycle state of this announcement.

    Authoring authority is checked first and separately: someone who may not
    even open the record should learn nothing more specific than that.
    """
    assert_can_author(actor, announcement.owner_office)
    if not has_effective_permission(actor, PUBLISH_PERMISSION):
        _deny(actor, announcement, reason="missing_publish_permission")
        raise PermissionDenied("You cannot publish or archive announcements.")


def assert_can_pin(actor: User, announcement: Announcement) -> None:
    assert_can_author(actor, announcement.owner_office)
    if not has_effective_permission(actor, PIN_PERMISSION):
        _deny(actor, announcement, reason="missing_pin_permission")
        raise PermissionDenied("You cannot pin announcements.")


# --------------------------------------------------------------------------- #
# Versioning, snapshots, and derived state
# --------------------------------------------------------------------------- #


def announcement_version(announcement: Announcement) -> str:
    """Opaque token for optimistic concurrency on the workspace form."""
    return announcement.updated_at.isoformat() if announcement.updated_at else ""


def _assert_fresh(announcement: Announcement, expected_version: str) -> None:
    if announcement_version(announcement) != (expected_version or ""):
        raise StaleAnnouncementVersion()


def snapshot(announcement: Announcement) -> dict[str, Any]:
    """Audit before/after values. Configuration and copy, never personal data."""
    return {
        "slug": announcement.slug,
        "title": announcement.title,
        "summary": announcement.summary,
        "status": announcement.status,
        "category": announcement.category.code if announcement.category else None,
        "priority": announcement.priority,
        "owner_office": announcement.owner_office.stable_key,
        "publish_at": announcement.publish_at,
        "expires_at": announcement.expires_at,
        "published_at": announcement.published_at,
        "archived_at": announcement.archived_at,
        "is_pinned": announcement.is_pinned,
        "cta_label": announcement.cta_label,
        "cta_url": announcement.cta_url,
        "source_url": announcement.source_url,
        "source_publisher": announcement.source_publisher,
        "audience": describe_audience(announcement),
    }


def lifecycle_state(announcement: Announcement, *, now=None) -> dict[str, str]:
    """The state an administrator reads, derived rather than stored.

    "Scheduled", "Live", and "Expired" are all ``status="published"`` on the
    row. Deriving them from the same window predicate the feed applies is what
    stops the workspace from claiming a notice is live while
    :meth:`AnnouncementQuerySet.within_window` is hiding it.
    """
    moment = now or timezone.now()
    if announcement.status == Announcement.Status.DRAFT:
        return {"code": "draft", "label": "Draft", "tone": "neutral"}
    if announcement.status == Announcement.Status.ARCHIVED:
        return {"code": "archived", "label": "Archived", "tone": "neutral"}
    if announcement.publish_at is not None and announcement.publish_at > moment:
        return {"code": "scheduled", "label": "Scheduled", "tone": "info"}
    if announcement.expires_at is not None and announcement.expires_at <= moment:
        return {"code": "expired", "label": "Expired", "tone": "warning"}
    return {"code": "live", "label": "Live", "tone": "success"}


def _actor_label(user: User | None) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.email


# --------------------------------------------------------------------------- #
# Slugs
# --------------------------------------------------------------------------- #


def build_slug(title: str, *, office: Office, exclude_pk: int | None = None) -> str:
    """A stable per-office key derived once, at creation, from the title.

    Uniqueness is per owning office (``announcement_unique_slug_per_office``),
    so the suffix search is scoped the same way. The slug never changes
    afterwards: it appears in audit rows and in the workspace URL, and a
    retitled announcement is still the same record.
    """
    base = slugify(title)[:70] or "announcement"
    taken = set(
        Announcement.objects.filter(owner_office=office)
        .exclude(pk=exclude_pk)
        .values_list("slug", flat=True)
    )
    if base not in taken:
        return base
    for suffix in range(2, 100):
        candidate = f"{base[: 70 - len(str(suffix)) - 1]}-{suffix}"
        if candidate not in taken:
            return candidate
    raise ValidationError(
        {"title": _("Too many announcements share this title in that office.")}
    )


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #


def _log(
    action: str,
    *,
    actor: User,
    announcement: Announcement,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    log_event(
        action,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=Announcement._meta.label_lower,
            target_id=str(announcement.pk),
            target_label=announcement.slug,
        ),
        before=before or {},
        after=after or {},
    )


def _apply_fields(announcement: Announcement, cleaned: dict[str, Any]) -> None:
    for name in EDITABLE_FIELDS:
        if name in cleaned:
            setattr(announcement, name, cleaned[name])


def create_announcement(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
) -> Announcement:
    """Author a new draft. Never publishes — that is a separate action.

    Authorization runs before the transaction opens so a denial leaves its
    audit row behind instead of being rolled back with the write it refused.
    """
    assert_can_author(actor, office)
    return _create(actor=actor, office=office, cleaned=cleaned, selectors=selectors)


@transaction.atomic
def _create(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
) -> Announcement:
    announcement = Announcement(
        owner_office=office,
        slug=build_slug(cleaned.get("title", ""), office=office),
        status=Announcement.Status.DRAFT,
        created_by=actor,
        updated_by=actor,
    )
    _apply_fields(announcement, cleaned)
    announcement.full_clean(exclude=["owner_office", "slug"])
    announcement.save()
    # Audience is authorized inside ``replace_audience`` against the actor's own
    # querysets, so a crafted office or user id fails here even though no
    # control ever offered it.
    replace_audience(actor, announcement, selectors)
    _log(
        "announcement.created",
        actor=actor,
        announcement=announcement,
        before=None,
        after=snapshot(announcement),
    )
    return announcement


def update_announcement(
    *,
    actor: User,
    announcement: Announcement,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
) -> Announcement:
    assert_can_author(actor, announcement.owner_office)
    return _update(
        actor=actor,
        announcement=announcement,
        cleaned=cleaned,
        selectors=selectors,
        expected_version=expected_version,
    )


@transaction.atomic
def _update(
    *,
    actor: User,
    announcement: Announcement,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
) -> Announcement:
    locked = _lock(announcement.pk)
    # Re-checked against the locked row: the actor's grant may have narrowed
    # between the form being rendered and this write.
    assert_can_author(actor, locked.owner_office)
    _assert_fresh(locked, expected_version)

    before = snapshot(locked)
    _apply_fields(locked, cleaned)
    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office", "slug"])
    locked.save()
    replace_audience(actor, locked, selectors)
    _log(
        "announcement.updated",
        actor=actor,
        announcement=locked,
        before=before,
        after=snapshot(locked),
    )
    return locked


def _lock(pk: int) -> Announcement:
    """Take the row under a write lock without locking its joins.

    ``of=("self",)`` is load-bearing: ``category`` is nullable, so
    ``select_related`` reaches it through a LEFT OUTER JOIN and PostgreSQL
    refuses a bare ``FOR UPDATE`` spanning the nullable side of an outer join.
    SQLite drops row locking altogether, so a local sqlite run never sees it.
    """
    return (
        Announcement.objects.select_for_update(of=("self",))
        .select_related("owner_office", "category")
        .get(pk=pk)
    )


def transition(
    *,
    actor: User,
    announcement: Announcement,
    action: str,
    expected_version: str,
    now=None,
) -> Announcement:
    """One explicit lifecycle move. Authorized before the transaction opens."""
    if action not in TRANSITIONS:
        raise TransitionRefused(str(_("That is not an announcement action.")))
    assert_can_publish(actor, announcement)
    return _transition(
        actor=actor,
        announcement=announcement,
        action=action,
        expected_version=expected_version,
        now=now,
    )


@transaction.atomic
def _transition(
    *,
    actor: User,
    announcement: Announcement,
    action: str,
    expected_version: str,
    now=None,
) -> Announcement:
    moment = now or timezone.now()
    locked = _lock(announcement.pk)
    assert_can_publish(actor, locked)
    _assert_fresh(locked, expected_version)
    before = snapshot(locked)

    if action in {"publish", "schedule"}:
        return _go_live(
            actor=actor, locked=locked, scheduled=action == "schedule", now=moment
        )

    if action == "unpublish":
        if locked.status != Announcement.Status.PUBLISHED:
            raise TransitionRefused(
                str(_("Only a published announcement can be returned to draft."))
            )
        locked.status = Announcement.Status.DRAFT
        # Cleared so a later publish dates itself honestly rather than claiming
        # the moment it first went out. The audit trail keeps the original.
        locked.published_at = None
        _unpin(locked)
        event_name = "announcement.unpublished"
    elif action == "archive":
        if locked.status == Announcement.Status.ARCHIVED:
            raise TransitionRefused(str(_("This announcement is already archived.")))
        locked.status = Announcement.Status.ARCHIVED
        locked.archived_at = moment
        _unpin(locked)
        event_name = "announcement.archived"
    else:  # restore
        if locked.status != Announcement.Status.ARCHIVED:
            raise TransitionRefused(
                str(_("Only an archived announcement can be restored."))
            )
        locked.status = Announcement.Status.DRAFT
        locked.archived_at = None
        locked.published_at = None
        event_name = "announcement.restored"

    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office", "slug"])
    locked.save()
    _log(
        event_name,
        actor=actor,
        announcement=locked,
        before=before,
        after=snapshot(locked),
    )
    _emit_lifecycle(event_name, actor=actor, announcement=locked, now=moment)
    return locked


def _go_live(
    *, actor: User, locked: Announcement, scheduled: bool, now
) -> Announcement:
    """Publish or schedule, refusing when the window contradicts the intent.

    Both actions produce the same row shape — ``status="published"`` with a
    window — so the difference is checked here rather than stored. Publishing
    something dated for next week without saying so would be the kind of
    surprise the whole workspace exists to prevent.
    """
    if locked.status == Announcement.Status.PUBLISHED:
        raise TransitionRefused(str(_("This announcement is already published.")))
    if scheduled and (locked.publish_at is None or locked.publish_at <= now):
        raise TransitionRefused(
            str(_("Set a publish time in the future before scheduling."))
        )
    if not scheduled and locked.publish_at is not None and locked.publish_at > now:
        raise TransitionRefused(
            str(
                _(
                    "This announcement is dated for the future. Schedule it, or "
                    "clear the publish time to send it now."
                )
            )
        )
    # ``publish_announcement`` is the single publish path: it re-runs the whole
    # validation checklist, re-authorizes every stored selector against the
    # actor's *current* grant, writes the audit row, and emits the domain event
    # after commit. Nothing is duplicated here.
    return publish_announcement(actor, locked, now=now)


def _unpin(announcement: Announcement) -> None:
    announcement.is_pinned = False
    announcement.pinned_at = None


def set_pinned(
    *, actor: User, announcement: Announcement, pinned: bool, expected_version: str
) -> Announcement:
    assert_can_pin(actor, announcement)
    return _set_pinned(
        actor=actor,
        announcement=announcement,
        pinned=pinned,
        expected_version=expected_version,
    )


@transaction.atomic
def _set_pinned(
    *, actor: User, announcement: Announcement, pinned: bool, expected_version: str
) -> Announcement:
    locked = _lock(announcement.pk)
    assert_can_pin(actor, locked)
    _assert_fresh(locked, expected_version)
    if pinned and locked.status != Announcement.Status.PUBLISHED:
        raise TransitionRefused(
            str(_("Only a published announcement can be pinned to the feed."))
        )
    before = snapshot(locked)
    locked.is_pinned = pinned
    locked.pinned_at = timezone.now() if pinned else None
    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office", "slug"])
    locked.save()
    _log(
        "announcement.pinned" if pinned else "announcement.unpinned",
        actor=actor,
        announcement=locked,
        before=before,
        after=snapshot(locked),
    )
    return locked


def _emit_lifecycle(name: str, *, actor: User, announcement: Announcement, now) -> None:
    """Publish a lifecycle domain event. ``publish`` defers it to commit."""
    publish_event(
        name,
        actor_id=str(actor.pk),
        subject=str(announcement.pk),
        payload={
            "announcement_id": announcement.pk,
            "owner_office_id": announcement.owner_office.pk,
            "scope_level": announcement.scope_level,
            "status": announcement.status,
            "occurred_at": now.isoformat(),
        },
    )


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #


def preview_context(*, office: Office | None, role_code: str) -> AudienceContext:
    """A hypothetical reader, expressed exactly as a real one is.

    ``user_id`` stays ``None`` because nobody in particular is being previewed;
    the ``user`` selector kind therefore never matches, which is correct — an
    individually named recipient is not something an office-and-role preview
    can stand in for, and the audience list says so in words.
    """
    return AudienceContext(
        user_id=None,
        office_id=office.pk if office else None,
        office_chain_ids=frozenset(node.pk for node in ancestors(office))
        if office
        else frozenset(),
        role_codes=frozenset({role_code}) if role_code else frozenset(),
        is_authenticated=True,
    )


def preview_payload(
    announcement: Announcement,
    *,
    office: Office | None,
    role_code: str,
) -> dict[str, Any]:
    """What the draft looks like, and whether the chosen reader would get it.

    ``article`` is exactly the payload the reader-facing detail page consumes,
    built by the same :func:`feed_row` the feed uses, so the preview renders
    through the real renderer rather than an approximation of it. Nothing here
    makes the draft reachable: the payload is assembled for one authorized
    administrator inside their own page response.
    """
    selectors = selectors_for(announcement)
    context = preview_context(office=office, role_code=role_code)
    chosen = bool(office or role_code)
    matched = chosen and selectors.filter(selector_q(context)).exists()
    has_named_recipients = selectors.filter(kind="user").exists()
    return {
        "article": {
            **feed_row(announcement),
            "audience": describe_audience(announcement),
            "hero": hero_payload(announcement),
            "attachments": attachments_payload(announcement),
        },
        "reach": {
            "chosen": chosen,
            "matched": matched,
            "officeId": office.pk if office else None,
            "officeName": office.name if office else "",
            "roleCode": role_code,
            "hasNamedRecipients": has_named_recipients,
        },
    }


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #


def publication_history(announcement: Announcement) -> list[dict[str, str]]:
    """The lifecycle story of one announcement, newest first.

    Read from the audit trail rather than from a second table of its own: the
    audit rows are already written for every transition and are the record that
    governance answers from, so a separate history table could only ever be a
    copy that drifts.
    """
    rows = AuditEvent.objects.filter(
        action__in=tuple(HISTORY_ACTIONS),
        target_type=Announcement._meta.label_lower,
        target_id=str(announcement.pk),
        outcome=AuditEvent.Outcome.SUCCESS,
    ).order_by("-occurred_at", "-recorded_at")[:HISTORY_LIMIT]
    history: list[dict[str, str]] = []
    for row in rows:
        label, tone = HISTORY_ACTIONS[row.action]
        history.append(
            {
                "id": str(row.pk),
                "action": row.action,
                "label": label,
                "tone": tone,
                "actor": row.actor_label,
                "occurredAt": row.occurred_at.isoformat(),
            }
        )
    return history


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #

AUDIENCE_KINDS = ("company", "role", "region", "office", "user")


@dataclass(frozen=True)
class WorkspaceFilters:
    """Validated workspace filters. Every value narrows; none can widen.

    Unknown values are dropped rather than applied, exactly as the reader-facing
    feed filters behave, so a stale bookmark shows fewer rows than expected and
    never more.
    """

    q: str = ""
    lifecycle: str = ""
    category: str = ""
    priority: str = ""
    audience: str = ""
    author: str = ""
    office: str = ""
    published_from: str = ""
    published_to: str = ""

    @classmethod
    def from_params(cls, params, *, known_categories, known_priorities) -> Any:
        from apps.announcements.taxonomy import PRIORITY_CODES

        def pick(name: str, allowed) -> str:
            value = (params.get(name) or "").strip()[:40]
            return value if value in allowed else ""

        return cls(
            q=(params.get("q") or "").strip()[:120],
            lifecycle=pick(
                "lifecycle",
                {"draft", "scheduled", "live", "expired", "archived"},
            ),
            category=pick("category", set(known_categories)),
            priority=pick("priority", set(known_priorities) & set(PRIORITY_CODES)),
            audience=pick("audience", set(AUDIENCE_KINDS)),
            author=(params.get("author") or "").strip()[:120],
            office=(params.get("office") or "").strip()[:12],
            published_from=(params.get("publishedFrom") or "").strip()[:10],
            published_to=(params.get("publishedTo") or "").strip()[:10],
        )

    def as_payload(self) -> dict[str, str]:
        return {
            "q": self.q,
            "lifecycle": self.lifecycle,
            "category": self.category,
            "priority": self.priority,
            "audience": self.audience,
            "author": self.author,
            "office": self.office,
            "publishedFrom": self.published_from,
            "publishedTo": self.published_to,
        }

    @property
    def active_count(self) -> int:
        return sum(
            1
            for value in (
                self.q,
                self.lifecycle,
                self.category,
                self.priority,
                self.audience,
                self.author,
                self.office,
                self.published_from,
                self.published_to,
            )
            if value
        )


def apply_workspace_filters(
    queryset: QuerySet[Announcement], filters: WorkspaceFilters, *, now=None
) -> QuerySet[Announcement]:
    """Narrow only. Called after :func:`manageable_queryset`, never instead."""
    from django.utils.dateparse import parse_date

    moment = now or timezone.now()
    if filters.q:
        queryset = queryset.filter(
            Q(title__icontains=filters.q)
            | Q(summary__icontains=filters.q)
            | Q(slug__icontains=filters.q)
        )
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.priority:
        queryset = queryset.filter(priority=filters.priority)
    if filters.audience:
        queryset = queryset.filter(audiences__kind=filters.audience).distinct()
    if filters.author:
        queryset = queryset.filter(
            Q(created_by__email__icontains=filters.author)
            | Q(created_by__first_name__icontains=filters.author)
            | Q(created_by__last_name__icontains=filters.author)
        )
    if filters.office.isdigit():
        # Never trusted as authority: the queryset is already bounded by the
        # actor's scope, so an office id outside it simply matches nothing.
        queryset = queryset.filter(owner_office_id=int(filters.office))
    start = parse_date(filters.published_from) if filters.published_from else None
    if start:
        queryset = queryset.filter(published_at__date__gte=start)
    end = parse_date(filters.published_to) if filters.published_to else None
    if end:
        queryset = queryset.filter(published_at__date__lte=end)
    return _apply_lifecycle(queryset, filters.lifecycle, moment)


def _apply_lifecycle(queryset, lifecycle: str, moment):
    """Lifecycle is derived, so the filter is expressed the same way.

    The stored ``status`` column cannot answer "scheduled" or "expired" on its
    own; both are ``published`` plus a window test. Writing the same predicate
    the feed uses here is what keeps the filter honest.
    """
    if not lifecycle:
        return queryset
    if lifecycle == "draft":
        return queryset.filter(status=Announcement.Status.DRAFT)
    if lifecycle == "archived":
        return queryset.filter(status=Announcement.Status.ARCHIVED)
    published = queryset.filter(status=Announcement.Status.PUBLISHED)
    if lifecycle == "scheduled":
        return published.filter(publish_at__gt=moment)
    if lifecycle == "expired":
        return published.filter(expires_at__lte=moment)
    return published.filter(
        Q(publish_at__isnull=True) | Q(publish_at__lte=moment),
        Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
    )


def order_for_workspace(queryset: QuerySet[Announcement]) -> QuerySet[Announcement]:
    """Most recently touched first — the workspace is a work queue, not a feed."""
    return queryset.order_by("-updated_at", "-pk")


def category_options(*, include_codes=()) -> list[dict[str, str]]:
    extra = {code for code in include_codes if code}
    rows = AnnouncementCategory.objects.filter(Q(is_active=True) | Q(code__in=extra))
    return [{"value": row.code, "label": row.label} for row in rows]


# --------------------------------------------------------------------------- #
# Payloads
# --------------------------------------------------------------------------- #


def admin_row(announcement: Announcement, *, now=None) -> dict[str, Any]:
    """One workspace table row. camelCase, and never a styling decision."""
    from apps.announcements.presentation import present_category, present_priority

    return {
        "id": announcement.pk,
        "slug": announcement.slug,
        "title": announcement.title,
        "summary": announcement.summary,
        "lifecycle": lifecycle_state(announcement, now=now),
        "status": announcement.status,
        "category": present_category(announcement.category),
        "priority": present_priority(announcement.priority),
        "isPinned": announcement.is_pinned,
        "ownerOffice": {
            "id": announcement.owner_office.pk,
            "name": announcement.owner_office.name,
        },
        "scopeLevel": announcement.scope_level,
        "audience": describe_audience(announcement),
        "publishAt": _iso(announcement.publish_at),
        "expiresAt": _iso(announcement.expires_at),
        "publishedAt": _iso(announcement.published_at),
        "updatedAt": _iso(announcement.updated_at),
        "updatedBy": _actor_label(announcement.updated_by),
        "createdBy": _actor_label(announcement.created_by),
        "version": announcement_version(announcement),
    }


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def detail_payload(announcement: Announcement, *, now=None) -> dict[str, Any]:
    """Everything the workspace form needs about one record."""
    return {
        **admin_row(announcement, now=now),
        "body": announcement.body,
        "categoryCode": (announcement.category.code if announcement.category else ""),
        "priorityCode": announcement.priority,
        "cta": (
            {"label": announcement.cta_label, "url": announcement.cta_url}
            if announcement.cta_label and announcement.cta_url
            else None
        ),
        "source": (
            {
                "url": announcement.source_url,
                "publisher": announcement.source_publisher,
                "retrievedAt": _iso(announcement.source_retrieved_at),
            }
            if announcement.source_url
            else None
        ),
        "aiAssisted": {
            "summary": announcement.ai_assisted_summary,
            "body": announcement.ai_assisted_body,
        },
        "validation": validation_debt_payload(announcement),
        "history": publication_history(announcement),
        "mediaHref": f"/operations/announcements/{announcement.pk}/media",
    }


def audience_choice_payload(actor: User) -> dict[str, Any]:
    """The selectors this actor may hand out — and nothing wider.

    Derived from the actor's own grant, so a control can never offer an office
    or a role the save would refuse. The server checks the same boundary again
    in ``assert_can_target``; this only keeps the form honest.
    """
    from apps.user.roles import ROLE_BY_KEY
    from apps.user.services.role_assignments import get_effective_access

    office_ids = targetable_office_ids(actor)
    offices = (
        Office.objects.filter(pk__in=office_ids, is_active=True)
        .order_by("sort_order", "name")
        .values("pk", "name", "kind")
    )
    access = get_effective_access(actor)
    roles = sorted(targetable_role_codes(actor))
    return {
        "canTargetCompany": bool(
            getattr(actor, "is_superuser", False) or access.company_wide
        ),
        "regions": [
            {"value": row["pk"], "label": row["name"]}
            for row in offices
            if row["kind"] in {Office.Kind.HEAD_OFFICE, Office.Kind.REGION}
        ],
        "offices": [
            {"value": row["pk"], "label": row["name"]}
            for row in offices
            if row["kind"] not in {Office.Kind.HEAD_OFFICE, Office.Kind.REGION}
        ],
        "roles": [
            {
                "value": code,
                "label": ROLE_BY_KEY[code].label if code in ROLE_BY_KEY else code,
            }
            for code in roles
        ],
    }


def stored_selectors(announcement: Announcement) -> list[AudienceSelector]:
    return [
        AudienceSelector(kind=row.kind, role=row.role, office=row.office, user=row.user)
        for row in selectors_for(announcement)
    ]
