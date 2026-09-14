"""Documents workspace: authority, lifecycle, versioning, concurrency, history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max, Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.documents.audience import (
    AudienceSelector,
    describe_audience,
    replace_audience,
    selectors_for,
    targetable_office_ids,
    targetable_role_codes,
)
from apps.documents.media_service import admin_files_payload, clone_files_to
from apps.documents.models import (
    DocumentCategory,
    DocumentFamily,
    DocumentFile,
    DocumentVersion,
)
from apps.documents.presentation import present_category, present_status
from apps.documents.services import (
    current_live_sibling,
    validation_debt,
    validation_debt_payload,
)
from apps.user.models import Office, User
from apps.user.services.hierarchy import ancestors
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)
from apps.web.authorization import scope_queryset_for_offices

MANAGE_PERMISSION = "web.manage_documents"
PUBLISH_PERMISSION = "web.publish_documents"
RETIRE_PERMISSION = "web.retire_documents"

DRAFT_EDITABLE_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "category",
    "effective_at",
    "expires_at",
    "jurisdiction_state_codes",
    "display_order",
)

TRANSITIONS: tuple[str, ...] = ("publish", "schedule", "retire")

PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
HISTORY_LIMIT = 25
AUDIENCE_KINDS = ("company", "role", "region", "office", "user")

HISTORY_ACTIONS: dict[str, tuple[str, str]] = {
    "document.created": ("Draft created", "neutral"),
    "document.updated": ("Draft edited", "neutral"),
    "document.scheduled": ("Scheduled", "info"),
    "document.published": ("Published", "success"),
    "document.superseded": ("Superseded", "warning"),
    "document.retired": ("Retired", "neutral"),
    "document.version_created": ("New version drafted", "info"),
}


class StaleDocumentVersion(ValidationError):
    message: str

    def __init__(self):
        self.message = str(
            _(
                "Somebody else saved this document while you were writing. "
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
    can_retire: bool

    def payload(self) -> dict[str, bool]:
        return {
            "canAuthor": self.can_author,
            "canPublish": self.can_publish,
            "canRetire": self.can_retire,
        }


def capabilities(actor: User) -> Capabilities:
    return Capabilities(
        can_author=has_effective_permission(actor, MANAGE_PERMISSION),
        can_publish=has_effective_permission(actor, PUBLISH_PERMISSION),
        can_retire=has_effective_permission(actor, RETIRE_PERMISSION),
    )


def _deny(actor: User, version: DocumentVersion | None, *, reason: str) -> None:
    log_event(
        "security.documents.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=DocumentVersion._meta.label_lower,
            target_id=str(version.pk) if version and version.pk else "",
            target_label=version.name if version else "",
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def manageable_office_ids(actor: User) -> frozenset[int]:
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


def granted_jurisdiction_codes(actor: User) -> frozenset[str]:
    access = get_effective_access(actor)
    if getattr(actor, "is_superuser", False) or access.company_wide:
        return frozenset()
    codes = Office.objects.filter(pk__in=targetable_office_ids(actor)).exclude(state="")
    return frozenset(codes.values_list("state", flat=True))


def assert_jurisdiction_in_grant(actor: User, codes: list[str]) -> None:
    access = get_effective_access(actor)
    if getattr(actor, "is_superuser", False) or access.company_wide:
        return
    if not codes:
        _deny(actor, None, reason="jurisdiction_broader_than_grant")
        raise PermissionDenied("Scoped publishers must name the states they can cover.")
    allowed = granted_jurisdiction_codes(actor)
    extra = sorted({code.upper() for code in codes} - allowed)
    if extra:
        _deny(actor, None, reason="jurisdiction_outside_grant")
        raise PermissionDenied(
            "Those states are outside the jurisdictions you may cover."
        )


def manageable_queryset(actor: User) -> QuerySet[DocumentVersion]:
    from django.db.models import Prefetch

    from apps.documents.models import DocumentAudience

    base = DocumentVersion.objects.select_related(
        "family",
        "family__owner_office",
        "category",
        "created_by",
        "updated_by",
        "owner_user",
    ).prefetch_related(
        Prefetch(
            "audiences",
            queryset=DocumentAudience.objects.select_related("office", "user"),
        )
    )
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        return base.none()
    office_ids = manageable_office_ids(actor)
    if not office_ids:
        return base.none()
    return base.filter(family__owner_office_id__in=office_ids)


def assert_can_author(actor: User, office: Office) -> None:
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _deny(actor, None, reason="missing_permission")
        raise PermissionDenied("You cannot manage documents.")
    if office.pk not in manageable_office_ids(actor):
        _deny(actor, None, reason="out_of_scope_office")
        raise PermissionDenied("That office is outside your documents scope.")


def assert_can_publish(actor: User, version: DocumentVersion) -> None:
    assert_can_author(actor, version.owner_office)
    if not has_effective_permission(actor, PUBLISH_PERMISSION):
        _deny(actor, version, reason="missing_publish_permission")
        raise PermissionDenied("You cannot publish documents.")


def assert_can_retire(actor: User, version: DocumentVersion) -> None:
    assert_can_author(actor, version.owner_office)
    if not has_effective_permission(actor, RETIRE_PERMISSION):
        _deny(actor, version, reason="missing_retire_permission")
        raise PermissionDenied("You cannot retire documents.")


def document_version_token(version: DocumentVersion) -> str:
    return version.updated_at.isoformat() if version.updated_at else ""


def _assert_fresh(version: DocumentVersion, expected_version: str) -> None:
    if document_version_token(version) != (expected_version or ""):
        raise StaleDocumentVersion()


def snapshot(version: DocumentVersion) -> dict[str, Any]:
    return {
        "name": version.name,
        "status": version.status,
        "category": version.category.code if version.category else None,
        "owner_office": version.owner_office.stable_key,
        "effective_at": version.effective_at,
        "expires_at": version.expires_at,
        "published_at": version.published_at,
        "jurisdiction_state_codes": list(version.jurisdiction_state_codes or []),
        "family_key": version.family.key,
        "version_number": version.version_number,
        "audience": describe_audience(version),
    }


def lifecycle_state(version: DocumentVersion, *, now=None) -> dict[str, str]:
    moment = now or timezone.now()
    if version.status == DocumentVersion.Status.DRAFT:
        return {"code": "draft", "label": "Draft", "tone": "neutral"}
    if version.status == DocumentVersion.Status.SUPERSEDED:
        return {"code": "superseded", "label": "Superseded", "tone": "warning"}
    if version.status == DocumentVersion.Status.RETIRED:
        return {"code": "retired", "label": "Retired", "tone": "neutral"}
    if version.effective_at is not None and version.effective_at > moment:
        return {"code": "scheduled", "label": "Scheduled", "tone": "info"}
    if version.expires_at is not None and version.expires_at <= moment:
        return {"code": "expired", "label": "Expired", "tone": "warning"}
    return {"code": "live", "label": "Live", "tone": "success"}


def _actor_label(user: User | None) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.email


def build_family_key(name: str, *, exclude_pk: int | None = None) -> str:
    base = slugify(name)[:70] or "document"
    taken = set(
        DocumentFamily.objects.exclude(pk=exclude_pk).values_list("key", flat=True)
        if exclude_pk
        else DocumentFamily.objects.values_list("key", flat=True)
    )
    if base not in taken:
        return base
    for suffix in range(2, 100):
        candidate = f"{base[: 70 - len(str(suffix)) - 1]}-{suffix}"
        if candidate not in taken:
            return candidate
    raise ValidationError({"name": _("Too many document families share this title.")})


def _log(
    action: str,
    *,
    actor: User,
    version: DocumentVersion,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    log_event(
        action,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=DocumentVersion._meta.label_lower,
            target_id=str(version.pk),
            target_label=version.name,
        ),
        before=before or {},
        after=after or {},
    )


def _apply_fields(
    version: DocumentVersion, cleaned: dict[str, Any], *, fields: tuple[str, ...]
) -> None:
    for name in fields:
        if name in cleaned:
            setattr(version, name, cleaned[name])


def create_document(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    family_key: str = "",
) -> DocumentVersion:
    assert_can_author(actor, office)
    return _create(
        actor=actor,
        office=office,
        cleaned=cleaned,
        selectors=selectors,
        family_key=family_key,
    )


@transaction.atomic
def _create(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    family_key: str,
) -> DocumentVersion:
    from apps.documents.audience import assert_can_target

    assert_jurisdiction_in_grant(
        actor, list(cleaned.get("jurisdiction_state_codes") or [])
    )
    assert_can_target(actor, selectors)
    key = (family_key or "").strip() or build_family_key(cleaned.get("name", ""))
    family = DocumentFamily(key=key, owner_office=office)
    family.full_clean()
    family.save()
    version = DocumentVersion(
        family=family,
        status=DocumentVersion.Status.DRAFT,
        version_number=1,
        created_by=actor,
        updated_by=actor,
        owner_user=actor,
    )
    _apply_fields(version, cleaned, fields=DRAFT_EDITABLE_FIELDS)
    version.full_clean()
    version.save()
    replace_audience(actor, version, selectors)
    _log(
        "document.created",
        actor=actor,
        version=version,
        before=None,
        after=snapshot(version),
    )
    return version


def update_document(
    *,
    actor: User,
    version: DocumentVersion,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
) -> DocumentVersion:
    assert_can_author(actor, version.owner_office)
    return _update(
        actor=actor,
        version=version,
        cleaned=cleaned,
        selectors=selectors,
        expected_version=expected_version,
    )


@transaction.atomic
def _update(
    *,
    actor: User,
    version: DocumentVersion,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
) -> DocumentVersion:
    from apps.documents.audience import assert_can_target

    locked = _lock(version.pk)
    assert_can_author(actor, locked.owner_office)
    _assert_fresh(locked, expected_version)
    if locked.status != DocumentVersion.Status.DRAFT:
        raise TransitionRefused(
            str(
                _(
                    "Published documents cannot be edited. Duplicate as a new "
                    "version first."
                )
            )
        )
    assert_jurisdiction_in_grant(
        actor, list(cleaned.get("jurisdiction_state_codes") or [])
    )
    assert_can_target(actor, selectors)
    before = snapshot(locked)
    _apply_fields(locked, cleaned, fields=DRAFT_EDITABLE_FIELDS)
    locked.updated_by = actor
    locked.full_clean()
    locked.save()
    replace_audience(actor, locked, selectors)
    after = snapshot(locked)
    _log(
        "document.updated",
        actor=actor,
        version=locked,
        before=before,
        after=after,
    )
    return locked


def _lock(pk: int) -> DocumentVersion:
    return (
        DocumentVersion.objects.select_for_update(of=("self",))
        .select_related("family", "family__owner_office", "category")
        .get(pk=pk)
    )


def _lock_family(family_id: int) -> DocumentFamily:
    return DocumentFamily.objects.select_for_update(of=("self",)).get(pk=family_id)


def transition(
    *,
    actor: User,
    version: DocumentVersion,
    action: str,
    expected_version: str,
    now=None,
) -> DocumentVersion:
    if action not in TRANSITIONS:
        raise TransitionRefused(str(_("That is not a document action.")))
    if action == "retire":
        assert_can_retire(actor, version)
    else:
        assert_can_publish(actor, version)
    return _transition(
        actor=actor,
        version=version,
        action=action,
        expected_version=expected_version,
        now=now,
    )


@transaction.atomic
def _transition(
    *,
    actor: User,
    version: DocumentVersion,
    action: str,
    expected_version: str,
    now=None,
) -> DocumentVersion:
    moment = now or timezone.now()
    _lock_family(version.family.pk)
    locked = _lock(version.pk)
    _assert_fresh(locked, expected_version)
    if action == "retire":
        assert_can_retire(actor, locked)
        return _retire(actor=actor, locked=locked, now=moment)
    assert_can_publish(actor, locked)
    return _go_live(
        actor=actor, locked=locked, scheduled=action == "schedule", now=moment
    )


def _stored_selectors(version: DocumentVersion) -> list[AudienceSelector]:
    return [
        AudienceSelector(
            kind=row.kind,
            role=row.role,
            office=row.office,
            user=row.user,
        )
        for row in selectors_for(version)
    ]


def _go_live(
    *, actor: User, locked: DocumentVersion, scheduled: bool, now
) -> DocumentVersion:
    from apps.documents.audience import assert_can_target

    if locked.status != DocumentVersion.Status.DRAFT:
        raise TransitionRefused(str(_("Only a draft can be published.")))
    if scheduled and (locked.effective_at is None or locked.effective_at <= now):
        raise TransitionRefused(
            str(_("Set an effective time in the future before scheduling."))
        )
    if not scheduled and locked.effective_at is not None and locked.effective_at > now:
        raise TransitionRefused(
            str(
                _(
                    "This version is dated for the future. Schedule it, or "
                    "clear the effective time to publish it now."
                )
            )
        )

    before = snapshot(locked)
    debt = validation_debt(locked)
    if debt:
        raise ValidationError(dict(debt))
    assert_can_target(actor, _stored_selectors(locked))
    assert_jurisdiction_in_grant(actor, list(locked.jurisdiction_state_codes or []))

    if scheduled:
        _cap_sibling_windows(actor=actor, locked=locked, now=now)
    else:
        _supersede_published_siblings(actor=actor, locked=locked, now=now)

    locked.status = DocumentVersion.Status.PUBLISHED
    locked.published_at = now
    locked.published_by = actor
    locked.updated_by = actor
    if locked.effective_at is None:
        locked.effective_at = now
    locked.full_clean()
    locked.save()

    event_name = "document.scheduled" if scheduled else "document.published"
    _log(
        event_name,
        actor=actor,
        version=locked,
        before=before,
        after=snapshot(locked),
    )
    _emit_lifecycle(event_name, actor=actor, version=locked, now=now)
    return locked


def _supersede_published_siblings(*, actor: User, locked: DocumentVersion, now) -> None:
    siblings = (
        DocumentVersion.objects.select_for_update(of=("self",))
        .filter(family=locked.family, status=DocumentVersion.Status.PUBLISHED)
        .exclude(pk=locked.pk)
        .order_by("pk")
    )
    for sibling in siblings:
        before = snapshot(sibling)
        sibling.status = DocumentVersion.Status.SUPERSEDED
        sibling.updated_by = actor
        sibling.save(update_fields=["status", "updated_by", "updated_at"])
        _log(
            "document.superseded",
            actor=actor,
            version=sibling,
            before=before,
            after=snapshot(sibling),
        )
        _emit_lifecycle("document.superseded", actor=actor, version=sibling, now=now)


def _cap_sibling_windows(*, actor: User, locked: DocumentVersion, now) -> None:
    """Keep one current version once a scheduled replacement becomes effective."""
    del now
    start = locked.effective_at
    if start is None:
        raise TransitionRefused(
            str(_("Set an effective time in the future before scheduling."))
        )
    siblings = (
        DocumentVersion.objects.select_for_update(of=("self",))
        .filter(family=locked.family, status=DocumentVersion.Status.PUBLISHED)
        .exclude(pk=locked.pk)
        .order_by("pk")
    )
    for sibling in siblings:
        sibling_start = sibling.effective_at
        if sibling_start is not None and sibling_start >= start:
            raise TransitionRefused(
                str(
                    _(
                        "Another published version already covers that "
                        "effective window. Change the schedule, or retire it."
                    )
                )
            )
        expires_at = sibling.expires_at
        if expires_at is not None and expires_at <= start:
            continue
        before = snapshot(sibling)
        sibling.expires_at = start
        sibling.updated_by = actor
        sibling.full_clean()
        sibling.save(update_fields=["expires_at", "updated_by", "updated_at"])
        _log(
            "document.updated",
            actor=actor,
            version=sibling,
            before=before,
            after=snapshot(sibling),
        )


def _retire(*, actor: User, locked: DocumentVersion, now) -> DocumentVersion:
    if locked.status != DocumentVersion.Status.PUBLISHED:
        raise TransitionRefused(str(_("Only published documents can be retired.")))
    before = snapshot(locked)
    locked.status = DocumentVersion.Status.RETIRED
    locked.updated_by = actor
    locked.full_clean()
    locked.save()
    _log(
        "document.retired",
        actor=actor,
        version=locked,
        before=before,
        after=snapshot(locked),
    )
    _emit_lifecycle("document.retired", actor=actor, version=locked, now=now)
    return locked


def duplicate_version(
    *, actor: User, version: DocumentVersion, expected_version: str
) -> DocumentVersion:
    assert_can_author(actor, version.owner_office)
    return _duplicate_version(
        actor=actor, version=version, expected_version=expected_version
    )


@transaction.atomic
def _duplicate_version(
    *, actor: User, version: DocumentVersion, expected_version: str
) -> DocumentVersion:
    _lock_family(version.family.pk)
    source = _lock(version.pk)
    assert_can_author(actor, source.owner_office)
    _assert_fresh(source, expected_version)

    next_number = (
        DocumentVersion.objects.filter(family=source.family).aggregate(
            Max("version_number")
        )["version_number__max"]
        or source.version_number
    ) + 1

    draft = DocumentVersion(
        family=source.family,
        name=source.name,
        description=source.description,
        category=source.category,
        jurisdiction_state_codes=list(source.jurisdiction_state_codes or []),
        status=DocumentVersion.Status.DRAFT,
        effective_at=None,
        expires_at=source.expires_at,
        display_order=source.display_order,
        version_number=next_number,
        owner_user=actor,
        created_by=actor,
        updated_by=actor,
    )
    draft.full_clean()
    draft.save()
    replace_audience(actor, draft, _stored_selectors(source))
    clone_files_to(actor, source, draft)
    _log(
        "document.version_created",
        actor=actor,
        version=draft,
        before={"source_id": source.pk, "source_version": source.version_number},
        after=snapshot(draft),
    )
    return draft


def _emit_lifecycle(name: str, *, actor: User, version: DocumentVersion, now) -> None:
    publish_event(
        name,
        actor_id=str(actor.pk),
        subject=str(version.pk),
        payload={
            "document_id": version.pk,
            "family_id": version.family.pk,
            "family_key": version.family.key,
            "owner_office_id": version.owner_office.pk,
            "scope_level": version.scope_level,
            "status": version.status,
            "version_number": version.version_number,
            "occurred_at": now.isoformat(),
        },
    )


def retirement_usage(version: DocumentVersion, *, now=None) -> dict[str, Any]:
    moment = now or timezone.now()
    live = current_live_sibling(version, at=moment)
    files = DocumentFile.objects.filter(document_version=version, is_active=True)
    file_ids = [
        str(pk)
        for pk in DocumentFile.objects.filter(document_version=version).values_list(
            "pk", flat=True
        )
    ]
    downloads = (
        AuditEvent.objects.filter(
            action="document.downloaded",
            target_type=DocumentFile._meta.label_lower,
            target_id__in=file_ids,
        ).count()
        if file_ids
        else 0
    )
    siblings = DocumentVersion.objects.filter(family=version.family)
    return {
        "isCurrent": live is not None and live.pk == version.pk,
        "familyKey": version.family.key,
        "versionNumber": version.version_number,
        "siblingCount": siblings.count(),
        "publishedSiblingCount": siblings.filter(
            status=DocumentVersion.Status.PUBLISHED
        ).count(),
        "fileCount": files.count(),
        "downloadCount": downloads,
        "wouldLeaveFamilyWithoutCurrent": live is not None and live.pk == version.pk,
    }


def preview_payload(
    version: DocumentVersion,
    *,
    actor: User,
    office: Office | None,
    role_code: str,
) -> dict[str, Any]:
    from apps.documents.audience import AudienceContext, selector_q, selectors_for
    from apps.documents.services import detail_payload as consumer_detail_payload

    selectors = selectors_for(version)
    context = AudienceContext(
        user_id=None,
        office_id=office.pk if office else None,
        office_chain_ids=frozenset(node.pk for node in ancestors(office))
        if office
        else frozenset(),
        role_codes=frozenset({role_code}) if role_code else frozenset(),
        is_authenticated=True,
    )
    chosen = bool(office or role_code)
    matched = chosen and selectors.filter(selector_q(context)).exists()
    has_named_recipients = selectors.filter(kind="user").exists()
    article = consumer_detail_payload(version)
    return {
        "article": {
            **article,
            "audience": describe_audience(version),
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


def publication_history(version: DocumentVersion) -> list[dict[str, str]]:
    rows = AuditEvent.objects.filter(
        action__in=tuple(HISTORY_ACTIONS),
        target_type=DocumentVersion._meta.label_lower,
        target_id=str(version.pk),
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
                {
                    "draft",
                    "scheduled",
                    "live",
                    "expired",
                    "superseded",
                    "retired",
                },
            ),
            category=pick("category", set(known_categories)),
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
            "audience": self.audience,
            "author": self.author,
            "office": self.office,
            "publishedFrom": self.published_from,
            "publishedTo": self.published_to,
        }


def apply_workspace_filters(
    queryset: QuerySet[DocumentVersion], filters: WorkspaceFilters, *, now=None
) -> QuerySet[DocumentVersion]:
    from django.utils.dateparse import parse_date

    moment = now or timezone.now()
    if filters.q:
        queryset = queryset.filter(
            Q(name__icontains=filters.q)
            | Q(description__icontains=filters.q)
            | Q(family__key__icontains=filters.q)
        )
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.audience:
        queryset = queryset.filter(audiences__kind=filters.audience).distinct()
    if filters.author:
        queryset = queryset.filter(
            Q(created_by__email__icontains=filters.author)
            | Q(created_by__first_name__icontains=filters.author)
            | Q(created_by__last_name__icontains=filters.author)
        )
    if filters.office.isdigit():
        queryset = queryset.filter(family__owner_office_id=int(filters.office))
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
        return queryset.filter(status=DocumentVersion.Status.DRAFT)
    if lifecycle == "superseded":
        return queryset.filter(status=DocumentVersion.Status.SUPERSEDED)
    if lifecycle == "retired":
        return queryset.filter(status=DocumentVersion.Status.RETIRED)
    published = queryset.filter(status=DocumentVersion.Status.PUBLISHED)
    if lifecycle == "scheduled":
        return published.filter(effective_at__gt=moment)
    if lifecycle == "expired":
        return published.filter(expires_at__lte=moment)
    return published.filter(
        Q(effective_at__isnull=True) | Q(effective_at__lte=moment),
        Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
    )


def order_for_workspace(
    queryset: QuerySet[DocumentVersion],
) -> QuerySet[DocumentVersion]:
    return queryset.order_by("-updated_at", "-pk")


def category_options(*, include_codes=()) -> list[dict[str, str]]:
    extra = {code for code in include_codes if code}
    rows = DocumentCategory.objects.filter(Q(is_active=True) | Q(code__in=extra))
    return [{"value": row.code, "label": row.label} for row in rows]


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _scope_payload(version: DocumentVersion) -> dict[str, str]:
    level = version.scope_level
    labels = {
        "company": "Brokerage-wide",
        "region": "Region",
        "office": "Office",
    }
    return {
        "level": level,
        "label": labels[level],
        "officeName": version.owner_office.name,
        "officeId": str(version.owner_office.pk),
    }


def admin_row(version: DocumentVersion, *, now=None) -> dict[str, Any]:
    return {
        "id": version.pk,
        "key": version.family.key,
        "name": version.name,
        "description": version.description,
        "lifecycle": lifecycle_state(version, now=now),
        "status": present_status(version.status),
        "category": present_category(version.category),
        "versionNumber": version.version_number,
        "versionLabel": f"v{version.version_number}",
        "ownerOffice": {
            "id": version.owner_office.pk,
            "name": version.owner_office.name,
        },
        "scope": _scope_payload(version),
        "audience": describe_audience(version),
        "jurisdictionStateCodes": list(version.jurisdiction_state_codes or []),
        "effectiveAt": _iso(version.effective_at),
        "expiresAt": _iso(version.expires_at),
        "publishedAt": _iso(version.published_at),
        "updatedAt": _iso(version.updated_at),
        "updatedBy": _actor_label(version.updated_by),
        "createdBy": _actor_label(version.created_by),
        "version": document_version_token(version),
    }


def detail_payload(
    version: DocumentVersion, *, actor: User | None = None, now=None
) -> dict[str, Any]:
    return {
        **admin_row(version, now=now),
        "categoryCode": version.category.code if version.category else "",
        "displayOrder": version.display_order,
        "validation": validation_debt_payload(version),
        "history": publication_history(version),
        "files": admin_files_payload(version, actor=actor),
        "mediaHref": f"/operations/documents/{version.pk}/media",
        "usage": retirement_usage(version, now=now),
        "familyId": version.family.pk,
    }


def audience_choice_payload(actor: User) -> dict[str, Any]:
    from apps.user.roles import ROLE_BY_KEY

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
