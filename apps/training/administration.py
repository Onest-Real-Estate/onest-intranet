"""Training workspace: authority, lifecycle, versioning, concurrency, and history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.training.audience import (
    AudienceContext,
    AudienceSelector,
    describe_audience,
    replace_audience,
    selector_q,
    selectors_for,
    targetable_office_ids,
    targetable_role_codes,
)
from apps.training.embeds import parse_embed_url
from apps.training.media_service import (
    admin_media_payload,
    attachments_payload,
    clone_media_to,
    primary_media_detail_payload,
)
from apps.training.models import (
    TrainingCategory,
    TrainingContent,
    TrainingEmbed,
    TrainingModule,
    TrainingProgress,
    TrainingTranscription,
)
from apps.training.presentation import present_category, present_content_type
from apps.training.services import (
    detail_payload as learner_detail_payload,
)
from apps.training.services import (
    validation_debt,
    validation_debt_payload,
)
from apps.training.taxonomy import CONTENT_TYPE_CODES
from apps.user.models import Office, User
from apps.user.services.hierarchy import ancestors
from apps.user.services.role_assignments import has_effective_permission

MANAGE_PERMISSION = "web.manage_training"

DRAFT_EDITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "summary",
    "body",
    "category",
    "content_type",
    "estimated_minutes",
    "tool_code",
    "external_url",
    "publish_at",
    "expires_at",
    "is_required",
)

PUBLISHED_EDITABLE_FIELDS: tuple[str, ...] = (
    "publish_at",
    "expires_at",
    "is_required",
)

HISTORY_ACTIONS: dict[str, tuple[str, str]] = {
    "training.created": ("Draft created", "neutral"),
    "training.updated": ("Draft edited", "neutral"),
    "training.audience_changed": ("Audience changed", "info"),
    "training.required_changed": ("Required state changed", "info"),
    "training.scheduled": ("Scheduled", "info"),
    "training.published": ("Published", "success"),
    "training.unpublished": ("Returned to draft", "warning"),
    "training.archived": ("Archived", "neutral"),
    "training.restored": ("Restored as draft", "info"),
    "training.version_created": ("New version drafted", "info"),
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
AUDIENCE_KINDS = ("company", "role", "region", "office", "user")


class StaleTrainingVersion(ValidationError):
    message: str

    def __init__(self):
        self.message = str(
            _(
                "Somebody else saved this training while you were writing. "
                "Review their version before applying your changes."
            )
        )
        super().__init__(self.message)


class TransitionRefused(ValidationError):
    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class Capabilities:
    can_author: bool
    can_publish: bool

    def payload(self) -> dict[str, bool]:
        return {
            "canAuthor": self.can_author,
            "canPublish": self.can_publish,
        }


def capabilities(actor: User) -> Capabilities:
    can = has_effective_permission(actor, MANAGE_PERMISSION)
    return Capabilities(can_author=can, can_publish=can)


def _deny(actor: User, content: TrainingContent | None, *, reason: str) -> None:
    log_event(
        "security.training.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=TrainingContent._meta.label_lower,
            target_id=str(content.pk) if content and content.pk else "",
            target_label=content.slug if content else "",
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def manageable_office_ids(actor: User) -> frozenset[int]:
    from apps.web.authorization import scope_queryset_for_offices

    return frozenset(
        scope_queryset_for_offices(actor, Office.objects.all()).values_list(
            "pk", flat=True
        )
    )


def publishable_office_queryset(actor: User) -> QuerySet[Office]:
    base = Office.objects.filter(is_active=True).select_related(
        "parent", "parent__parent", "parent__parent__parent", "region"
    )
    return base.filter(pk__in=manageable_office_ids(actor)).order_by(
        "sort_order", "name"
    )


def manageable_queryset(actor: User) -> QuerySet[TrainingContent]:
    base = TrainingContent.objects.select_related(
        "owner_office", "category", "created_by", "updated_by"
    )
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        return base.none()
    office_ids = manageable_office_ids(actor)
    if not office_ids:
        return base.none()
    return base.filter(owner_office_id__in=office_ids)


def assert_can_author(actor: User, office: Office) -> None:
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _deny(actor, None, reason="missing_permission")
        raise PermissionDenied("You cannot manage training.")
    if office.pk not in manageable_office_ids(actor):
        _deny(actor, None, reason="out_of_scope_office")
        raise PermissionDenied("That office is outside your training scope.")


def assert_can_publish(actor: User, content: TrainingContent) -> None:
    assert_can_author(actor, content.owner_office)


def content_version(content: TrainingContent) -> str:
    return content.updated_at.isoformat() if content.updated_at else ""


def _assert_fresh(content: TrainingContent, expected_version: str) -> None:
    if content_version(content) != (expected_version or ""):
        raise StaleTrainingVersion()


def snapshot(content: TrainingContent) -> dict[str, Any]:
    return {
        "slug": content.slug,
        "title": content.title,
        "summary": content.summary,
        "status": content.status,
        "category": content.category.code if content.category else None,
        "content_type": content.content_type,
        "is_required": content.is_required,
        "owner_office": content.owner_office.stable_key,
        "publish_at": content.publish_at,
        "expires_at": content.expires_at,
        "published_at": content.published_at,
        "archived_at": content.archived_at,
        "version_family": str(content.version_family),
        "version_number": content.version_number,
        "audience": describe_audience(content),
    }


def lifecycle_state(content: TrainingContent, *, now=None) -> dict[str, str]:
    moment = now or timezone.now()
    if content.status == TrainingContent.Status.DRAFT:
        return {"code": "draft", "label": "Draft", "tone": "neutral"}
    if content.status == TrainingContent.Status.ARCHIVED:
        return {"code": "archived", "label": "Archived", "tone": "neutral"}
    if content.publish_at is not None and content.publish_at > moment:
        return {"code": "scheduled", "label": "Scheduled", "tone": "info"}
    if content.expires_at is not None and content.expires_at <= moment:
        return {"code": "expired", "label": "Expired", "tone": "warning"}
    return {"code": "live", "label": "Live", "tone": "success"}


def _actor_label(user: User | None) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.email


def build_slug(title: str, *, office: Office, exclude_pk: int | None = None) -> str:
    base = slugify(title)[:70] or "training"
    taken = set(
        TrainingContent.objects.filter(owner_office=office)
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
        {"title": _("Too many training items share this title in that office.")}
    )


def _version_slug(base_slug: str, version_number: int, *, office: Office) -> str:
    suffix = f"-v{version_number}"
    stem = base_slug[: 80 - len(suffix)] or "training"
    candidate = f"{stem}{suffix}"
    taken = set(
        TrainingContent.objects.filter(owner_office=office).values_list(
            "slug", flat=True
        )
    )
    if candidate not in taken:
        return candidate
    for extra in range(2, 100):
        alt = f"{stem[: 80 - len(suffix) - len(str(extra)) - 1]}{suffix}-{extra}"
        if alt not in taken:
            return alt
    raise ValidationError(
        {"title": _("Could not allocate a unique slug for this version.")}
    )


def _log(
    action: str,
    *,
    actor: User,
    content: TrainingContent,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    log_event(
        action,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=TrainingContent._meta.label_lower,
            target_id=str(content.pk),
            target_label=content.slug,
        ),
        before=before or {},
        after=after or {},
    )


def _apply_fields(
    content: TrainingContent, cleaned: dict[str, Any], *, fields: tuple[str, ...]
) -> None:
    for name in fields:
        if name in cleaned:
            setattr(content, name, cleaned[name])


def _set_embed(content: TrainingContent, url: str) -> None:
    url = (url or "").strip()
    existing = TrainingEmbed.objects.filter(content=content).first()
    if not url:
        if existing:
            existing.delete()
        return
    parsed = parse_embed_url(url)
    if parsed is None:
        raise ValidationError({"embed_url": _("That embed URL is not allowed.")})
    if existing is None:
        existing = TrainingEmbed(content=content)
    existing.url = url
    existing.provider = parsed.provider
    existing.host = parsed.host
    existing.full_clean()
    existing.save()


def create_content(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    embed_url: str = "",
) -> TrainingContent:
    assert_can_author(actor, office)
    return _create(
        actor=actor,
        office=office,
        cleaned=cleaned,
        selectors=selectors,
        embed_url=embed_url,
    )


@transaction.atomic
def _create(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    embed_url: str,
) -> TrainingContent:
    content = TrainingContent(
        owner_office=office,
        slug=build_slug(cleaned.get("title", ""), office=office),
        status=TrainingContent.Status.DRAFT,
        version_family=uuid4(),
        version_number=1,
        created_by=actor,
        updated_by=actor,
    )
    _apply_fields(content, cleaned, fields=DRAFT_EDITABLE_FIELDS)
    content.full_clean(exclude=["owner_office", "slug"])
    content.save()
    replace_audience(actor, content, selectors)
    _set_embed(content, embed_url)
    _log(
        "training.created",
        actor=actor,
        content=content,
        before=None,
        after=snapshot(content),
    )
    return content


def update_content(
    *,
    actor: User,
    content: TrainingContent,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
    embed_url: str | None = None,
) -> TrainingContent:
    assert_can_author(actor, content.owner_office)
    return _update(
        actor=actor,
        content=content,
        cleaned=cleaned,
        selectors=selectors,
        expected_version=expected_version,
        embed_url=embed_url,
    )


@transaction.atomic
def _update(
    *,
    actor: User,
    content: TrainingContent,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
    embed_url: str | None,
) -> TrainingContent:
    locked = _lock(content.pk)
    assert_can_author(actor, locked.owner_office)
    _assert_fresh(locked, expected_version)
    before = snapshot(locked)
    was_required = locked.is_required

    if locked.status == TrainingContent.Status.DRAFT:
        fields = DRAFT_EDITABLE_FIELDS
    elif locked.status == TrainingContent.Status.PUBLISHED:
        fields = PUBLISHED_EDITABLE_FIELDS
    else:
        raise TransitionRefused(
            str(_("Archived training cannot be edited. Restore it first."))
        )

    forbidden = set(cleaned) - set(fields)
    body_touched = any(
        key in cleaned
        for key in ("title", "summary", "body", "category", "content_type", "tool_code")
    )
    if locked.status != TrainingContent.Status.DRAFT and (
        forbidden or body_touched or embed_url is not None
    ):
        # Allow only window/required/audience on published rows.
        cleaned = {key: cleaned[key] for key in fields if key in cleaned}
        embed_url = None

    _apply_fields(locked, cleaned, fields=fields)
    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office", "slug"])
    locked.save()
    replace_audience(actor, locked, selectors)
    if embed_url is not None and locked.status == TrainingContent.Status.DRAFT:
        _set_embed(locked, embed_url)

    after = snapshot(locked)
    _log(
        "training.updated",
        actor=actor,
        content=locked,
        before=before,
        after=after,
    )
    if was_required != locked.is_required:
        _log(
            "training.required_changed",
            actor=actor,
            content=locked,
            before={"is_required": was_required},
            after={"is_required": locked.is_required},
        )
    return locked


def _lock(pk: int) -> TrainingContent:
    return (
        TrainingContent.objects.select_for_update(of=("self",))
        .select_related("owner_office", "category")
        .get(pk=pk)
    )


def transition(
    *,
    actor: User,
    content: TrainingContent,
    action: str,
    expected_version: str,
    now=None,
) -> TrainingContent:
    if action not in TRANSITIONS:
        raise TransitionRefused(str(_("That is not a training action.")))
    assert_can_publish(actor, content)
    return _transition(
        actor=actor,
        content=content,
        action=action,
        expected_version=expected_version,
        now=now,
    )


@transaction.atomic
def _transition(
    *,
    actor: User,
    content: TrainingContent,
    action: str,
    expected_version: str,
    now=None,
) -> TrainingContent:
    moment = now or timezone.now()
    locked = _lock(content.pk)
    assert_can_publish(actor, locked)
    _assert_fresh(locked, expected_version)
    before = snapshot(locked)

    if action in {"publish", "schedule"}:
        return _go_live(
            actor=actor, locked=locked, scheduled=action == "schedule", now=moment
        )

    if action == "unpublish":
        if locked.status != TrainingContent.Status.PUBLISHED:
            raise TransitionRefused(
                str(_("Only published training can be returned to draft."))
            )
        locked.status = TrainingContent.Status.DRAFT
        locked.published_at = None
        event_name = "training.unpublished"
    elif action == "archive":
        if locked.status == TrainingContent.Status.ARCHIVED:
            raise TransitionRefused(str(_("This training is already archived.")))
        locked.status = TrainingContent.Status.ARCHIVED
        locked.archived_at = moment
        event_name = "training.archived"
    else:
        if locked.status != TrainingContent.Status.ARCHIVED:
            raise TransitionRefused(str(_("Only archived training can be restored.")))
        locked.status = TrainingContent.Status.DRAFT
        locked.archived_at = None
        locked.published_at = None
        event_name = "training.restored"

    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office", "slug"])
    locked.save()
    _log(
        event_name,
        actor=actor,
        content=locked,
        before=before,
        after=snapshot(locked),
    )
    _emit_lifecycle(event_name, actor=actor, content=locked, now=moment)
    return locked


def _stored_selectors(content: TrainingContent) -> list[AudienceSelector]:
    return [
        AudienceSelector(
            kind=row.kind,
            role=row.role,
            office=row.office,
            user=row.user,
        )
        for row in selectors_for(content)
    ]


def _go_live(
    *, actor: User, locked: TrainingContent, scheduled: bool, now
) -> TrainingContent:
    from apps.training.audience import assert_can_target

    if locked.status == TrainingContent.Status.PUBLISHED:
        raise TransitionRefused(str(_("This training is already published.")))
    if scheduled and (locked.publish_at is None or locked.publish_at <= now):
        raise TransitionRefused(
            str(_("Set a publish time in the future before scheduling."))
        )
    if not scheduled and locked.publish_at is not None and locked.publish_at > now:
        raise TransitionRefused(
            str(
                _(
                    "This training is dated for the future. Schedule it, or "
                    "clear the publish time to publish it now."
                )
            )
        )

    before = snapshot(locked)
    debt = validation_debt(locked)
    if debt:
        raise ValidationError(dict(debt))
    assert_can_target(actor, _stored_selectors(locked))

    if locked.version_number > 1:
        _supersede_previous_live(actor=actor, locked=locked, now=now)

    locked.status = TrainingContent.Status.PUBLISHED
    locked.published_at = locked.published_at or now
    locked.archived_at = None
    locked.updated_by = actor
    locked.full_clean()
    locked.save()

    event_name = "training.scheduled" if scheduled else "training.published"
    _log(
        event_name,
        actor=actor,
        content=locked,
        before=before,
        after=snapshot(locked),
    )
    _emit_lifecycle(event_name, actor=actor, content=locked, now=now)
    return locked


def _supersede_previous_live(*, actor: User, locked: TrainingContent, now) -> None:
    siblings = (
        TrainingContent.objects.select_for_update(of=("self",))
        .filter(
            version_family=locked.version_family,
            status=TrainingContent.Status.PUBLISHED,
        )
        .exclude(pk=locked.pk)
    )
    for sibling in siblings:
        before = snapshot(sibling)
        sibling.status = TrainingContent.Status.ARCHIVED
        sibling.archived_at = now
        sibling.updated_by = actor
        sibling.save(
            update_fields=["status", "archived_at", "updated_by", "updated_at"]
        )
        _log(
            "training.archived",
            actor=actor,
            content=sibling,
            before=before,
            after=snapshot(sibling),
        )
        _emit_lifecycle("training.archived", actor=actor, content=sibling, now=now)


def duplicate_version(
    *, actor: User, content: TrainingContent, expected_version: str
) -> TrainingContent:
    assert_can_author(actor, content.owner_office)
    return _duplicate_version(
        actor=actor, content=content, expected_version=expected_version
    )


@transaction.atomic
def _duplicate_version(
    *, actor: User, content: TrainingContent, expected_version: str
) -> TrainingContent:
    source = _lock(content.pk)
    assert_can_author(actor, source.owner_office)
    _assert_fresh(source, expected_version)

    next_number = (
        TrainingContent.objects.filter(version_family=source.version_family).aggregate(
            Max("version_number")
        )["version_number__max"]
        or source.version_number
    ) + 1

    draft = TrainingContent(
        owner_office=source.owner_office,
        slug=_version_slug(source.slug, next_number, office=source.owner_office),
        title=source.title,
        summary=source.summary,
        body=source.body,
        content_type=source.content_type,
        category=source.category,
        is_required=source.is_required,
        estimated_minutes=source.estimated_minutes,
        tool_code=source.tool_code,
        external_url=source.external_url,
        status=TrainingContent.Status.DRAFT,
        publish_at=None,
        expires_at=source.expires_at,
        display_order=source.display_order,
        version_family=source.version_family,
        version_number=next_number,
        version_completion_policy=source.version_completion_policy,
        created_by=actor,
        updated_by=actor,
    )
    draft.full_clean(exclude=["owner_office", "slug"])
    draft.save()

    replace_audience(actor, draft, _stored_selectors(source))

    embed = TrainingEmbed.objects.filter(content=source).first()
    if embed is not None:
        TrainingEmbed.objects.create(
            content=draft,
            url=embed.url,
            provider=embed.provider,
            host=embed.host,
        )

    transcription = TrainingTranscription.objects.filter(content=source).first()
    if transcription is not None:
        clone_tx = TrainingTranscription(
            content=draft,
            segments=transcription.segments,
        )
        clone_tx.rebuild_search_text()
        clone_tx.save()

    for module in TrainingModule.objects.filter(course=source).order_by(
        "sort_order", "pk"
    ):
        TrainingModule.objects.create(
            course=draft, child=module.child, sort_order=module.sort_order
        )

    from apps.training.models import (
        TrainingLiveSession,
        TrainingQuiz,
        TrainingQuizQuestion,
    )

    quiz = TrainingQuiz.objects.filter(content=source).first()
    if quiz is not None:
        clone_quiz = TrainingQuiz.objects.create(
            content=draft,
            pass_threshold_percent=quiz.pass_threshold_percent,
            max_attempts=quiz.max_attempts,
            feedback_policy=quiz.feedback_policy,
        )
        TrainingQuizQuestion.objects.bulk_create(
            [
                TrainingQuizQuestion(
                    quiz=clone_quiz,
                    prompt=question.prompt,
                    choices=question.choices,
                    correct_choice_ids=question.correct_choice_ids,
                    sort_order=question.sort_order,
                )
                for question in TrainingQuizQuestion.objects.filter(quiz=quiz).order_by(
                    "sort_order", "pk"
                )
            ]
        )

    session = TrainingLiveSession.objects.filter(content=source).first()
    if session is not None:
        TrainingLiveSession.objects.create(
            content=draft,
            starts_at=session.starts_at,
            timezone=session.timezone,
            duration_minutes=session.duration_minutes,
            capacity=session.capacity,
            meeting_url=session.meeting_url,
            registration_opens_at=session.registration_opens_at,
            registration_closes_at=session.registration_closes_at,
        )

    clone_media_to(actor, source, draft)

    _log(
        "training.version_created",
        actor=actor,
        content=draft,
        before={"source_id": source.pk, "source_version": source.version_number},
        after=snapshot(draft),
    )
    return draft


def _emit_lifecycle(name: str, *, actor: User, content: TrainingContent, now) -> None:
    publish_event(
        name,
        actor_id=str(actor.pk),
        subject=str(content.pk),
        payload={
            "content_id": content.pk,
            "owner_office_id": content.owner_office.pk,
            "scope_level": content.scope_level,
            "status": content.status,
            "version_number": content.version_number,
            "version_family": str(content.version_family),
            "occurred_at": now.isoformat(),
        },
    )


def preview_context(*, office: Office | None, role_code: str) -> AudienceContext:
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
    content: TrainingContent,
    *,
    actor: User,
    office: Office | None,
    role_code: str,
) -> dict[str, Any]:
    selectors = selectors_for(content)
    context = preview_context(office=office, role_code=role_code)
    chosen = bool(office or role_code)
    matched = chosen and selectors.filter(selector_q(context)).exists()
    has_named_recipients = selectors.filter(kind="user").exists()
    article = learner_detail_payload(content, user=actor)
    # Preview must not invent completion for the admin.
    article["completion"] = {"status": "not_started", "label": "Not Started"}
    return {
        "article": {
            **article,
            "audience": describe_audience(content),
            "primaryMedia": primary_media_detail_payload(content),
            "attachments": attachments_payload(content),
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


def publication_history(content: TrainingContent) -> list[dict[str, str]]:
    rows = AuditEvent.objects.filter(
        action__in=tuple(HISTORY_ACTIONS),
        target_type=TrainingContent._meta.label_lower,
        target_id=str(content.pk),
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


def usage_payload(content: TrainingContent) -> dict[str, int]:
    from apps.training.audience import recipients_for

    progress = TrainingProgress.objects.filter(content=content).aggregate(
        completed=Count("pk", filter=Q(status=TrainingProgress.Status.COMPLETED)),
        in_progress=Count("pk", filter=Q(status=TrainingProgress.Status.IN_PROGRESS)),
        not_started=Count("pk", filter=Q(status=TrainingProgress.Status.NOT_STARTED)),
    )
    return {
        "recipientEstimate": recipients_for(content).count(),
        "completed": progress["completed"] or 0,
        "inProgress": progress["in_progress"] or 0,
        "notStarted": progress["not_started"] or 0,
    }


@dataclass(frozen=True)
class WorkspaceFilters:
    q: str = ""
    lifecycle: str = ""
    category: str = ""
    content_type: str = ""
    audience: str = ""
    author: str = ""
    office: str = ""
    required: str = ""
    published_from: str = ""
    published_to: str = ""

    @classmethod
    def from_params(cls, params, *, known_categories) -> WorkspaceFilters:
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
            content_type=pick("type", set(CONTENT_TYPE_CODES)),
            audience=pick("audience", set(AUDIENCE_KINDS)),
            author=(params.get("author") or "").strip()[:120],
            office=(params.get("office") or "").strip()[:12],
            required=pick("required", {"true", "false"}),
            published_from=(params.get("publishedFrom") or "").strip()[:10],
            published_to=(params.get("publishedTo") or "").strip()[:10],
        )

    def as_payload(self) -> dict[str, str]:
        return {
            "q": self.q,
            "lifecycle": self.lifecycle,
            "category": self.category,
            "type": self.content_type,
            "audience": self.audience,
            "author": self.author,
            "office": self.office,
            "required": self.required,
            "publishedFrom": self.published_from,
            "publishedTo": self.published_to,
        }


def apply_workspace_filters(
    queryset: QuerySet[TrainingContent], filters: WorkspaceFilters, *, now=None
) -> QuerySet[TrainingContent]:
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
    if filters.content_type:
        queryset = queryset.filter(content_type=filters.content_type)
    if filters.audience:
        queryset = queryset.filter(audiences__kind=filters.audience).distinct()
    if filters.author:
        queryset = queryset.filter(
            Q(created_by__email__icontains=filters.author)
            | Q(created_by__first_name__icontains=filters.author)
            | Q(created_by__last_name__icontains=filters.author)
        )
    if filters.office.isdigit():
        queryset = queryset.filter(owner_office_id=int(filters.office))
    if filters.required == "true":
        queryset = queryset.filter(is_required=True)
    elif filters.required == "false":
        queryset = queryset.filter(is_required=False)
    start = parse_date(filters.published_from) if filters.published_from else None
    if start:
        queryset = queryset.filter(published_at__date__gte=start)
    end = parse_date(filters.published_to) if filters.published_to else None
    if end:
        queryset = queryset.filter(published_at__date__lte=end)
    return _apply_lifecycle(queryset, filters.lifecycle, moment)


def _apply_lifecycle(queryset, lifecycle: str, moment):
    if not lifecycle:
        return queryset
    if lifecycle == "draft":
        return queryset.filter(status=TrainingContent.Status.DRAFT)
    if lifecycle == "archived":
        return queryset.filter(status=TrainingContent.Status.ARCHIVED)
    published = queryset.filter(status=TrainingContent.Status.PUBLISHED)
    if lifecycle == "scheduled":
        return published.filter(publish_at__gt=moment)
    if lifecycle == "expired":
        return published.filter(expires_at__lte=moment)
    return published.filter(
        Q(publish_at__isnull=True) | Q(publish_at__lte=moment),
        Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
    )


def order_for_workspace(
    queryset: QuerySet[TrainingContent],
) -> QuerySet[TrainingContent]:
    return queryset.order_by("-updated_at", "-pk")


def category_options(*, include_codes=()) -> list[dict[str, str]]:
    extra = {code for code in include_codes if code}
    rows = TrainingCategory.objects.filter(Q(is_active=True) | Q(code__in=extra))
    return [{"value": row.code, "label": row.label} for row in rows]


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def admin_row(content: TrainingContent, *, now=None) -> dict[str, Any]:
    return {
        "id": content.pk,
        "slug": content.slug,
        "title": content.title,
        "summary": content.summary,
        "lifecycle": lifecycle_state(content, now=now),
        "status": content.status,
        "contentType": present_content_type(content.content_type),
        "category": present_category(content.category),
        "isRequired": content.is_required,
        "versionNumber": content.version_number,
        "versionLabel": f"v{content.version_number}",
        "ownerOffice": {
            "id": content.owner_office.pk,
            "name": content.owner_office.name,
        },
        "scopeLevel": content.scope_level,
        "audience": describe_audience(content),
        "publishAt": _iso(content.publish_at),
        "expiresAt": _iso(content.expires_at),
        "publishedAt": _iso(content.published_at),
        "updatedAt": _iso(content.updated_at),
        "updatedBy": _actor_label(content.updated_by),
        "createdBy": _actor_label(content.created_by),
        "version": content_version(content),
    }


def detail_payload(content: TrainingContent, *, now=None) -> dict[str, Any]:
    from apps.training.course_service import admin_modules_payload
    from apps.training.quiz_service import admin_quiz_payload
    from apps.training.session_service import admin_session_payload

    embed = TrainingEmbed.objects.filter(content=content).first()
    return {
        **admin_row(content, now=now),
        "body": content.body,
        "categoryCode": content.category.code if content.category else "",
        "contentTypeCode": content.content_type,
        "toolCode": content.tool_code,
        "externalUrl": content.external_url,
        "estimatedMinutes": content.estimated_minutes,
        "displayOrder": content.display_order,
        "embedUrl": embed.url if embed else "",
        "validation": validation_debt_payload(content),
        "history": publication_history(content),
        "usage": usage_payload(content),
        "media": admin_media_payload(content),
        "mediaHref": f"/operations/training/{content.pk}/media",
        "versionFamily": str(content.version_family),
        "versionCompletionPolicy": content.version_completion_policy,
        "quiz": admin_quiz_payload(content),
        "liveSession": admin_session_payload(content),
        "modules": admin_modules_payload(content),
    }


def audience_choice_payload(actor: User) -> dict[str, Any]:
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
