"""Marketing workspace: authority, lifecycle, versioning, concurrency, history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max, Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.marketing.audience import (
    AudienceContext,
    AudienceSelector,
    describe_audience,
    replace_audience,
    selector_q,
    selectors_for,
    targetable_office_ids,
    targetable_role_codes,
)
from apps.marketing.media_service import (
    DOWNLOAD_SOURCES,
    admin_files_payload,
    clone_files_to,
    export_files_payload,
)
from apps.marketing.models import MarketingAsset, MarketingCategory
from apps.marketing.presentation import present_asset_type, present_category
from apps.marketing.services import (
    detail_payload as consumer_detail_payload,
)
from apps.marketing.services import (
    validation_debt,
    validation_debt_payload,
)
from apps.marketing.taxonomy import ASSET_TYPE_CODES
from apps.user.models import Office, User
from apps.user.services.hierarchy import ancestors
from apps.user.services.role_assignments import has_effective_permission

MANAGE_PERMISSION = "web.manage_marketing_resources"
PUBLISH_PERMISSION = "web.publish_marketing_resources"

DRAFT_EDITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "usage_instructions",
    "category",
    "asset_type",
    "publish_at",
    "expires_at",
    "jurisdiction_state_codes",
    "brand_codes",
    "display_order",
)

PUBLISHED_EDITABLE_FIELDS: tuple[str, ...] = (
    "publish_at",
    "expires_at",
    "jurisdiction_state_codes",
    "brand_codes",
)

HISTORY_ACTIONS: dict[str, tuple[str, str]] = {
    "marketing.created": ("Draft created", "neutral"),
    "marketing.updated": ("Draft edited", "neutral"),
    "marketing.audience_changed": ("Audience changed", "info"),
    "marketing.scheduled": ("Scheduled", "info"),
    "marketing.published": ("Published", "success"),
    "marketing.unpublished": ("Returned to draft", "warning"),
    "marketing.archived": ("Archived", "neutral"),
    "marketing.restored": ("Restored as draft", "info"),
    "marketing.version_created": ("New version drafted", "info"),
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


class StaleMarketingVersion(ValidationError):
    message: str

    def __init__(self):
        self.message = str(
            _(
                "Somebody else saved this marketing asset while you were writing. "
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
    can_download_sources: bool

    def payload(self) -> dict[str, bool]:
        return {
            "canAuthor": self.can_author,
            "canPublish": self.can_publish,
            "canDownloadSources": self.can_download_sources,
        }


def capabilities(actor: User) -> Capabilities:
    return Capabilities(
        can_author=has_effective_permission(actor, MANAGE_PERMISSION),
        can_publish=has_effective_permission(actor, PUBLISH_PERMISSION),
        can_download_sources=has_effective_permission(actor, DOWNLOAD_SOURCES),
    )


def _deny(actor: User, asset: MarketingAsset | None, *, reason: str) -> None:
    log_event(
        "security.marketing.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=MarketingAsset._meta.label_lower,
            target_id=str(asset.pk) if asset and asset.pk else "",
            target_label=asset.slug if asset else "",
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


def manageable_queryset(actor: User) -> QuerySet[MarketingAsset]:
    base = MarketingAsset.objects.select_related(
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
        raise PermissionDenied("You cannot manage marketing resources.")
    if office.pk not in manageable_office_ids(actor):
        _deny(actor, None, reason="out_of_scope_office")
        raise PermissionDenied("That office is outside your marketing scope.")


def assert_can_publish(actor: User, asset: MarketingAsset) -> None:
    assert_can_author(actor, asset.owner_office)
    if not has_effective_permission(actor, PUBLISH_PERMISSION):
        _deny(actor, asset, reason="missing_publish_permission")
        raise PermissionDenied("You cannot publish or archive marketing resources.")


def asset_version(asset: MarketingAsset) -> str:
    return asset.updated_at.isoformat() if asset.updated_at else ""


def _assert_fresh(asset: MarketingAsset, expected_version: str) -> None:
    if asset_version(asset) != (expected_version or ""):
        raise StaleMarketingVersion()


def snapshot(asset: MarketingAsset) -> dict[str, Any]:
    return {
        "slug": asset.slug,
        "title": asset.title,
        "description": asset.description,
        "status": asset.status,
        "category": asset.category.code if asset.category else None,
        "asset_type": asset.asset_type,
        "owner_office": asset.owner_office.stable_key,
        "publish_at": asset.publish_at,
        "expires_at": asset.expires_at,
        "published_at": asset.published_at,
        "archived_at": asset.archived_at,
        "jurisdiction_state_codes": list(asset.jurisdiction_state_codes or []),
        "brand_codes": list(asset.brand_codes or []),
        "version_family": str(asset.version_family),
        "version_number": asset.version_number,
        "audience": describe_audience(asset),
    }


def lifecycle_state(asset: MarketingAsset, *, now=None) -> dict[str, str]:
    moment = now or timezone.now()
    if asset.status == MarketingAsset.Status.DRAFT:
        return {"code": "draft", "label": "Draft", "tone": "neutral"}
    if asset.status == MarketingAsset.Status.ARCHIVED:
        return {"code": "archived", "label": "Archived", "tone": "neutral"}
    if asset.publish_at is not None and asset.publish_at > moment:
        return {"code": "scheduled", "label": "Scheduled", "tone": "info"}
    if asset.expires_at is not None and asset.expires_at <= moment:
        return {"code": "expired", "label": "Expired", "tone": "warning"}
    return {"code": "live", "label": "Live", "tone": "success"}


def _actor_label(user: User | None) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.email


def build_slug(title: str, *, office: Office, exclude_pk: int | None = None) -> str:
    base = slugify(title)[:70] or "marketing"
    taken = set(
        MarketingAsset.objects.filter(owner_office=office)
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
        {"title": _("Too many marketing assets share this title in that office.")}
    )


def _version_slug(base_slug: str, version_number: int, *, office: Office) -> str:
    suffix = f"-v{version_number}"
    stem = base_slug[: 80 - len(suffix)] or "marketing"
    candidate = f"{stem}{suffix}"
    taken = set(
        MarketingAsset.objects.filter(owner_office=office).values_list(
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
    asset: MarketingAsset,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    log_event(
        action,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=MarketingAsset._meta.label_lower,
            target_id=str(asset.pk),
            target_label=asset.slug,
        ),
        before=before or {},
        after=after or {},
    )


def _apply_fields(
    asset: MarketingAsset, cleaned: dict[str, Any], *, fields: tuple[str, ...]
) -> None:
    for name in fields:
        if name in cleaned:
            setattr(asset, name, cleaned[name])


def create_asset(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
) -> MarketingAsset:
    assert_can_author(actor, office)
    return _create(actor=actor, office=office, cleaned=cleaned, selectors=selectors)


@transaction.atomic
def _create(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
) -> MarketingAsset:
    asset = MarketingAsset(
        owner_office=office,
        slug=build_slug(cleaned.get("title", ""), office=office),
        status=MarketingAsset.Status.DRAFT,
        version_family=uuid4(),
        version_number=1,
        created_by=actor,
        updated_by=actor,
    )
    _apply_fields(asset, cleaned, fields=DRAFT_EDITABLE_FIELDS)
    asset.full_clean(exclude=["owner_office", "slug"])
    asset.save()
    replace_audience(actor, asset, selectors)
    _log(
        "marketing.created",
        actor=actor,
        asset=asset,
        before=None,
        after=snapshot(asset),
    )
    return asset


def update_asset(
    *,
    actor: User,
    asset: MarketingAsset,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
) -> MarketingAsset:
    assert_can_author(actor, asset.owner_office)
    return _update(
        actor=actor,
        asset=asset,
        cleaned=cleaned,
        selectors=selectors,
        expected_version=expected_version,
    )


@transaction.atomic
def _update(
    *,
    actor: User,
    asset: MarketingAsset,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
) -> MarketingAsset:
    locked = _lock(asset.pk)
    assert_can_author(actor, locked.owner_office)
    _assert_fresh(locked, expected_version)
    before = snapshot(locked)

    if locked.status == MarketingAsset.Status.DRAFT:
        fields = DRAFT_EDITABLE_FIELDS
    elif locked.status == MarketingAsset.Status.PUBLISHED:
        fields = PUBLISHED_EDITABLE_FIELDS
    else:
        raise TransitionRefused(
            str(_("Archived marketing assets cannot be edited. Restore first."))
        )

    if locked.status != MarketingAsset.Status.DRAFT:
        cleaned = {key: cleaned[key] for key in fields if key in cleaned}

    _apply_fields(locked, cleaned, fields=fields)
    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office", "slug"])
    locked.save()
    replace_audience(actor, locked, selectors)

    after = snapshot(locked)
    _log(
        "marketing.updated",
        actor=actor,
        asset=locked,
        before=before,
        after=after,
    )
    return locked


def _lock(pk: int) -> MarketingAsset:
    return (
        MarketingAsset.objects.select_for_update(of=("self",))
        .select_related("owner_office", "category")
        .get(pk=pk)
    )


def transition(
    *,
    actor: User,
    asset: MarketingAsset,
    action: str,
    expected_version: str,
    now=None,
) -> MarketingAsset:
    if action not in TRANSITIONS:
        raise TransitionRefused(str(_("That is not a marketing action.")))
    assert_can_publish(actor, asset)
    return _transition(
        actor=actor,
        asset=asset,
        action=action,
        expected_version=expected_version,
        now=now,
    )


@transaction.atomic
def _transition(
    *,
    actor: User,
    asset: MarketingAsset,
    action: str,
    expected_version: str,
    now=None,
) -> MarketingAsset:
    moment = now or timezone.now()
    locked = _lock(asset.pk)
    assert_can_publish(actor, locked)
    _assert_fresh(locked, expected_version)
    before = snapshot(locked)

    if action in {"publish", "schedule"}:
        return _go_live(
            actor=actor, locked=locked, scheduled=action == "schedule", now=moment
        )

    if action == "unpublish":
        if locked.status != MarketingAsset.Status.PUBLISHED:
            raise TransitionRefused(
                str(_("Only published marketing assets can be returned to draft."))
            )
        locked.status = MarketingAsset.Status.DRAFT
        locked.published_at = None
        event_name = "marketing.unpublished"
    elif action == "archive":
        if locked.status == MarketingAsset.Status.ARCHIVED:
            raise TransitionRefused(str(_("This marketing asset is already archived.")))
        locked.status = MarketingAsset.Status.ARCHIVED
        locked.archived_at = moment
        event_name = "marketing.archived"
    else:
        if locked.status != MarketingAsset.Status.ARCHIVED:
            raise TransitionRefused(
                str(_("Only archived marketing assets can be restored."))
            )
        locked.status = MarketingAsset.Status.DRAFT
        locked.archived_at = None
        locked.published_at = None
        event_name = "marketing.restored"

    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office", "slug"])
    locked.save()
    _log(
        event_name,
        actor=actor,
        asset=locked,
        before=before,
        after=snapshot(locked),
    )
    _emit_lifecycle(event_name, actor=actor, asset=locked, now=moment)
    return locked


def _stored_selectors(asset: MarketingAsset) -> list[AudienceSelector]:
    return [
        AudienceSelector(
            kind=row.kind,
            role=row.role,
            office=row.office,
            user=row.user,
        )
        for row in selectors_for(asset)
    ]


def _go_live(
    *, actor: User, locked: MarketingAsset, scheduled: bool, now
) -> MarketingAsset:
    from apps.marketing.audience import assert_can_target

    if locked.status == MarketingAsset.Status.PUBLISHED:
        raise TransitionRefused(str(_("This marketing asset is already published.")))
    if scheduled and (locked.publish_at is None or locked.publish_at <= now):
        raise TransitionRefused(
            str(_("Set a publish time in the future before scheduling."))
        )
    if not scheduled and locked.publish_at is not None and locked.publish_at > now:
        raise TransitionRefused(
            str(
                _(
                    "This asset is dated for the future. Schedule it, or "
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

    locked.status = MarketingAsset.Status.PUBLISHED
    locked.published_at = locked.published_at or now
    locked.archived_at = None
    locked.updated_by = actor
    locked.full_clean()
    locked.save()

    event_name = "marketing.scheduled" if scheduled else "marketing.published"
    _log(
        event_name,
        actor=actor,
        asset=locked,
        before=before,
        after=snapshot(locked),
    )
    _emit_lifecycle(event_name, actor=actor, asset=locked, now=now)
    return locked


def _supersede_previous_live(*, actor: User, locked: MarketingAsset, now) -> None:
    siblings = (
        MarketingAsset.objects.select_for_update(of=("self",))
        .filter(
            version_family=locked.version_family,
            status=MarketingAsset.Status.PUBLISHED,
        )
        .exclude(pk=locked.pk)
    )
    for sibling in siblings:
        before = snapshot(sibling)
        sibling.status = MarketingAsset.Status.ARCHIVED
        sibling.archived_at = now
        sibling.updated_by = actor
        sibling.save(
            update_fields=["status", "archived_at", "updated_by", "updated_at"]
        )
        _log(
            "marketing.archived",
            actor=actor,
            asset=sibling,
            before=before,
            after=snapshot(sibling),
        )
        _emit_lifecycle("marketing.archived", actor=actor, asset=sibling, now=now)


def duplicate_version(
    *, actor: User, asset: MarketingAsset, expected_version: str
) -> MarketingAsset:
    assert_can_author(actor, asset.owner_office)
    return _duplicate_version(
        actor=actor, asset=asset, expected_version=expected_version
    )


@transaction.atomic
def _duplicate_version(
    *, actor: User, asset: MarketingAsset, expected_version: str
) -> MarketingAsset:
    source = _lock(asset.pk)
    assert_can_author(actor, source.owner_office)
    _assert_fresh(source, expected_version)

    next_number = (
        MarketingAsset.objects.filter(version_family=source.version_family).aggregate(
            Max("version_number")
        )["version_number__max"]
        or source.version_number
    ) + 1

    draft = MarketingAsset(
        owner_office=source.owner_office,
        slug=_version_slug(source.slug, next_number, office=source.owner_office),
        title=source.title,
        description=source.description,
        usage_instructions=source.usage_instructions,
        asset_type=source.asset_type,
        category=source.category,
        jurisdiction_state_codes=list(source.jurisdiction_state_codes or []),
        brand_codes=list(source.brand_codes or []),
        status=MarketingAsset.Status.DRAFT,
        publish_at=None,
        expires_at=source.expires_at,
        display_order=source.display_order,
        version_family=source.version_family,
        version_number=next_number,
        created_by=actor,
        updated_by=actor,
    )
    draft.full_clean(exclude=["owner_office", "slug"])
    draft.save()

    replace_audience(actor, draft, _stored_selectors(source))
    clone_files_to(actor, source, draft)

    _log(
        "marketing.version_created",
        actor=actor,
        asset=draft,
        before={"source_id": source.pk, "source_version": source.version_number},
        after=snapshot(draft),
    )
    return draft


#: Alias kept for callers that say "supersede" explicitly.
supersede = duplicate_version


def _emit_lifecycle(name: str, *, actor: User, asset: MarketingAsset, now) -> None:
    publish_event(
        name,
        actor_id=str(actor.pk),
        subject=str(asset.pk),
        payload={
            "asset_id": asset.pk,
            "owner_office_id": asset.owner_office.pk,
            "scope_level": asset.scope_level,
            "status": asset.status,
            "version_number": asset.version_number,
            "version_family": str(asset.version_family),
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
    asset: MarketingAsset,
    *,
    actor: User,
    office: Office | None,
    role_code: str,
) -> dict[str, Any]:
    selectors = selectors_for(asset)
    context = preview_context(office=office, role_code=role_code)
    chosen = bool(office or role_code)
    matched = chosen and selectors.filter(selector_q(context)).exists()
    has_named_recipients = selectors.filter(kind="user").exists()
    article = consumer_detail_payload(asset)
    return {
        "article": {
            **article,
            "audience": describe_audience(asset),
            "exports": export_files_payload(asset),
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


def publication_history(asset: MarketingAsset) -> list[dict[str, str]]:
    rows = AuditEvent.objects.filter(
        action__in=tuple(HISTORY_ACTIONS),
        target_type=MarketingAsset._meta.label_lower,
        target_id=str(asset.pk),
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


@dataclass(frozen=True)
class WorkspaceFilters:
    q: str = ""
    lifecycle: str = ""
    category: str = ""
    asset_type: str = ""
    audience: str = ""
    author: str = ""
    office: str = ""
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
            asset_type=pick("type", set(ASSET_TYPE_CODES)),
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
            "type": self.asset_type,
            "audience": self.audience,
            "author": self.author,
            "office": self.office,
            "publishedFrom": self.published_from,
            "publishedTo": self.published_to,
        }


def apply_workspace_filters(
    queryset: QuerySet[MarketingAsset], filters: WorkspaceFilters, *, now=None
) -> QuerySet[MarketingAsset]:
    from django.utils.dateparse import parse_date

    moment = now or timezone.now()
    if filters.q:
        queryset = queryset.filter(
            Q(title__icontains=filters.q)
            | Q(description__icontains=filters.q)
            | Q(slug__icontains=filters.q)
        )
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.asset_type:
        queryset = queryset.filter(asset_type=filters.asset_type)
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
        return queryset.filter(status=MarketingAsset.Status.DRAFT)
    if lifecycle == "archived":
        return queryset.filter(status=MarketingAsset.Status.ARCHIVED)
    published = queryset.filter(status=MarketingAsset.Status.PUBLISHED)
    if lifecycle == "scheduled":
        return published.filter(publish_at__gt=moment)
    if lifecycle == "expired":
        return published.filter(expires_at__lte=moment)
    return published.filter(
        Q(publish_at__isnull=True) | Q(publish_at__lte=moment),
        Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
    )


def order_for_workspace(
    queryset: QuerySet[MarketingAsset],
) -> QuerySet[MarketingAsset]:
    return queryset.order_by("-updated_at", "-pk")


def category_options(*, include_codes=()) -> list[dict[str, str]]:
    extra = {code for code in include_codes if code}
    rows = MarketingCategory.objects.filter(Q(is_active=True) | Q(code__in=extra))
    return [{"value": row.code, "label": row.label} for row in rows]


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def admin_row(asset: MarketingAsset, *, now=None) -> dict[str, Any]:
    return {
        "id": asset.pk,
        "slug": asset.slug,
        "title": asset.title,
        "description": asset.description,
        "lifecycle": lifecycle_state(asset, now=now),
        "status": asset.status,
        "assetType": present_asset_type(asset.asset_type),
        "category": present_category(asset.category),
        "versionNumber": asset.version_number,
        "versionLabel": f"v{asset.version_number}",
        "ownerOffice": {
            "id": asset.owner_office.pk,
            "name": asset.owner_office.name,
        },
        "scopeLevel": asset.scope_level,
        "audience": describe_audience(asset),
        "jurisdictionStateCodes": list(asset.jurisdiction_state_codes or []),
        "brandCodes": list(asset.brand_codes or []),
        "publishAt": _iso(asset.publish_at),
        "expiresAt": _iso(asset.expires_at),
        "publishedAt": _iso(asset.published_at),
        "updatedAt": _iso(asset.updated_at),
        "updatedBy": _actor_label(asset.updated_by),
        "createdBy": _actor_label(asset.created_by),
        "version": asset_version(asset),
    }


def detail_payload(
    asset: MarketingAsset, *, actor: User | None = None, now=None
) -> dict[str, Any]:
    return {
        **admin_row(asset, now=now),
        "usageInstructions": asset.usage_instructions,
        "categoryCode": asset.category.code if asset.category else "",
        "assetTypeCode": asset.asset_type,
        "displayOrder": asset.display_order,
        "validation": validation_debt_payload(asset),
        "history": publication_history(asset),
        "files": admin_files_payload(asset, actor=actor),
        "mediaHref": f"/operations/marketing-resources/{asset.pk}/media",
        "versionFamily": str(asset.version_family),
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
