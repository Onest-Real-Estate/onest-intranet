"""Compliance workspace: authority, lifecycle, versioning, and admin payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.compliance.audience import (
    AudienceSelector,
    describe_audience,
    replace_audience,
    selectors_for,
    targetable_office_ids,
    targetable_role_codes,
)
from apps.compliance.media_service import (
    admin_files_payload,
    clone_files_to,
    seal_content_checksum,
)
from apps.compliance.models import PolicyCategory, PolicyVersion
from apps.compliance.presentation import present_category, present_status
from apps.compliance.services import validation_debt, validation_debt_payload
from apps.user.models import Office, User
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)
from apps.web.authorization import scope_queryset_for_offices

MANAGE_PERMISSION = "web.manage_policies"
APPROVE_PERMISSION = "web.approve_policies"
PUBLISH_PERMISSION = "web.publish_policies"

DRAFT_EDITABLE_FIELDS: tuple[str, ...] = (
    "owner_user",
    "title",
    "summary",
    "body",
    "category",
    "effective_at",
    "expires_at",
    "jurisdiction_state_codes",
    "is_mandatory",
    "reacknowledge_on_supersede",
    "acknowledgement_disclosure",
    "disclosure_version",
    "display_order",
)

TRANSITIONS: tuple[str, ...] = (
    "submit",
    "approve",
    "publish",
    "retire",
    "return_to_draft",
)

PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
HISTORY_LIMIT = 25
AUDIENCE_KINDS = ("company", "role", "region", "office", "user")

HISTORY_ACTIONS: dict[str, tuple[str, str]] = {
    "compliance.created": ("Draft created", "neutral"),
    "compliance.updated": ("Draft edited", "neutral"),
    "compliance.audience_changed": ("Audience changed", "info"),
    "compliance.submitted": ("Submitted for review", "info"),
    "compliance.approved": ("Approved", "success"),
    "policy.submitted": ("Submitted for review", "info"),
    "policy.approved": ("Approved", "success"),
    "policy.published": ("Published", "success"),
    "policy.superseded": ("Superseded", "warning"),
    "policy.retired": ("Retired", "neutral"),
    "compliance.version_created": ("New version drafted", "info"),
}


class StalePolicyVersion(ValidationError):
    message: str

    def __init__(self):
        self.message = str(
            _(
                "Somebody else saved this policy while you were writing. "
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
    can_approve: bool
    can_publish: bool
    can_view_acks: bool
    can_waive: bool

    def payload(self) -> dict[str, bool]:
        return {
            "canAuthor": self.can_author,
            "canApprove": self.can_approve,
            "canPublish": self.can_publish,
            "canViewAcks": self.can_view_acks,
            "canWaive": self.can_waive,
        }


def capabilities(actor: User) -> Capabilities:
    return Capabilities(
        can_author=has_effective_permission(actor, MANAGE_PERMISSION),
        can_approve=has_effective_permission(actor, APPROVE_PERMISSION),
        can_publish=has_effective_permission(actor, PUBLISH_PERMISSION),
        can_view_acks=any(
            has_effective_permission(actor, code)
            for code in (
                MANAGE_PERMISSION,
                "web.view_compliance",
                "web.view_policy_acknowledgements",
            )
        ),
        can_waive=has_effective_permission(actor, "web.waive_policy_acknowledgements"),
    )


def _deny(actor: User, version: PolicyVersion | None, *, reason: str) -> None:
    log_event(
        "security.compliance.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=PolicyVersion._meta.label_lower,
            target_id=str(version.pk) if version and version.pk else "",
            target_label=version.title if version else "",
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


def publication_queryset(actor: User) -> QuerySet[PolicyVersion]:
    """Policies whose owner_office is inside the actor's effective access."""
    base = PolicyVersion.objects.select_related(
        "owner_office", "category", "created_by", "updated_by", "owner_user"
    )
    if not (
        has_effective_permission(actor, MANAGE_PERMISSION)
        or has_effective_permission(actor, "web.view_compliance")
        or has_effective_permission(actor, "web.view_policy_acknowledgements")
        or has_effective_permission(actor, "web.waive_policy_acknowledgements")
    ):
        return base.none()
    access = get_effective_access(actor)
    if getattr(actor, "is_superuser", False) or access.company_wide:
        return base
    office_ids = manageable_office_ids(actor)
    if not office_ids:
        return base.none()
    return base.filter(owner_office_id__in=office_ids)


