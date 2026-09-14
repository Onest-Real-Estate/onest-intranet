"""Marketing library reads: visibility, filters, versioning, and serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from django.db.models import Count, Q, QuerySet
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.marketing.audience import visible_assets, visible_to
from apps.marketing.media_service import export_files_payload, media_publish_debt
from apps.marketing.models import MarketingAsset, MarketingCategory, MarketingFile
from apps.marketing.presentation import present_asset_type, present_category
from apps.marketing.taxonomy import (
    ASSET_TYPE_CHOICES,
    ASSET_TYPE_CODES,
    ASSET_TYPE_LOGO,
    ASSET_TYPE_TEMPLATE,
)
from apps.user.models import User
from apps.web.contracts import list_response

PAGE_SIZE = 12
MAX_PAGE_SIZE = 50

_SCOPE_LABELS = {
    "company": "Brokerage-wide",
    "region": "Region",
    "office": "Office",
}

ResolveResult = tuple[Literal["ok", "redirect"], MarketingAsset]


@dataclass(frozen=True)
class LibraryFilters:
    category: str = ""
    asset_type: str = ""
    jurisdiction: str = ""
    brand: str = ""
    query: str = ""
    rejected: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_params(cls, params, *, known_category_codes) -> LibraryFilters:
        rejected: list[str] = []

        raw_category = (params.get("category") or "").strip()[:40]
        category = raw_category if raw_category in known_category_codes else ""
        if raw_category and not category:
            rejected.append("category")

        raw_type = (params.get("type") or params.get("assetType") or "").strip()[:32]
        asset_type = raw_type if raw_type in ASSET_TYPE_CODES else ""
        if raw_type and not asset_type:
            rejected.append("type")

        jurisdiction = (params.get("jurisdiction") or "").strip().upper()[:2]
        if jurisdiction and len(jurisdiction) != 2:
            rejected.append("jurisdiction")
            jurisdiction = ""

        brand = (params.get("brand") or "").strip().lower()[:40]
        query = (params.get("q") or "").strip()[:120]

        return cls(
            category=category,
            asset_type=asset_type,
            jurisdiction=jurisdiction,
            brand=brand,
            query=query,
            rejected=tuple(rejected),
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "type": self.asset_type,
            "jurisdiction": self.jurisdiction,
            "brand": self.brand,
            "q": self.query,
            "rejected": list(self.rejected),
        }

    @property
    def active_count(self) -> int:
        return sum(
            1
            for value in (
                self.category,
                self.asset_type,
                self.jurisdiction,
                self.brand,
            )
            if value
        )


def apply_library_filters(
    queryset: QuerySet[MarketingAsset], filters: LibraryFilters
) -> QuerySet[MarketingAsset]:
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.asset_type:
        queryset = queryset.filter(asset_type=filters.asset_type)
    if filters.jurisdiction:
        # Empty jurisdiction list means all states.
        queryset = queryset.filter(
            Q(jurisdiction_state_codes=[])
            | Q(jurisdiction_state_codes__contains=[filters.jurisdiction])
        )
    if filters.brand:
        queryset = queryset.filter(
            Q(brand_codes=[]) | Q(brand_codes__contains=[filters.brand])
        )
    if filters.query:
        queryset = queryset.filter(
            Q(title__icontains=filters.query)
            | Q(description__icontains=filters.query)
            | Q(usage_instructions__icontains=filters.query)
        )
    return queryset


def _one_live_per_family(
    queryset: QuerySet[MarketingAsset],
) -> QuerySet[MarketingAsset]:
    """Keep the highest version_number per version_family.

    Uses a correlated subquery rather than ``DISTINCT ON`` so the result can
    be re-ordered for library display and ``.count()``'d on PostgreSQL without
    ``ORDER BY`` / ``DISTINCT ON`` conflicts. SQLite accepts the same shape.
    """
    from django.db.models import OuterRef, Subquery

    visible_pks = queryset.values("pk")
    newest_pk = (
        MarketingAsset.objects.filter(
            pk__in=visible_pks,
            version_family=OuterRef("version_family"),
        )
        .order_by("-version_number", "-pk")
        .values("pk")[:1]
    )
    return (
        MarketingAsset.objects.filter(pk__in=visible_pks)
        .filter(pk=Subquery(newest_pk))
        .select_related("category", "owner_office")
    )


def library_queryset(
    user: User, filters: LibraryFilters | None = None, *, at=None
) -> QuerySet[MarketingAsset]:
    applied = filters or LibraryFilters()
    base = apply_library_filters(visible_assets(user, at=at), applied)
    collapsed = _one_live_per_family(base)
    return collapsed.order_by("display_order", "title", "pk")


def current_live_sibling(asset: MarketingAsset, *, at=None) -> MarketingAsset | None:
    """Published in-window sibling with the highest version_number in the family."""
    from django.utils import timezone

    moment = at or timezone.now()
    return (
        MarketingAsset.objects.filter(version_family=asset.version_family)
        .published()
        .within_window(now=moment)
        .select_related("category", "owner_office")
        .order_by("-version_number", "-pk")
        .first()
    )


def resolve_consumer_asset(user: User, asset_id: int, *, at=None) -> ResolveResult:
    """Resolve detail target; archived rows redirect to the live sibling."""
    asset = (
        MarketingAsset.objects.select_related("category", "owner_office")
        .filter(pk=asset_id)
        .first()
    )
    if asset is None:
        raise Http404("No marketing asset matches that id.")

    if visible_to(user, asset, at=at):
        return ("ok", asset)

    if asset.status == MarketingAsset.Status.ARCHIVED:
        live = current_live_sibling(asset, at=at)
        if live is not None and visible_to(user, live, at=at):
            return ("redirect", live)

    raise Http404("No marketing asset matches that id.")


def validation_debt(asset: MarketingAsset) -> list[tuple[str, Any]]:
    from apps.marketing.audience import selectors_for

    debt: list[tuple[str, Any]] = []
    if asset.category is None:
        debt.append(("category", _("Choose a category before publishing.")))
    if not (asset.title or "").strip():
        debt.append(("title", _("Add a title before publishing.")))
    if asset.pk is not None and not selectors_for(asset).exists():
        debt.append(("audience", _("Choose who this asset is for.")))
    if asset.pk is not None:
        has_ready_export = MarketingFile.objects.filter(
            asset=asset,
            role=MarketingFile.Role.EXPORT,
            is_active=True,
            processing_state=MarketingFile.ProcessingState.READY,
        ).exists()
        if not has_ready_export:
            debt.append(
                (
                    "files",
                    _("Upload at least one ready export file before publishing."),
                )
            )
        debt.extend(media_publish_debt(asset))
    return debt


def validation_debt_payload(asset: MarketingAsset) -> dict[str, Any]:
    debt = validation_debt(asset)
    return {
        "isPublishable": not debt,
        "items": [
            {"field": field_name, "message": str(msg)} for field_name, msg in debt
        ],
    }


def _scope_payload(asset: MarketingAsset) -> dict[str, str]:
    level = asset.scope_level
    return {
        "level": level,
        "label": _SCOPE_LABELS[level],
        "officeName": asset.owner_office.name,
    }


def library_payload(asset: MarketingAsset) -> dict[str, Any]:
    preview = ""
    exports = export_files_payload(asset)
    if exports:
        preview = exports[0].get("previewUrl") or ""
    return {
        "id": asset.pk,
        "slug": asset.slug,
        "title": asset.title,
        "description": asset.description,
        "assetType": present_asset_type(asset.asset_type),
        "category": present_category(asset.category),
        "scope": _scope_payload(asset),
        "jurisdictionStateCodes": list(asset.jurisdiction_state_codes or []),
        "brandCodes": list(asset.brand_codes or []),
        "versionNumber": asset.version_number,
        "versionLabel": f"v{asset.version_number}",
        "previewUrl": preview,
        "exportCount": len(exports),
        "publishedAt": (asset.published_at.isoformat() if asset.published_at else None),
        "detailUrl": reverse("marketing_resource_detail", args=[asset.pk]),
    }


def detail_payload(asset: MarketingAsset) -> dict[str, Any]:
    exports = export_files_payload(asset)
    return {
        **library_payload(asset),
        "usageInstructions": asset.usage_instructions,
        "exports": exports,
        "publishAt": asset.publish_at.isoformat() if asset.publish_at else None,
        "expiresAt": asset.expires_at.isoformat() if asset.expires_at else None,
    }


def build_library(
    user: User,
    *,
    params,
    page: int,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    known_codes = frozenset(
        MarketingCategory.objects.active().values_list("code", flat=True)
    )
    filters = LibraryFilters.from_params(params, known_category_codes=known_codes)
    queryset = library_queryset(user, filters)
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    total = queryset.count()
    total_pages = max(1, (total + size - 1) // size)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * size
    page_items = list(queryset[start : start + size])

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
    rows = MarketingCategory.objects.filter(
        Q(is_active=True) | Q(code__in=codes)
    ).order_by("display_order", "label")
    return [{"value": row.code, "label": row.label} for row in rows]


def library_summary(user: User) -> dict[str, int]:
    counts = library_queryset(user, LibraryFilters()).aggregate(
        published=Count("pk"),
        logos=Count("pk", filter=Q(asset_type=ASSET_TYPE_LOGO)),
        templates=Count("pk", filter=Q(asset_type=ASSET_TYPE_TEMPLATE)),
    )
    return {
        "published": counts["published"],
        "logos": counts["logos"],
        "templates": counts["templates"],
    }


def asset_type_filter_options() -> list[dict[str, str]]:
    return [{"value": code, "label": label} for code, label in ASSET_TYPE_CHOICES]


__all__ = [
    "LibraryFilters",
    "apply_library_filters",
    "asset_type_filter_options",
    "build_library",
    "category_filter_options",
    "current_live_sibling",
    "detail_payload",
    "library_payload",
    "library_queryset",
    "library_summary",
    "resolve_consumer_asset",
    "validation_debt",
    "validation_debt_payload",
]
