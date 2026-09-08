"""Effective office-resource visibility for one signed-in user.

Visibility contract (deterministic, documented in docs/office-resources.md):

1. The scope chain is the primary office plus its ancestors up to and
   including the head office. A user without a primary office has no chain
   and therefore sees nothing.
2. Only non-archived, active resources inside their publish window
   (``starts_at`` / ``ends_at``) on nodes of that chain are candidates.
   Filtering happens here, before serialization — search can never see other
   offices' data.
3. ``slug`` is the resource identity across scopes. When the same slug exists
   at multiple levels, the closest scope wins (office > region > company), so
   a branch can override company defaults without duplicates appearing.
4. Ordering within a category: ``sort_order``, then title, then pk.

Resolution is cached per office node keyed by a generation counter that any
``OfficeResource`` write bumps (see signals at the bottom), so admin changes
appear immediately without stale reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.core.cache import cache
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from apps.user.models import Office, OfficeResource, User

_CATEGORY_ORDER = {
    value: index
    for index, (value, _label) in enumerate(OfficeResource.Category.choices)
}

_SOURCE_LABELS = {"company": "Company", "region": "Region"}

GENERATION_KEY = "office_resources:generation"
_CACHE_TTL = 300


@dataclass(frozen=True)
class ResourceFilters:
    q: str = ""
    category: str = ""

    @classmethod
    def from_params(cls, params) -> ResourceFilters:
        category = (params.get("category") or "").strip()
        if category not in OfficeResource.Category.values:
            category = ""
        return cls(
            q=(params.get("q") or "").strip()[:120],
            category=category,
        )


def scope_chain(office: Office) -> list[Office]:
    """The office followed by ancestors, head office last."""
    chain: list[Office] = []
    current: Office | None = office
    while current is not None and current not in chain:
        chain.append(current)
        current = current.parent
    return chain


def _generation() -> int:
    return int(cache.get(GENERATION_KEY, 0))


def bump_generation() -> None:
    """Invalidate every cached effective library (any resource write)."""
    try:
        cache.incr(GENERATION_KEY)
    except ValueError:
        cache.set(GENERATION_KEY, 1, None)


def effective_library_for_office(office_node: Office) -> list[OfficeResource]:
    """Deduplicated, precedence-ordered library for one office node.

    The single resolution path shared by the agent page, search, downloads,
    and the admin preview — so a preview always matches what that office's
    members actually see.
    """
    key = f"office_resources:library:{_generation()}:{office_node.pk}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    chain = scope_chain(office_node)
    chain_ids = {node.pk: index for index, node in enumerate(chain)}
    today = timezone.localdate()
    by_slug: dict[str, tuple[int, OfficeResource]] = {}
    resources = (
        OfficeResource.objects.filter(
            owner_office__in=chain,
            is_active=True,
            archived_at__isnull=True,
        )
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=today))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=today))
        .select_related("owner_office")
        .order_by("category", "sort_order", "title", "pk")
    )
    for resource in resources:
        specificity = chain_ids.get(resource.owner_office.pk, len(chain_ids))
        incumbent = by_slug.get(resource.slug)
        if incumbent is None or specificity < incumbent[0]:
            by_slug[resource.slug] = (specificity, resource)

    winners = [resource for _spec, resource in by_slug.values()]
    winners.sort(
        key=lambda item: (
            _CATEGORY_ORDER.get(item.category, len(_CATEGORY_ORDER)),
            item.sort_order,
            item.title,
            item.pk,
        )
    )
    cache.set(key, winners, _CACHE_TTL)
    return winners


def effective_resources_queryset(user: User):
    """Scoped queryset of active, in-window resources for one user.

    This is the single visibility gate: the download view reuses it so file
    access can never exceed page visibility.
    """
    primary = getattr(user, "office", None)
    if primary is None or not primary.is_active:
        return OfficeResource.objects.none()
    today = timezone.localdate()
    return (
        OfficeResource.objects.filter(
            owner_office__in=scope_chain(primary),
            is_active=True,
            archived_at__isnull=True,
        )
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=today))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=today))
        .select_related("owner_office")
        .order_by("category", "sort_order", "title", "pk")
    )


def effective_resources(user: User) -> list[OfficeResource]:
    """Deduplicated, precedence-ordered resource list for one user."""
    primary = getattr(user, "office", None)
    if primary is None or not primary.is_active:
        return []
    return effective_library_for_office(primary)


def apply_resource_filters(
    resources: list[OfficeResource], filters: ResourceFilters
) -> list[OfficeResource]:
    """Search/filter an already-scoped resource list (never widens it)."""
    result = resources
    if filters.category:
        result = [item for item in result if item.category == filters.category]
    if filters.q:
        needle = filters.q.casefold()
        result = [
            item
            for item in result
            if needle in item.title.casefold()
            or needle in item.summary.casefold()
            or needle in item.body.casefold()
        ]
    return result


def source_label(resource: OfficeResource) -> str:
    level = resource.scope_level
    return _SOURCE_LABELS.get(level, resource.owner_office.name)


def _resource_payload(resource: OfficeResource) -> dict[str, object]:
    payload: dict[str, object] = {
        "slug": resource.slug,
        "title": resource.title,
        "summary": resource.summary,
        "category": resource.category,
        "categoryLabel": OfficeResource.Category(resource.category).label,
        "resourceType": resource.resource_type,
        "sourceLabel": source_label(resource),
        "sourceLevel": resource.scope_level,
    }
    types = OfficeResource.ResourceType
    if resource.resource_type == types.LINK:
        payload["url"] = resource.url
    elif resource.resource_type == types.FILE:
        payload["downloadUrl"] = reverse(
            "office_resources_download", args=[resource.slug]
        )
        payload["fileName"] = (
            resource.original_file_name or Path(resource.file.name).name
            if resource.file
            else ""
        )
    else:
        payload["body"] = resource.body
    return payload


def group_by_category(resources: list[OfficeResource]) -> list[dict[str, object]]:
    """Group resolved resources into stable, labeled categories."""
    labels = dict(OfficeResource.Category.choices)
    groups: dict[str, list[OfficeResource]] = {}
    for resource in resources:
        groups.setdefault(resource.category, []).append(resource)
    return [
        {
            "key": key,
            "label": labels.get(key, key),
            "items": [_resource_payload(item) for item in items],
        }
        for key, items in groups.items()
    ]


def _categories_payload() -> list[dict[str, str]]:
    return [
        {"value": value, "label": label}
        for value, label in OfficeResource.Category.choices
    ]


def office_resources_page_payload(
    user: User, *, filters: ResourceFilters
) -> dict[str, object]:
    """Everything the OfficeResources Inertia page needs for one actor."""
    primary = getattr(user, "office", None)
    if primary is None or not primary.is_active:
        return {
            "groups": [],
            "filters": {"q": filters.q, "category": filters.category},
            "categories": _categories_payload(),
            "empty": {
                "title": "No office assigned",
                "description": (
                    "Your profile does not have a primary office yet. "
                    "Update your profile or contact your branch administrator."
                ),
                "kind": "no-office",
            },
        }
    scoped = effective_resources(user)
    visible = apply_resource_filters(scoped, filters)
    if visible:
        empty = None
    elif scoped:
        empty = {
            "title": "No resources found",
            "description": "Nothing matches your search.",
            "kind": "no-results",
        }
    else:
        empty = {
            "title": "No resources yet",
            "description": (
                "Your office has no published resources yet. "
                "Ask your branch administrator."
            ),
            "kind": "empty",
        }
    return {
        "groups": group_by_category(visible),
        "filters": {"q": filters.q, "category": filters.category},
        "categories": _categories_payload(),
        "empty": empty,
    }


@receiver(post_save, sender=OfficeResource)
def _resource_saved(sender, instance, **kwargs) -> None:
    bump_generation()


@receiver(post_delete, sender=OfficeResource)
def _resource_deleted(sender, instance, **kwargs) -> None:
    bump_generation()