def assert_can_author(actor: User, office: Office) -> None:
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _deny(actor, None, reason="missing_permission")
        raise PermissionDenied("You cannot manage policies.")
    if office.pk not in manageable_office_ids(actor):
        _deny(actor, None, reason="out_of_scope_office")
        raise PermissionDenied("That office is outside your compliance scope.")


def assert_can_approve(actor: User, version: PolicyVersion) -> None:
    assert_can_author(actor, version.owner_office)
    if not has_effective_permission(actor, APPROVE_PERMISSION):
        _deny(actor, version, reason="missing_approve_permission")
        raise PermissionDenied("You cannot approve policies.")


def assert_can_publish(actor: User, version: PolicyVersion) -> None:
    assert_can_author(actor, version.owner_office)
    if not has_effective_permission(actor, PUBLISH_PERMISSION):
        _deny(actor, version, reason="missing_publish_permission")
        raise PermissionDenied("You cannot publish or retire policies.")


def policy_version_token(version: PolicyVersion) -> str:
    return version.updated_at.isoformat() if version.updated_at else ""


def _assert_fresh(version: PolicyVersion, expected_version: str) -> None:
    if policy_version_token(version) != (expected_version or ""):
        raise StalePolicyVersion()


def snapshot(version: PolicyVersion) -> dict[str, Any]:
    return {
        "title": version.title,
        "summary": version.summary,
        "status": version.status,
        "category": version.category.code if version.category else None,
        "owner_office": version.owner_office.stable_key,
        "effective_at": version.effective_at,
        "expires_at": version.expires_at,
        "published_at": version.published_at,
        "content_checksum": version.content_checksum,
        "is_mandatory": version.is_mandatory,
        "jurisdiction_state_codes": list(version.jurisdiction_state_codes or []),
        "version_family": str(version.version_family),
        "version_number": version.version_number,
        "audience": describe_audience(version),
    }


def _actor_label(user: User | None) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.email


def _log(
    action: str,
    *,
    actor: User,
    version: PolicyVersion,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    log_event(
        action,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=PolicyVersion._meta.label_lower,
            target_id=str(version.pk),
            target_label=version.title,
        ),
        before=before or {},
        after=after or {},
    )


def _apply_fields(
    version: PolicyVersion, cleaned: dict[str, Any], *, fields: tuple[str, ...]
) -> None:
    for name in fields:
        if name in cleaned:
            setattr(version, name, cleaned[name])


def _lock(pk: int) -> PolicyVersion:
    return (
        PolicyVersion.objects.select_for_update(of=("self",))
        .select_related("owner_office", "category")
        .get(pk=pk)
    )


def create_draft(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
) -> PolicyVersion:
    assert_can_author(actor, office)
    return _create(actor=actor, office=office, cleaned=cleaned, selectors=selectors)


@transaction.atomic
def _create(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
) -> PolicyVersion:
    version = PolicyVersion(
        owner_office=office,
        status=PolicyVersion.Status.DRAFT,
        version_family=uuid4(),
        version_number=1,
        created_by=actor,
        updated_by=actor,
    )
    _apply_fields(version, cleaned, fields=DRAFT_EDITABLE_FIELDS)
    version.full_clean(exclude=["owner_office"])
    version.save()
    replace_audience(actor, version, selectors)
    _log(
        "compliance.created",
        actor=actor,
        version=version,
        before=None,
        after=snapshot(version),
    )
    return version


def update_draft(
    *,
    actor: User,
    version: PolicyVersion,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
) -> PolicyVersion:
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
    version: PolicyVersion,
    cleaned: dict[str, Any],
    selectors: list[AudienceSelector],
    expected_version: str,
) -> PolicyVersion:
    locked = _lock(version.pk)
    assert_can_author(actor, locked.owner_office)
    _assert_fresh(locked, expected_version)
    if locked.status in PolicyVersion.IMMUTABLE_STATUSES:
        raise TransitionRefused(
            str(_("Published policies cannot be edited. Duplicate as a new version."))
        )
    before = snapshot(locked)
    if "acknowledgement_disclosure" in cleaned:
        previous = locked.acknowledgement_disclosure
        incoming = cleaned.get("acknowledgement_disclosure") or ""
        if incoming != previous:
            current = locked.disclosure_version or 1
            requested = cleaned.get("disclosure_version") or current
            cleaned = {
                **cleaned,
                "disclosure_version": max(int(requested), current + 1),
            }
    _apply_fields(locked, cleaned, fields=DRAFT_EDITABLE_FIELDS)
    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office"])
    locked.save()
    replace_audience(actor, locked, selectors)
    after = snapshot(locked)
    _log(
        "compliance.updated",
        actor=actor,
        version=locked,
        before=before,
        after=after,
    )
    return locked


