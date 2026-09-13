"""Compliance library reads: visibility, filters, versioning, and serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from django.db import connection
from django.db.models import Q, QuerySet
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.compliance.audience import selectors_for, visible_policies, visible_to
from apps.compliance.media_service import document_files_payload, media_publish_debt
from apps.compliance.models import PolicyCategory, PolicyVersion
from apps.compliance.presentation import present_category, present_status
from apps.user.models import User
from apps.web.contracts import list_response

PAGE_SIZE = 12
MAX_PAGE_SIZE = 50

_SCOPE_LABELS = {
    "company": "Brokerage-wide",
    "region": "Region",
    "office": "Office",
}

ResolveResult = tuple[Literal["ok", "redirect"], PolicyVersion]


@dataclass(frozen=True)
class LibraryFilters:
    category: str = ""
    jurisdiction: str = ""
    query: str = ""
    rejected: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_params(cls, params, *, known_category_codes) -> LibraryFilters:
        rejected: list[str] = []

        raw_category = (params.get("category") or "").strip()[:40]
        category = raw_category if raw_category in known_category_codes else ""
        if raw_category and not category:
            rejected.append("category")

        jurisdiction = (params.get("jurisdiction") or "").strip().upper()[:2]
        if jurisdiction and len(jurisdiction) != 2:
            rejected.append("jurisdiction")
            jurisdiction = ""

        query = (params.get("q") or "").strip()[:120]

        return cls(
            category=category,
            jurisdiction=jurisdiction,
            query=query,
            rejected=tuple(rejected),
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "jurisdiction": self.jurisdiction,
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
    """Match empty (all jurisdictions) OR any of the given state codes."""
    clause = Q(jurisdiction_state_codes=[])
    for code in codes:
        if connection.vendor == "postgresql":
            clause |= Q(jurisdiction_state_codes__contains=[code])
        else:
            clause |= Q(jurisdiction_state_codes__icontains=f'"{code}"')
    return clause


def apply_jurisdiction_visibility(
    queryset: QuerySet[PolicyVersion], user: User
) -> QuerySet[PolicyVersion]:
    """Empty jurisdiction list means all; else match license or office state."""
    codes = actor_jurisdiction_codes(user)
    if not codes:
        # No state on the actor: only policies that apply everywhere.
        return queryset.filter(jurisdiction_state_codes=[])
    return queryset.filter(_jurisdiction_clause(codes))


def apply_library_filters(
    queryset: QuerySet[PolicyVersion], filters: LibraryFilters
) -> QuerySet[PolicyVersion]:
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.jurisdiction:
        queryset = queryset.filter(_jurisdiction_clause([filters.jurisdiction]))
    if filters.query:
        queryset = queryset.filter(
            Q(title__icontains=filters.query)
            | Q(summary__icontains=filters.query)
            | Q(body__icontains=filters.query)
        )
    return queryset


def _one_live_per_family(
    queryset: QuerySet[PolicyVersion],
) -> QuerySet[PolicyVersion]:
    from django.db.models import OuterRef, Subquery

    visible_pks = queryset.values("pk")
    newest_pk = (
        PolicyVersion.objects.filter(
            pk__in=visible_pks,
            version_family=OuterRef("version_family"),
        )
        .order_by("-version_number", "-pk")
        .values("pk")[:1]
    )
    return (
        PolicyVersion.objects.filter(pk__in=visible_pks)
        .filter(pk=Subquery(newest_pk))
        .select_related("category", "owner_office", "owner_user")
    )


def library_queryset(
    user: User, filters: LibraryFilters | None = None, *, at=None
) -> QuerySet[PolicyVersion]:
    applied = filters or LibraryFilters()
    base = apply_library_filters(visible_policies(user, at=at), applied)
    base = apply_jurisdiction_visibility(base, user)
    collapsed = _one_live_per_family(base)
    return collapsed.order_by("display_order", "title", "pk")


def current_live_sibling(version: PolicyVersion, *, at=None) -> PolicyVersion | None:
    from django.utils import timezone

    moment = at or timezone.now()
    return (
        PolicyVersion.objects.filter(version_family=version.version_family)
        .published()
        .within_window(now=moment)
        .select_related("category", "owner_office", "owner_user")
        .order_by("-version_number", "-pk")
        .first()
    )


def resolve_consumer_policy(user: User, policy_id: int, *, at=None) -> ResolveResult:
    version = (
        PolicyVersion.objects.select_related("category", "owner_office", "owner_user")
        .filter(pk=policy_id)
        .first()
    )
    if version is None:
        raise Http404("No policy matches that id.")

    if visible_to(user, version, at=at) and _matches_jurisdiction(user, version):
        live = current_live_sibling(version, at=at)
        if live is not None and live.pk != version.pk and visible_to(user, live, at=at):
            return ("redirect", live)
        return ("ok", version)

    if version.status in {
        PolicyVersion.Status.SUPERSEDED,
        PolicyVersion.Status.RETIRED,
    }:
        live = current_live_sibling(version, at=at)
        if (
            live is not None
            and visible_to(user, live, at=at)
            and _matches_jurisdiction(user, live)
        ):
            return ("redirect", live)

    raise Http404("No policy matches that id.")


def _matches_jurisdiction(user: User, version: PolicyVersion) -> bool:
    codes = list(version.jurisdiction_state_codes or [])
    if not codes:
        return True
    actor_codes = actor_jurisdiction_codes(user)
    return bool(actor_codes.intersection(codes))


def validation_debt(version: PolicyVersion) -> list[tuple[str, Any]]:
    debt: list[tuple[str, Any]] = []
    if version.category is None:
        debt.append(("category", _("Choose a category before publishing.")))
    if not (version.title or "").strip():
        debt.append(("title", _("Add a title before publishing.")))
    if version.pk is not None and not selectors_for(version).exists():
        debt.append(("audience", _("Choose who this policy is for.")))
    if version.pk is not None:
        debt.extend(media_publish_debt(version))
    return debt


def validation_debt_payload(version: PolicyVersion) -> dict[str, Any]:
    debt = validation_debt(version)
    return {
        "isPublishable": not debt,
        "items": [
            {"field": field_name, "message": str(msg)} for field_name, msg in debt
        ],
    }


def _scope_payload(version: PolicyVersion) -> dict[str, str]:
    level = version.scope_level
    return {
        "level": level,
        "label": _SCOPE_LABELS[level],
        "officeName": version.owner_office.name,
    }


def library_payload(
    version: PolicyVersion, *, actor: User | None = None
) -> dict[str, Any]:
    from apps.compliance.acknowledgements import user_ack_status

    ack = (
        user_ack_status(actor, version)
        if actor is not None
        else {
            "acknowledged": False,
            "required": False,
            "dueAt": None,
            "canAcknowledge": False,
            "waived": False,
        }
    )
    return {
        "id": version.pk,
        "title": version.title,
        "summary": version.summary,
        "status": present_status(version.status),
        "category": present_category(version.category),
        "scope": _scope_payload(version),
        "jurisdictionStateCodes": list(version.jurisdiction_state_codes or []),
        "versionNumber": version.version_number,
        "versionLabel": f"v{version.version_number}",
        "isMandatory": version.is_mandatory,
        "publishedAt": (
            version.published_at.isoformat() if version.published_at else None
        ),
        "detailUrl": reverse("policy_detail", args=[version.pk]),
        "acknowledged": ack["acknowledged"],
        "required": ack["required"],
        "dueAt": ack["dueAt"],
        "canAcknowledge": ack["canAcknowledge"],
        "mustOpenDocument": ack.get("mustOpenDocument", False),
        "documentAccessed": ack.get("documentAccessed", False),
    }


def detail_payload(version: PolicyVersion, *, actor: User) -> dict[str, Any]:
    from apps.compliance.acknowledgements import user_ack_status

    ack = user_ack_status(actor, version)
    documents = document_files_payload(version)
    return {
        **library_payload(version, actor=actor),
        "body": version.body,
        "documents": documents,
        "contentChecksum": version.content_checksum,
        "acknowledgementDisclosure": version.acknowledgement_disclosure,
        "disclosureVersion": version.disclosure_version,
        "effectiveAt": (
            version.effective_at.isoformat() if version.effective_at else None
        ),
        "expiresAt": version.expires_at.isoformat() if version.expires_at else None,
        "acknowledged": ack["acknowledged"],
        "required": ack["required"],
        "dueAt": ack["dueAt"],
        "canAcknowledge": ack["canAcknowledge"],
        "waived": ack["waived"],
        "acknowledgedAt": ack.get("acknowledgedAt"),
        "mustOpenDocument": ack.get("mustOpenDocument", False),
        "documentAccessed": ack.get("documentAccessed", False),
    }


def build_library(
    user: User,
    *,
    params,
    page: int,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    known_codes = frozenset(
        PolicyCategory.objects.active().values_list("code", flat=True)
    )
    filters = LibraryFilters.from_params(params, known_category_codes=known_codes)
    queryset = library_queryset(user, filters)
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    total = queryset.count()
    total_pages = max(1, (total + size - 1) // size)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * size
    page_items = list(queryset[start : start + size])

    rows = [library_payload(item, actor=user) for item in page_items]
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
    rows = PolicyCategory.objects.filter(
        Q(is_active=True) | Q(code__in=codes)
    ).order_by("display_order", "label")
    return [{"value": row.code, "label": row.label} for row in rows]
