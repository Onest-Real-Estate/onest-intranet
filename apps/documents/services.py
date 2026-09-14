"""Documents library reads: visibility, filters, versioning, and serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q, QuerySet
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.events import publish as publish_event
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.documents.audience import (
    selectors_for,
    visible_documents,
    visible_to,
)
from apps.documents.media_service import document_files_payload, media_publish_debt
from apps.documents.models import DocumentCategory, DocumentFamily, DocumentVersion
from apps.documents.presentation import present_category, present_status
from apps.user.models import Office, User
from apps.user.roles import ROLE_BY_KEY, ROLE_DEFINITIONS
from apps.user.services.role_assignments import has_effective_permission
from apps.web.contracts import list_response

PAGE_SIZE = 12
MAX_PAGE_SIZE = 50

_SCOPE_LABELS = {
    "company": "Brokerage-wide",
    "region": "Region",
    "office": "Office",
}

ResolveResult = tuple[Literal["ok", "redirect"], DocumentVersion]


@dataclass(frozen=True)
class LibraryFilters:
    category: str = ""
    jurisdiction: str = ""
    office: str = ""
    role: str = ""
    query: str = ""
    rejected: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_params(
        cls,
        params,
        *,
        known_category_codes,
        visible_office_ids: frozenset[int] | None = None,
    ) -> LibraryFilters:
        rejected: list[str] = []

        raw_category = (params.get("category") or "").strip()[:40]
        category = raw_category if raw_category in known_category_codes else ""
        if raw_category and not category:
            rejected.append("category")

        jurisdiction = (params.get("jurisdiction") or "").strip().upper()[:2]
        if jurisdiction and len(jurisdiction) != 2:
            rejected.append("jurisdiction")
            jurisdiction = ""

        raw_office = (params.get("office") or "").strip()[:12]
        office = ""
        if raw_office:
            try:
                office_id = int(raw_office)
            except ValueError:
                rejected.append("office")
            else:
                if visible_office_ids is None or office_id in visible_office_ids:
                    office = str(office_id)
                else:
                    rejected.append("office")

        raw_role = (params.get("role") or "").strip()[:64]
        role = raw_role if raw_role in ROLE_BY_KEY else ""
        if raw_role and not role:
            rejected.append("role")

        query = (params.get("q") or "").strip()[:120]

        return cls(
            category=category,
            jurisdiction=jurisdiction,
            office=office,
            role=role,
            query=query,
            rejected=tuple(rejected),
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "jurisdiction": self.jurisdiction,
            "office": self.office,
            "role": self.role,
            "q": self.query,
            "rejected": list(self.rejected),
        }


def actor_jurisdiction_codes(user: User) -> frozenset[str]:
    codes: set[str] = set()
    license_state = (getattr(user, "license_state", "") or "").strip().upper()
    if license_state:
        codes.add(license_state)
    office = getattr(user, "office", None)
    office_state = (
        (getattr(office, "state", "") or "").strip().upper() if office else ""
    )
    if office_state:
        codes.add(office_state)
    return frozenset(codes)


def _jurisdiction_clause(codes: frozenset[str] | set[str] | list[str]) -> Q:
    clause = Q(jurisdiction_state_codes=[])
    for code in codes:
        if connection.vendor == "postgresql":
            clause |= Q(jurisdiction_state_codes__contains=[code])
        else:
            clause |= Q(jurisdiction_state_codes__icontains=f'"{code}"')
    return clause


def apply_jurisdiction_visibility(
    queryset: QuerySet[DocumentVersion], user: User
) -> QuerySet[DocumentVersion]:
    codes = actor_jurisdiction_codes(user)
    if not codes:
        return queryset.filter(jurisdiction_state_codes=[])
    return queryset.filter(_jurisdiction_clause(codes))


def apply_library_filters(
    queryset: QuerySet[DocumentVersion], filters: LibraryFilters
) -> QuerySet[DocumentVersion]:
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.jurisdiction:
        queryset = queryset.filter(_jurisdiction_clause([filters.jurisdiction]))
    if filters.office:
        queryset = queryset.filter(family__owner_office_id=int(filters.office))
    if filters.role:
        queryset = queryset.filter(
            audiences__kind="role",
            audiences__role=filters.role,
        )
    if filters.query:
        queryset = queryset.filter(
            Q(name__icontains=filters.query)
            | Q(description__icontains=filters.query)
            | Q(family__key__icontains=filters.query)
        )
    return queryset


def _one_live_per_family(
    queryset: QuerySet[DocumentVersion],
) -> QuerySet[DocumentVersion]:
    from django.db.models import OuterRef, Subquery

    visible_pks = queryset.values("pk")
    newest_pk = (
        DocumentVersion.objects.filter(
            pk__in=visible_pks,
            family_id=OuterRef("family_id"),
        )
        .order_by("-version_number", "-pk")
        .values("pk")[:1]
    )
    return (
        DocumentVersion.objects.filter(pk__in=visible_pks)
        .filter(pk=Subquery(newest_pk))
        .select_related("category", "family", "family__owner_office", "owner_user")
    )


def visible_office_ids(user: User, *, at=None) -> frozenset[int]:
    base = apply_jurisdiction_visibility(visible_documents(user, at=at), user)
    collapsed = _one_live_per_family(base)
    return frozenset(
        collapsed.values_list("family__owner_office_id", flat=True).distinct()
    )


def library_queryset(
    user: User, filters: LibraryFilters | None = None, *, at=None
) -> QuerySet[DocumentVersion]:
    applied = filters or LibraryFilters()
    base = apply_library_filters(visible_documents(user, at=at), applied)
    base = apply_jurisdiction_visibility(base, user)
    collapsed = _one_live_per_family(base)
    return collapsed.order_by("display_order", "name", "pk")


def current_live_sibling(
    version: DocumentVersion, *, at=None
) -> DocumentVersion | None:
    moment = at or timezone.now()
    return (
        DocumentVersion.objects.filter(family=version.family)
        .published()
        .within_window(now=moment)
        .select_related("category", "family", "family__owner_office", "owner_user")
        .order_by("-version_number", "-pk")
        .first()
    )


def _matches_jurisdiction(user: User, version: DocumentVersion) -> bool:
    codes = list(version.jurisdiction_state_codes or [])
    if not codes:
        return True
    actor_codes = actor_jurisdiction_codes(user)
    return bool(actor_codes.intersection(codes))


def is_current_for(user: User, version: DocumentVersion, *, at=None) -> bool:
    if not visible_to(user, version, at=at) or not _matches_jurisdiction(user, version):
        return False
    live = current_live_sibling(version, at=at)
    return live is not None and live.pk == version.pk


def resolve_consumer_document(
    user: User, document_id: int, *, at=None
) -> ResolveResult:
    version = (
        DocumentVersion.objects.select_related(
            "category", "family", "family__owner_office", "owner_user"
        )
        .filter(pk=document_id)
        .first()
    )
    if version is None:
        raise Http404("No document matches that id.")

    if visible_to(user, version, at=at) and _matches_jurisdiction(user, version):
        live = current_live_sibling(version, at=at)
        if live is not None and live.pk != version.pk and visible_to(user, live, at=at):
            return ("redirect", live)
        return ("ok", version)

    if version.status in {
        DocumentVersion.Status.SUPERSEDED,
        DocumentVersion.Status.RETIRED,
    }:
        live = current_live_sibling(version, at=at)
        if (
            live is not None
            and visible_to(user, live, at=at)
            and _matches_jurisdiction(user, live)
        ):
            return ("redirect", live)

    raise Http404("No document matches that id.")


def validation_debt(version: DocumentVersion) -> list[tuple[str, Any]]:
    debt: list[tuple[str, Any]] = []
    if version.category is None:
        debt.append(("category", _("Choose a category before publishing.")))
    if not (version.name or "").strip():
        debt.append(("name", _("Add a name before publishing.")))
    if version.pk is not None and not selectors_for(version).exists():
        debt.append(("audience", _("Choose who this document is for.")))
    if version.pk is not None:
        debt.extend(media_publish_debt(version))
    return debt


def validation_debt_payload(version: DocumentVersion) -> dict[str, Any]:
    debt = validation_debt(version)
    return {
        "isPublishable": not debt,
        "items": [
            {"field": field_name, "message": str(msg)} for field_name, msg in debt
        ],
    }


def _scope_payload(version: DocumentVersion) -> dict[str, str]:
    level = version.scope_level
    return {
        "level": level,
        "label": _SCOPE_LABELS[level],
        "officeName": version.owner_office.name,
        "officeId": str(version.owner_office.pk),
    }


def library_payload(version: DocumentVersion) -> dict[str, Any]:
    files = document_files_payload(version)
    return {
        "id": version.pk,
        "key": version.family.key,
        "name": version.name,
        "description": version.description,
        "status": present_status(version.status),
        "category": present_category(version.category),
        "scope": _scope_payload(version),
        "jurisdictionStateCodes": list(version.jurisdiction_state_codes or []),
        "versionNumber": version.version_number,
        "versionLabel": f"v{version.version_number}",
        "effectiveAt": (
            version.effective_at.isoformat() if version.effective_at else None
        ),
        "expiresAt": version.expires_at.isoformat() if version.expires_at else None,
        "publishedAt": (
            version.published_at.isoformat() if version.published_at else None
        ),
        "fileCount": len(files),
        "detailUrl": reverse("document_detail", args=[version.pk]),
    }


def detail_payload(
    version: DocumentVersion, *, superseded: bool = False
) -> dict[str, Any]:
    return {
        **library_payload(version),
        "files": document_files_payload(version),
        "superseded": superseded,
    }


def build_library(
    user: User,
    *,
    params,
    page: int,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    known_codes = frozenset(
        DocumentCategory.objects.active().values_list("code", flat=True)
    )
    offices = visible_office_ids(user)
    filters = LibraryFilters.from_params(
        params,
        known_category_codes=known_codes,
        visible_office_ids=offices,
    )
    queryset = library_queryset(user, filters)
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    total = queryset.count()
    total_pages = max(1, (total + size - 1) // size)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * size
    page_items = list(queryset.prefetch_related("files")[start : start + size])

    rows = [library_payload(item) for item in page_items]
    payload = list_response(
        rows,
        page=current,
        page_size=size,
        total_items=total,
        filters=filters.as_payload(),
    )
    payload["filters"] = filters.as_payload()
    return payload


def category_filter_options(*, include_codes=()) -> list[dict[str, str]]:
    codes = set(include_codes)
    rows = DocumentCategory.objects.filter(
        Q(is_active=True) | Q(code__in=codes)
    ).order_by("display_order", "label")
    return [{"value": row.code, "label": row.label} for row in rows]


def office_filter_options(user: User) -> list[dict[str, str]]:
    ids = visible_office_ids(user)
    if not ids:
        return []
    rows = Office.objects.filter(pk__in=ids).order_by("name")
    return [{"value": str(row.pk), "label": row.name} for row in rows]


def role_filter_options() -> list[dict[str, str]]:
    return [
        {"value": definition.code, "label": definition.label}
        for definition in ROLE_DEFINITIONS
    ]


def _version_snapshot(version: DocumentVersion) -> dict[str, Any]:
    return {
        "name": version.name,
        "status": version.status,
        "version_number": version.version_number,
        "family_key": version.family.key,
    }


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


def _log_lifecycle(
    name: str, *, actor: User, version: DocumentVersion, before, after
) -> None:
    log_event(
        name,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=DocumentVersion._meta.label_lower,
            target_id=str(version.pk),
            target_label=version.name,
        ),
        before=before,
        after=after,
    )


@transaction.atomic
def publish_version(actor: User, version: DocumentVersion) -> DocumentVersion:
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, "web.publish_documents")
    ):
        raise PermissionDenied("You cannot publish documents.")

    DocumentFamily.objects.select_for_update(of=("self",)).get(pk=version.family.pk)
    locked = DocumentVersion.objects.select_for_update(of=("self",)).get(pk=version.pk)

    debt = validation_debt(locked)
    if debt:
        raise ValidationError(dict(debt))

    now = timezone.now()
    siblings = (
        DocumentVersion.objects.select_for_update(of=("self",))
        .filter(family=locked.family, status=DocumentVersion.Status.PUBLISHED)
        .exclude(pk=locked.pk)
        .order_by("pk")
    )
    for sibling in siblings:
        before = _version_snapshot(sibling)
        sibling.status = DocumentVersion.Status.SUPERSEDED
        sibling.updated_by = actor
        sibling.save(update_fields=["status", "updated_by", "updated_at"])
        _log_lifecycle(
            "document.superseded",
            actor=actor,
            version=sibling,
            before=before,
            after=_version_snapshot(sibling),
        )
        _emit_lifecycle("document.superseded", actor=actor, version=sibling, now=now)

    before = _version_snapshot(locked)
    locked.status = DocumentVersion.Status.PUBLISHED
    locked.published_at = now
    locked.published_by = actor
    locked.updated_by = actor
    if locked.effective_at is None:
        locked.effective_at = now
    locked.full_clean()
    locked.save()
    _log_lifecycle(
        "document.published",
        actor=actor,
        version=locked,
        before=before,
        after=_version_snapshot(locked),
    )
    _emit_lifecycle("document.published", actor=actor, version=locked, now=now)
    return locked