def transition(
    *,
    actor: User,
    version: PolicyVersion,
    action: str,
    expected_version: str,
    now=None,
    ack_due_at=None,
) -> PolicyVersion:
    if action not in TRANSITIONS:
        raise TransitionRefused(str(_("That is not a compliance action.")))
    return _transition(
        actor=actor,
        version=version,
        action=action,
        expected_version=expected_version,
        now=now,
        ack_due_at=ack_due_at,
    )


@transaction.atomic
def _transition(
    *,
    actor: User,
    version: PolicyVersion,
    action: str,
    expected_version: str,
    now=None,
    ack_due_at=None,
) -> PolicyVersion:
    moment = now or timezone.now()
    locked = _lock(version.pk)
    _assert_fresh(locked, expected_version)
    before = snapshot(locked)

    if action == "submit":
        assert_can_author(actor, locked.owner_office)
        if locked.status != PolicyVersion.Status.DRAFT:
            raise TransitionRefused(str(_("Only drafts can be submitted for review.")))
        locked.status = PolicyVersion.Status.IN_REVIEW
        event_name = "policy.submitted"
    elif action == "approve":
        assert_can_approve(actor, locked)
        if locked.status != PolicyVersion.Status.IN_REVIEW:
            raise TransitionRefused(str(_("Only policies in review can be approved.")))
        locked.status = PolicyVersion.Status.APPROVED
        event_name = "policy.approved"
    elif action == "publish":
        assert_can_publish(actor, locked)
        return _publish(
            actor=actor,
            locked=locked,
            before=before,
            now=moment,
            ack_due_at=ack_due_at,
        )
    elif action == "retire":
        assert_can_publish(actor, locked)
        if locked.status != PolicyVersion.Status.PUBLISHED:
            raise TransitionRefused(str(_("Only published policies can be retired.")))
        locked.status = PolicyVersion.Status.RETIRED
        event_name = "policy.retired"
    else:
        assert_can_author(actor, locked.owner_office)
        if locked.status not in {
            PolicyVersion.Status.IN_REVIEW,
            PolicyVersion.Status.APPROVED,
        }:
            raise TransitionRefused(
                str(_("Only in-review or approved policies can return to draft."))
            )
        locked.status = PolicyVersion.Status.DRAFT
        event_name = "compliance.updated"

    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office"])
    locked.save()
    _log(
        event_name if event_name.startswith("policy.") else "compliance.updated",
        actor=actor,
        version=locked,
        before=before,
        after=snapshot(locked),
    )
    if event_name.startswith("policy."):
        _emit_lifecycle(event_name, actor=actor, version=locked, now=moment)
    return locked


def _stored_selectors(version: PolicyVersion) -> list[AudienceSelector]:
    return [
        AudienceSelector(
            kind=row.kind,
            role=row.role,
            office=row.office,
            user=row.user,
        )
        for row in selectors_for(version)
    ]


def _publish(
    *,
    actor: User,
    locked: PolicyVersion,
    before: dict[str, Any],
    now,
    ack_due_at=None,
) -> PolicyVersion:
    from apps.compliance.acknowledgements import on_policy_published
    from apps.compliance.audience import assert_can_target

    if locked.status != PolicyVersion.Status.APPROVED:
        raise TransitionRefused(str(_("Only approved policies can be published.")))

    debt = validation_debt(locked)
    if debt:
        raise ValidationError(dict(debt))
    assert_can_target(actor, _stored_selectors(locked))

    _supersede_previous_live(actor=actor, locked=locked, now=now)

    locked.status = PolicyVersion.Status.PUBLISHED
    locked.content_checksum = seal_content_checksum(locked)
    locked.published_at = locked.published_at or now
    locked.published_by = actor
    locked.updated_by = actor
    locked.full_clean()
    locked.save()

    on_policy_published(locked, actor, now=now, due_at=ack_due_at)

    _log(
        "policy.published",
        actor=actor,
        version=locked,
        before=before,
        after=snapshot(locked),
    )
    _emit_lifecycle("policy.published", actor=actor, version=locked, now=now)
    return locked


