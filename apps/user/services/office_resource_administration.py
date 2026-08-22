"""Scoped administration of the Office Resources catalog.

Guarding the React pages is not security — every read and write re-checks
``web.view_office_resources_admin`` / ``web.manage_office_resources`` and the
actor's office-tree grant here. Ownership boundaries:

- **Office actors** (branch scope) manage resources owned by their own office.
- **Regional actors** manage resources owned by their region nodes and every
  descendant branch.
- **Company actors** additionally manage head-office (company-owned)
  resources, which requires both company-wide authority *and*
  ``web.publish_company_resources``.

A scoped actor can never select an out-of-boundary owner, edit a wider-scope
resource, or shadow (slug-collide with) a resource owned by a node outside
their writable boundary — crafted owner/slug values fail closed server-side.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import Office, OfficeResource, User
from apps.user.services.hierarchy import descendant_queryset
from apps.user.services.office_resources import (
    effective_library_for_office,
    source_label,
)
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)

VIEW_PERMISSION = "web.view_office_resources_admin"
MANAGE_PERMISSION = "web.manage_office_resources"
COMPANY_PUBLISH_PERMISSION = "web.publish_company_resources"

PAGE_SIZE = 50

# Files are validated by extension; sizes above this are rejected outright.
ALLOWED_FILE_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".png",
        ".jpg",
        ".jpeg",
        ".txt",
        ".csv",
    }
)
MAX_FILE_BYTES = 10 * 1024 * 1024


class StaleResourceVersion(Exception):
    """Optimistic concurrency token no longer matches the resource row."""


# ---------------------------------------------------------------------------
# Scope and authority
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceScope:
    office_ids: frozenset[int]
    includes_company: bool


def _has_permission(actor: User, codename: str) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    return has_effective_permission(actor, codename)


def resource_scope(actor: User) -> ResourceScope:
    """Writable owner offices for this actor, per their role grants."""
    access = get_effective_access(actor)
    ids: set[int] = set()
    if access.company_wide:
        ids.update(Office.objects.filter(is_active=True).values_list("pk", flat=True))
        return ResourceScope(office_ids=frozenset(ids), includes_company=True)

    if access.region_keys:
        regions = Office.objects.filter(
            kind=Office.Kind.REGION, stable_key__in=access.region_keys
        )
        for region in regions:
            ids.update(descendant_queryset(region).values_list("pk", flat=True))
    if access.office_keys:
        seats = Office.objects.filter(stable_key__in=access.office_keys)
        for seat in seats:
            # A branch seat gets itself only; a wider seat carries its subtree.
            ids.add(seat.pk)
            if seat.kind != Office.Kind.BRANCH:
                ids.update(descendant_queryset(seat).values_list("pk", flat=True))
    return ResourceScope(office_ids=frozenset(ids), includes_company=False)


def can_view_resources(actor: User) -> bool:
    return _has_permission(actor, VIEW_PERMISSION)


def can_manage_resources(actor: User) -> bool:
    return _has_permission(actor, MANAGE_PERMISSION)


def can_publish_company(actor: User) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    access = get_effective_access(actor)
    return access.company_wide and _has_permission(actor, COMPANY_PUBLISH_PERMISSION)


def managed_resource_queryset(actor: User) -> QuerySet[OfficeResource]:
    return OfficeResource.objects.filter(
        owner_office__in=resource_scope(actor).office_ids
    )


def ensure_view_authority(actor: User) -> None:
    if not can_view_resources(actor):
        log_denial(actor, reason="missing_permission")
        raise PermissionDenied(
            _("You do not have permission to view office resources.")
        )


def ensure_manage_authority(actor: User, owner: Office | None = None) -> ResourceScope:
    """Write authority check. Fails closed on permission, scope, and level."""
    scope = resource_scope(actor)
    if not can_manage_resources(actor):
        log_denial(actor, reason="missing_manage_permission")
        raise PermissionDenied(
            _("You do not have permission to manage office resources.")
        )
    if owner is not None:
        if owner.pk not in scope.office_ids:
            log_denial(actor, reason="out_of_scope")
            raise PermissionDenied(
                _("That owning office is outside your administrative scope.")
            )
        if owner.kind == Office.Kind.HEAD_OFFICE and not can_publish_company(actor):
            log_denial(actor, reason="company_publish_required")
            raise PermissionDenied(
                _("Publishing company-owned resources requires company authority.")
            )
    return scope


def log_denial(
    actor: User, *, reason: str, resource: OfficeResource | None = None
) -> None:
    log_event(
        "security.office_resource_administration.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=OfficeResource._meta.label_lower,
            target_id=str(getattr(resource, "pk", "") or ""),
            target_label=getattr(resource, "slug", "") or "",
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def _resource_target(resource: OfficeResource) -> AuditTarget:
    return AuditTarget(
        target_type=OfficeResource._meta.label_lower,
        target_id=str(resource.pk),
        target_label=f"{resource.owner_office.name} / {resource.slug}",
    )


def resource_version(resource: OfficeResource) -> str:
    stamp = resource.updated_at.isoformat(timespec="microseconds")
    return f"{resource.pk}:{stamp}"


# ---------------------------------------------------------------------------
# Filters + list
# ---------------------------------------------------------------------------

_STATUS_CHOICES = ("active", "inactive", "scheduled", "expired", "archived")


@dataclass(frozen=True)
class AdminResourceFilters:
    q: str = ""
    category: str = ""
    resource_type: str = ""
    status: str = ""
    owner: str = ""
    region: str = ""

    def as_payload(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def parse_admin_filters(params) -> AdminResourceFilters:
    category = (params.get("category") or "").strip()
    if category not in OfficeResource.Category.values:
        category = ""
    resource_type = (params.get("type") or "").strip()
    if resource_type not in OfficeResource.ResourceType.values:
        resource_type = ""
    status = (params.get("status") or "").strip()
    if status not in _STATUS_CHOICES:
        status = ""
    return AdminResourceFilters(
        q=(params.get("q") or "").strip()[:120],
        category=category,
        resource_type=resource_type,
        status=status,
        owner=(params.get("owner") or "").strip()[:80],
        region=(params.get("region") or "").strip()[:80],
    )


def resource_state(resource: OfficeResource) -> str:
    today = timezone.localdate()
    if resource.archived_at is not None:
        return "archived"
    if not resource.is_active:
        return "inactive"
    if resource.starts_at and resource.starts_at > today:
        return "scheduled"
    if resource.ends_at and resource.ends_at < today:
        return "expired"
    return "active"


def _matches_status(resource: OfficeResource, status: str) -> bool:
    if not status:
        return True
    if status == "archived":
        return resource.archived_at is not None
    if resource.archived_at is not None:
        return False
    if status == "active":
        return resource.is_active
    if status == "inactive":
        return not resource.is_active
    today = timezone.localdate()
    if status == "scheduled":
        return bool(resource.starts_at and resource.starts_at > today)
    if status == "expired":
        return bool(resource.ends_at and resource.ends_at < today)
    return True


def build_resource_list(
    actor: User, *, filters: AdminResourceFilters, page: int = 1
) -> dict[str, Any]:
    from apps.web.contracts import list_response

    ensure_view_authority(actor)
    scope = resource_scope(actor)
    queryset = managed_resource_queryset(actor)
    if filters.q:
        queryset = queryset.filter(
            Q(title__icontains=filters.q)
            | Q(summary__icontains=filters.q)
            | Q(slug__icontains=filters.q)
        )
    if filters.category:
        queryset = queryset.filter(category=filters.category)
    if filters.resource_type:
        queryset = queryset.filter(resource_type=filters.resource_type)
    if filters.owner:
        queryset = queryset.filter(owner_office__stable_key=filters.owner)
    if filters.region:
        queryset = queryset.filter(
            Q(owner_office__region__stable_key=filters.region)
            | Q(owner_office__stable_key=filters.region)
        )

    ordered = sorted(
        queryset,
        key=lambda item: (item.category, item.sort_order, item.title, item.pk),
    )
    matching = [item for item in ordered if _matches_status(item, filters.status)]
    page = max(1, page)
    start = (page - 1) * PAGE_SIZE
    rows = [_admin_row(item) for item in matching[start : start + PAGE_SIZE]]

    writable_offices = (
        Office.objects.filter(pk__in=scope.office_ids)
        .select_related("region", "parent")
        .order_by("sort_order", "name")
        if scope.office_ids
        else Office.objects.none()
    )
    return {
        "resources": list_response(
            rows,
            page=page,
            page_size=PAGE_SIZE,
            total_items=len(matching),
            filters=filters.as_payload(),
        ),
        "filterOptions": {
            "categories": [
                {"value": value, "label": label}
                for value, label in OfficeResource.Category.choices
            ],
            "types": [
                {"value": value, "label": label}
                for value, label in OfficeResource.ResourceType.choices
            ],
            "statuses": [
                {"value": "active", "label": "Active"},
                {"value": "inactive", "label": "Inactive"},
                {"value": "scheduled", "label": "Scheduled"},
                {"value": "expired", "label": "Expired"},
                {"value": "archived", "label": "Archived"},
            ],
            "owners": [
                {"value": node.stable_key, "label": node.path_label()}
                for node in writable_offices
            ],
        },
        "capabilities": {
            "canManage": can_manage_resources(actor),
            "canPublishCompany": can_publish_company(actor),
        },
    }


def _admin_row(resource: OfficeResource) -> dict[str, Any]:
    return {
        "id": resource.pk,
        "slug": resource.slug,
        "title": resource.title,
        "summary": resource.summary,
        "category": resource.category,
        "categoryLabel": OfficeResource.Category(resource.category).label,
        "resourceType": resource.resource_type,
        "typeLabel": OfficeResource.ResourceType(resource.resource_type).label,
        "ownerPathLabel": resource.owner_office.path_label(),
        "ownerStableKey": resource.owner_office.stable_key,
        "sourceLabel": source_label(resource),
        "state": resource_state(resource),
        "isActive": resource.is_active,
        "isArchived": resource.archived_at is not None,
        "processingState": resource.processing_state,
        "fileName": resource.original_file_name,
        "startsAt": resource.starts_at.isoformat() if resource.starts_at else "",
        "endsAt": resource.ends_at.isoformat() if resource.ends_at else "",
        "updatedAt": resource.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Detail payload + preview
# ---------------------------------------------------------------------------


def detail_payload(
    actor: User,
    resource: OfficeResource | None,
    *,
    preview_office_id: int | None = None,
) -> dict[str, Any]:
    ensure_view_authority(actor)
    scope = resource_scope(actor)
    writable_offices = (
        list(
            Office.objects.filter(pk__in=scope.office_ids)
            .select_related("region")
            .order_by("sort_order", "name")
        )
        if scope.office_ids
        else []
    )

    preview = None
    if preview_office_id is not None:
        selected = next(
            (node for node in writable_offices if node.pk == preview_office_id),
            None,
        )
        if selected is not None:
            library = effective_library_for_office(selected)
            items = [_preview_row(item, selected) for item in library]
            local_count = sum(1 for row in items if row["origin"] == "local")
            preview = {
                "officeId": selected.pk,
                "officeLabel": selected.path_label(),
                "items": items,
                "localCount": local_count,
                "inheritedCount": len(items) - local_count,
            }

    return {
        "resource": _detail_resource(resource) if resource else None,
        "version": resource_version(resource) if resource else "",
        "preview": preview,
        "writableOffices": [
            {"id": node.pk, "label": node.path_label(), "kind": node.kind}
            for node in writable_offices
        ],
        "capabilities": {
            "canManage": can_manage_resources(actor),
            "canPublishCompany": can_publish_company(actor),
        },
        "categories": [
            {"value": value, "label": label}
            for value, label in OfficeResource.Category.choices
        ],
        "types": [
            {"value": value, "label": label}
            for value, label in OfficeResource.ResourceType.choices
        ],
    }


def _preview_row(resource: OfficeResource, selected: Office) -> dict[str, Any]:
    origin = "local" if resource.owner_office.pk == selected.pk else "inherited"
    row: dict[str, Any] = {
        "slug": resource.slug,
        "title": resource.title,
        "summary": resource.summary,
        "categoryLabel": OfficeResource.Category(resource.category).label,
        "resourceType": resource.resource_type,
        "sourceLabel": source_label(resource),
        "origin": origin,
    }
    types = OfficeResource.ResourceType
    if resource.resource_type == types.LINK:
        row["url"] = resource.url
    elif resource.resource_type == types.FILE:
        row["downloadUrl"] = reverse("office_resources_download", args=[resource.slug])
    else:
        row["body"] = resource.body
    return row


def _detail_resource(resource: OfficeResource) -> dict[str, Any]:
    file_name = ""
    if resource.file:
        file_name = resource.original_file_name or Path(resource.file.name).name
    return {
        "id": resource.pk,
        "slug": resource.slug,
        "title": resource.title,
        "summary": resource.summary,
        "category": resource.category,
        "resourceType": resource.resource_type,
        "body": resource.body,
        "url": resource.url,
        "ownerId": resource.owner_office.pk,
        "ownerPathLabel": resource.owner_office.path_label(),
        "isActive": resource.is_active,
        "isArchived": resource.archived_at is not None,
        "archivedAt": (
            resource.archived_at.isoformat() if resource.archived_at else ""
        ),
        "processingState": resource.processing_state,
        "fileName": file_name,
        "downloadUrl": (
            reverse("office_resources_download", args=[resource.slug])
            if resource.file
            else ""
        ),
        "sortOrder": resource.sort_order,
        "startsAt": resource.starts_at.isoformat() if resource.starts_at else "",
        "endsAt": resource.ends_at.isoformat() if resource.ends_at else "",
        "createdAt": resource.created_at.isoformat(),
        "updatedAt": resource.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def _snapshot(resource: OfficeResource) -> dict[str, Any]:
    return {
        "slug": resource.slug,
        "title": resource.title,
        "summary": resource.summary,
        "category": resource.category,
        "resource_type": resource.resource_type,
        "owner_office": resource.owner_office.stable_key,
        "body_excerpt": resource.body[:200],
        "url": resource.url,
        "is_active": resource.is_active,
        "sort_order": resource.sort_order,
        "starts_at": resource.starts_at.isoformat() if resource.starts_at else "",
        "ends_at": resource.ends_at.isoformat() if resource.ends_at else "",
        "archived": resource.archived_at is not None,
        "file": resource.original_file_name,
        "processing_state": resource.processing_state,
    }


def _shadowing_blocked(scope: ResourceScope, resource: OfficeResource) -> bool:
    """True when the slug collides with a resource outside the writable boundary."""
    collisions = (
        OfficeResource.objects.filter(slug=resource.slug)
        .exclude(pk=resource.pk)
        .select_related("owner_office")
    )
    return any(other.owner_office.pk not in scope.office_ids for other in collisions)


@transaction.atomic
def create_resource(
    actor: User, *, cleaned: dict[str, Any], uploaded_file=None
) -> OfficeResource:
    owner: Office = cleaned["owner_office"]
    scope = ensure_manage_authority(actor, owner)
    resource = OfficeResource(owner_office=owner)
    _apply_fields(resource, cleaned)
    if uploaded_file is not None:
        _attach_file(resource, uploaded_file)
    if _shadowing_blocked(scope, resource):
        raise ValidationError(
            {
                "slug": _(
                    "This slug shadows a resource outside your administrative "
                    "boundary. Choose another slug."
                )
            }
        )
    resource.full_clean(exclude={"created_by"})
    resource.created_by = actor
    resource.save()
    log_event(
        "office_resource.created",
        actor=actor_from_user(actor),
        target=_resource_target(resource),
        after=_snapshot(resource),
        office_id=owner.stable_key,
        region_id=owner.region.stable_key if owner.region else "",
    )
    return resource


@transaction.atomic
def update_resource(
    actor: User, resource_id: int, *, cleaned: dict[str, Any], expected_version: str
) -> OfficeResource:
    locked = (
        OfficeResource.objects.select_for_update(of=("self",))
        .select_related("owner_office")
        .get(pk=resource_id)
    )
    scope = ensure_manage_authority(actor, locked.owner_office)
    new_owner: Office = cleaned.get("owner_office") or locked.owner_office
    if new_owner.pk != locked.owner_office.pk:
        # Ownership moves are held to the stricter of the two boundaries.
        ensure_manage_authority(actor, new_owner)
    if resource_version(locked) != (expected_version or ""):
        raise StaleResourceVersion()

    before = _snapshot(locked)
    _apply_fields(locked, cleaned)
    if new_owner.pk != locked.owner_office.pk:
        locked.owner_office = new_owner
    if _shadowing_blocked(scope, locked):
        raise ValidationError(
            {
                "slug": _(
                    "This slug shadows a resource outside your administrative "
                    "boundary. Choose another slug."
                )
            }
        )
    locked.full_clean(exclude={"created_by"})
    locked.save()
    after = _snapshot(locked)
    if before != after:
        log_event(
            "office_resource.updated",
            actor=actor_from_user(actor),
            target=_resource_target(locked),
            before=before,
            after=after,
            office_id=locked.owner_office.stable_key,
            region_id=(
                locked.owner_office.region.stable_key
                if locked.owner_office.region
                else ""
            ),
        )
    return locked


def _apply_fields(resource: OfficeResource, cleaned: dict[str, Any]) -> None:
    text_fields = ("title", "summary", "category", "resource_type", "body", "url")
    for field in text_fields:
        if cleaned.get(field) is not None:
            setattr(resource, field, cleaned[field])
    if cleaned.get("slug"):
        resource.slug = cleaned["slug"]
    elif not resource.slug and resource.title:
        resource.slug = slugify(resource.title)[:80]
    if cleaned.get("sort_order") is not None:
        resource.sort_order = cleaned["sort_order"]
    if cleaned.get("is_active") is not None:
        resource.is_active = bool(cleaned["is_active"])
    for field in ("starts_at", "ends_at"):
        if field in cleaned:
            setattr(resource, field, cleaned[field])


_TRANSITIONS = {
    "activate",
    "deactivate",
    "archive",
    "unarchive",
    "move_up",
    "move_down",
}


@transaction.atomic
def transition_resource(
    actor: User, resource_id: int, *, action: str, expected_version: str
) -> OfficeResource:
    if action not in _TRANSITIONS:
        raise ValidationError({"action": _("Unknown action.")})
    locked = (
        OfficeResource.objects.select_for_update(of=("self",))
        .select_related("owner_office")
        .get(pk=resource_id)
    )
    ensure_manage_authority(actor, locked.owner_office)
    if resource_version(locked) != (expected_version or ""):
        raise StaleResourceVersion()

    before = _snapshot(locked)
    if action == "activate":
        locked.is_active = True
    elif action == "deactivate":
        locked.is_active = False
    elif action == "archive":
        # Archive, never delete: history and referenced metadata survive.
        locked.is_active = False
        if locked.archived_at is None:
            locked.archived_at = timezone.now()
    elif action == "unarchive":
        locked.archived_at = None
    else:
        _shift_order(locked, direction=-1 if action == "move_up" else 1)
    locked.full_clean(exclude={"created_by"})
    locked.save()
    after = _snapshot(locked)
    if before != after:
        log_event(
            f"office_resource.{action}",
            actor=actor_from_user(actor),
            target=_resource_target(locked),
            before=before,
            after=after,
            office_id=locked.owner_office.stable_key,
            region_id=(
                locked.owner_office.region.stable_key
                if locked.owner_office.region
                else ""
            ),
        )
    return locked


def _shift_order(resource: OfficeResource, *, direction: int) -> None:
    siblings = list(
        OfficeResource.objects.filter(
            owner_office=resource.owner_office,
            category=resource.category,
            archived_at__isnull=True,
        ).order_by("sort_order", "title", "pk")
    )
    index = next((i for i, item in enumerate(siblings) if item.pk == resource.pk), None)
    if index is None:
        return
    swap_with = index + direction
    if swap_with < 0 or swap_with >= len(siblings):
        return
    neighbour = siblings[swap_with]
    resource.sort_order, neighbour.sort_order = (
        neighbour.sort_order,
        resource.sort_order,
    )
    neighbour.save(update_fields=["sort_order", "updated_at"])


def replace_file(
    actor: User, resource_id: int, *, uploaded_file, expected_version: str
) -> OfficeResource:
    """Replace the file on a resource.

    On validation failure the row is marked quarantined + deactivated and the
    failure is committed BEFORE the error propagates, so the broken state is
    visible and recoverable instead of silently rolled back.
    """
    quarantine_error: ValidationError | None = None
    with transaction.atomic():
        locked = (
            OfficeResource.objects.select_for_update(of=("self",))
            .select_related("owner_office")
            .get(pk=resource_id)
        )
        ensure_manage_authority(actor, locked.owner_office)
        if resource_version(locked) != (expected_version or ""):
            raise StaleResourceVersion()

        old_name = locked.file.name if locked.file else ""
        old_original = locked.original_file_name
        try:
            # Savepoint: a failed attach rolls the row back while the outer
            # transaction still commits the quarantine bookkeeping below.
            with transaction.atomic():
                _attach_file(locked, uploaded_file)
                locked.full_clean(exclude={"created_by"})
                locked.save()
        except ValidationError as exc:
            new_storage_name = locked.file.name if locked.file else ""
            if new_storage_name and new_storage_name != old_name:
                # Clean up the abandoned upload object.
                storage = locked.file.storage
                if storage.exists(new_storage_name):
                    storage.delete(new_storage_name)
            locked.processing_state = OfficeResource.ProcessingState.QUARANTINED
            locked.is_active = False
            locked.file.name = old_name
            locked.original_file_name = old_original
            locked.save()
            log_event(
                "office_resource.file_quarantined",
                actor=actor_from_user(actor),
                target=_resource_target(locked),
                metadata={"fileName": Path(uploaded_file.name).name},
                outcome=AuditEvent.Outcome.FAILURE,
                office_id=locked.owner_office.stable_key,
                region_id=(
                    locked.owner_office.region.stable_key
                    if locked.owner_office.region
                    else ""
                ),
            )
            quarantine_error = exc

    if quarantine_error is not None:
        # Raised outside the transaction so the quarantine state commits.
        raise ValidationError(quarantine_error.error_dict or quarantine_error.messages)

    if old_name and old_name != locked.file.name:
        storage = locked.file.storage
        if storage.exists(old_name):
            storage.delete(old_name)
    log_event(
        "office_resource.file_replaced",
        actor=actor_from_user(actor),
        target=_resource_target(locked),
        metadata={"fileName": locked.original_file_name},
        office_id=locked.owner_office.stable_key,
        region_id=(
            locked.owner_office.region.stable_key if locked.owner_office.region else ""
        ),
    )
    return locked


def _attach_file(resource: OfficeResource, uploaded_file) -> None:
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_FILE_EXTENSIONS:
        raise ValidationError(
            {"file": _(f"File type '{extension or 'unknown'}' is not allowed.")}
        )
    if uploaded_file.size > MAX_FILE_BYTES:
        raise ValidationError({"file": _("Files must be 10 MB or smaller.")})
    uploaded_file.seek(0)
    resource.file.save(
        Path(uploaded_file.name).name,
        ContentFile(uploaded_file.read()),
        save=False,
    )
    resource.original_file_name = Path(uploaded_file.name).name
    resource.processing_state = OfficeResource.ProcessingState.READY