def _supersede_previous_live(*, actor: User, locked: PolicyVersion, now) -> None:
    siblings = (
        PolicyVersion.objects.select_for_update(of=("self",))
        .filter(
            version_family=locked.version_family,
            status=PolicyVersion.Status.PUBLISHED,
        )
        .exclude(pk=locked.pk)
    )
    for sibling in siblings:
        before = snapshot(sibling)
        sibling.status = PolicyVersion.Status.SUPERSEDED
        sibling.updated_by = actor
        sibling.save(update_fields=["status", "updated_by", "updated_at"])
        _log(
            "policy.superseded",
            actor=actor,
            version=sibling,
            before=before,
            after=snapshot(sibling),
        )
        _emit_lifecycle("policy.superseded", actor=actor, version=sibling, now=now)


def duplicate_version(
    *, actor: User, version: PolicyVersion, expected_version: str
) -> PolicyVersion:
    assert_can_author(actor, version.owner_office)
    return _duplicate_version(
        actor=actor, version=version, expected_version=expected_version
    )


@transaction.atomic
def _duplicate_version(
    *, actor: User, version: PolicyVersion, expected_version: str
) -> PolicyVersion:
    source = _lock(version.pk)
    assert_can_author(actor, source.owner_office)
    _assert_fresh(source, expected_version)

    next_number = (
        PolicyVersion.objects.filter(version_family=source.version_family).aggregate(
            Max("version_number")
        )["version_number__max"]
        or source.version_number
    ) + 1

    draft = PolicyVersion(
        owner_office=source.owner_office,
        owner_user=source.owner_user,
        title=source.title,
        summary=source.summary,
        body=source.body,
        category=source.category,
        jurisdiction_state_codes=list(source.jurisdiction_state_codes or []),
        status=PolicyVersion.Status.DRAFT,
        effective_at=None,
        expires_at=source.expires_at,
        is_mandatory=source.is_mandatory,
        reacknowledge_on_supersede=source.reacknowledge_on_supersede,
        acknowledgement_disclosure=source.acknowledgement_disclosure,
        disclosure_version=source.disclosure_version,
        display_order=source.display_order,
        version_family=source.version_family,
        version_number=next_number,
        created_by=actor,
        updated_by=actor,
    )
    draft.full_clean(exclude=["owner_office"])
    draft.save()

    replace_audience(actor, draft, _stored_selectors(source))
    clone_files_to(actor, source, draft)

    _log(
        "compliance.version_created",
        actor=actor,
        version=draft,
        before={"source_id": source.pk, "source_version": source.version_number},
        after=snapshot(draft),
    )
    return draft


def _emit_lifecycle(name: str, *, actor: User, version: PolicyVersion, now) -> None:
    publish_event(
        name,
        actor_id=str(actor.pk),
        subject=str(version.pk),
        payload={
            "policy_id": version.pk,
            "owner_office_id": version.owner_office.pk,
            "scope_level": version.scope_level,
            "status": version.status,
            "version_number": version.version_number,
            "version_family": str(version.version_family),
            "is_mandatory": version.is_mandatory,
            "occurred_at": now.isoformat(),
        },
    )


@dataclass(frozen=True)
class WorkspaceFilters:
    q: str = ""
    status: str = ""
    category: str = ""
    office: str = ""

    @classmethod
    def from_params(cls, params, *, known_categories) -> WorkspaceFilters:
        def pick(name: str, allowed) -> str:
            value = (params.get(name) or "").strip()[:40]
            return value if value in allowed else ""

        return cls(
            q=(params.get("q") or "").strip()[:120],
            status=pick("status", {c.value for c in PolicyVersion.Status}),
            category=pick("category", set(known_categories)),
            office=(params.get("office") or "").strip()[:12],
        )

    def as_payload(self) -> dict[str, str]:
        return {
            "q": self.q,
            "status": self.status,
            "category": self.category,
            "office": self.office,
        }


def apply_workspace_filters(
    queryset: QuerySet[PolicyVersion], filters: WorkspaceFilters
) -> QuerySet[PolicyVersion]:
    if filters.q:
        queryset = queryset.filter(
            Q(title__icontains=filters.q) | Q(summary__icontains=filters.q)
        )
    if filters.status:
        queryset = queryset.filter(status=filters.status)
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.office.isdigit():
        queryset = queryset.filter(owner_office_id=int(filters.office))
    return queryset


def order_for_workspace(
    queryset: QuerySet[PolicyVersion],
) -> QuerySet[PolicyVersion]:
    return queryset.order_by("-updated_at", "-pk")


def category_options(*, include_codes=()) -> list[dict[str, str]]:
    extra = {code for code in include_codes if code}
    rows = PolicyCategory.objects.filter(Q(is_active=True) | Q(code__in=extra))
    return [{"value": row.code, "label": row.label} for row in rows]


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def admin_row(version: PolicyVersion) -> dict[str, Any]:
    return {
        "id": version.pk,
        "title": version.title,
        "summary": version.summary,
        "status": present_status(version.status),
        "statusCode": version.status,
        "category": present_category(version.category),
        "versionNumber": version.version_number,
        "versionLabel": f"v{version.version_number}",
        "ownerOffice": {
            "id": version.owner_office.pk,
            "name": version.owner_office.name,
        },
        "scopeLevel": version.scope_level,
        "audience": describe_audience(version),
        "jurisdictionStateCodes": list(version.jurisdiction_state_codes or []),
        "isMandatory": version.is_mandatory,
        "effectiveAt": _iso(version.effective_at),
        "expiresAt": _iso(version.expires_at),
        "publishedAt": _iso(version.published_at),
        "updatedAt": _iso(version.updated_at),
        "updatedBy": _actor_label(version.updated_by),
        "createdBy": _actor_label(version.created_by),
        "version": policy_version_token(version),
    }


def publication_history(version: PolicyVersion) -> list[dict[str, str]]:
    rows = AuditEvent.objects.filter(
        action__in=tuple(HISTORY_ACTIONS),
        target_type=PolicyVersion._meta.label_lower,
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


def detail_payload(
    version: PolicyVersion, *, actor: User | None = None
) -> dict[str, Any]:
    return {
        **admin_row(version),
        "body": version.body,
        "categoryCode": version.category.code if version.category else "",
        "displayOrder": version.display_order,
        "ownerUserId": version.owner_user.pk if version.owner_user else None,
        "acknowledgementDisclosure": version.acknowledgement_disclosure,
        "disclosureVersion": version.disclosure_version,
        "reacknowledgeOnSupersede": version.reacknowledge_on_supersede,
        "contentChecksum": version.content_checksum,
        "validation": validation_debt_payload(version),
        "history": publication_history(version),
        "files": admin_files_payload(version),
        "versionFamily": str(version.version_family),
        "capabilities": capabilities(actor).payload() if actor else None,
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


def build_admin_index(actor: User, *, params, page: int = 1) -> dict[str, Any]:
    from apps.web.contracts import list_response

    known_categories = list(PolicyCategory.objects.values_list("code", flat=True))
    filters = WorkspaceFilters.from_params(params, known_categories=known_categories)
    rows = order_for_workspace(
        apply_workspace_filters(publication_queryset(actor), filters)
    )
    total = rows.count()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * PAGE_SIZE
    items = [admin_row(row) for row in rows[start : start + PAGE_SIZE]]
    offices = [
        {"value": office.pk, "label": office.name}
        for office in publishable_office_queryset(actor)
    ]
    scoped = publication_queryset(actor)
    counts = scoped.aggregate(
        draft=Count("pk", filter=Q(status=PolicyVersion.Status.DRAFT)),
        in_review=Count("pk", filter=Q(status=PolicyVersion.Status.IN_REVIEW)),
        published=Count("pk", filter=Q(status=PolicyVersion.Status.PUBLISHED)),
    )
    return {
        "summary": {
            "draft": counts["draft"],
            "inReview": counts["in_review"],
            "published": counts["published"],
        },
        "policies": list_response(
            items,
            page=current,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters.as_payload(),
            sort_key="updatedAt",
            sort_direction="desc",
        ),
        "filterOptions": {
            "categories": category_options(include_codes=(filters.category,)),
            "statuses": [
                {"value": code, "label": label}
                for code, label in PolicyVersion.Status.choices
            ],
            "offices": offices,
        },
        "createOptions": {
            "offices": offices,
            "categories": category_options(),
            "audience": audience_choice_payload(actor),
        },
        "capabilities": capabilities(actor).payload(),
    }
