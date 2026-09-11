"""Attach, replace, reorder, remove, and serve marketing files."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.marketing.media import (
    EXPORT_ALLOWED_MEDIA,
    MAX_EXPORT_FILES,
    MAX_SOURCE_FILES,
    SOURCE_ALLOWED_MEDIA,
    inspect_marketing_upload,
)
from apps.marketing.models import MarketingAsset, MarketingFile
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

State = MarketingFile.ProcessingState
Role = MarketingFile.Role

DOWNLOAD_SOURCES = "web.download_marketing_sources"


# --------------------------------------------------------------------------- #
# Authority
# --------------------------------------------------------------------------- #


def assert_can_manage_media(actor: User, asset: MarketingAsset) -> None:
    from apps.marketing.administration import assert_can_author

    assert_can_author(actor, asset.owner_office)


def assert_can_mutate_media(actor: User, asset: MarketingAsset) -> None:
    assert_can_manage_media(actor, asset)
    if asset.status != MarketingAsset.Status.DRAFT:
        raise ValidationError(
            {
                "file": _(
                    "Published marketing assets cannot change files in place. "
                    "Duplicate as a new version first."
                )
            }
        )


def _target(row: MarketingFile) -> AuditTarget:
    return AuditTarget(
        target_type=MarketingFile._meta.label_lower,
        target_id=str(row.pk or ""),
        target_label=row.display_name,
    )


def _snapshot(row: MarketingFile) -> dict[str, Any]:
    return {
        "display_name": row.display_name,
        "role": row.role,
        "media_type": row.media_type,
        "byte_size": row.byte_size,
        "checksum": row.checksum,
        "processing_state": row.processing_state,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
    }


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def _next_sort_order(asset: MarketingAsset, *, role: str) -> int:
    existing = (
        MarketingFile.objects.filter(asset=asset, role=role, is_active=True)
        .order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
    )
    return 0 if existing is None else existing + 1


def _assert_role_room(asset: MarketingAsset, *, role: str) -> None:
    if role == Role.EXPORT:
        limit = MAX_EXPORT_FILES
        label = "export files"
    elif role == Role.SOURCE:
        limit = MAX_SOURCE_FILES
        label = "source files"
    else:
        raise ValidationError({"file": _("That file role cannot be uploaded.")})
    count = MarketingFile.objects.filter(asset=asset, role=role, is_active=True).count()
    if count >= limit:
        raise ValidationError(
            {"file": _(f"A marketing asset can carry at most {limit} {label}.")}
        )


@transaction.atomic
def attach_file(
    actor: User,
    asset: MarketingAsset,
    uploaded,
    *,
    role: str,
) -> MarketingFile:
    """Attach an EXPORT or SOURCE file. PREVIEW is system-generated only."""
    assert_can_mutate_media(actor, asset)
    if role == Role.PREVIEW:
        raise ValidationError(
            {
                "file": _(
                    "Preview files are generated automatically. Upload an export "
                    "image instead."
                )
            }
        )
    if role not in {Role.EXPORT, Role.SOURCE}:
        raise ValidationError({"file": _("Unknown file role.")})

    inspected, data = inspect_marketing_upload(uploaded, role=role)
    _assert_role_room(asset, role=role)
    sort_order = _next_sort_order(asset, role=role)

    row = MarketingFile(
        asset=asset,
        role=role,
        display_name=inspected.display_name,
        media_type=inspected.media_type,
        byte_size=inspected.byte_size,
        checksum=inspected.checksum,
        processing_state=State.PENDING,
        sort_order=sort_order,
        uploaded_by=actor,
    )
    row.file.save(inspected.display_name, ContentFile(data), save=False)
    row.full_clean(exclude={"uploaded_by"})
    row.save()

    log_event(
        "marketing.file_attached",
        actor=actor_from_user(actor),
        target=_target(row),
        after=_snapshot(row),
        metadata={"asset_id": asset.pk},
    )
    transaction.on_commit(lambda: _queue_processing(row.pk))
    return row


def _queue_processing(file_id: int) -> None:
    from apps.marketing.tasks import process_marketing_file

    process_marketing_file.delay(file_id)


def _deactivate_or_delete(actor: User, row: MarketingFile, *, reason: str) -> None:
    before = _snapshot(row)
    published = row.asset.status != MarketingAsset.Status.DRAFT
    if published:
        row.is_active = False
        row.save(update_fields=["is_active", "updated_at"])
        action = "marketing.file_retired"
        after = _snapshot(row)
    else:
        _delete_stored_objects(row)
        row.delete()
        action = "marketing.file_deleted"
        after = {}
    log_event(
        action,
        actor=actor_from_user(actor),
        target=_target(row),
        before=before,
        after=after,
        reason=reason,
        metadata={"asset_id": row.asset.pk},
    )


def _delete_stored_objects(row: MarketingFile) -> None:
    storage = row.file.storage
    if row.file:
        storage.delete(row.file.name)
    for key in (row.variants or {}).values():
        if key:
            storage.delete(key)


@transaction.atomic
def replace_file(actor: User, row: MarketingFile, uploaded) -> MarketingFile:
    assert_can_mutate_media(actor, row.asset)
    if row.role == Role.PREVIEW:
        raise ValidationError(
            {
                "file": _(
                    "Preview files are generated automatically and cannot be replaced."
                )
            }
        )
    asset = row.asset
    role = row.role
    order = row.sort_order
    _deactivate_or_delete(actor, row, reason="replaced")
    replacement = attach_file(actor, asset, uploaded, role=role)
    replacement.sort_order = order
    replacement.save(update_fields=["sort_order", "updated_at"])
    return replacement


@transaction.atomic
def remove_file(actor: User, row: MarketingFile) -> None:
    assert_can_mutate_media(actor, row.asset)
    if row.role == Role.PREVIEW:
        raise ValidationError(
            {
                "file": _(
                    "Preview files are generated automatically and cannot be removed."
                )
            }
        )
    _deactivate_or_delete(actor, row, reason="removed_by_admin")


@transaction.atomic
def reorder_files(
    actor: User,
    asset: MarketingAsset,
    ordered_ids: list[int],
    *,
    role: str = Role.EXPORT,
) -> None:
    assert_can_mutate_media(actor, asset)
    if role not in {Role.EXPORT, Role.SOURCE}:
        raise ValidationError({"file": _("That role cannot be reordered.")})
    rows = {
        item.pk: item
        for item in MarketingFile.objects.filter(asset=asset, role=role, is_active=True)
    }
    before = [item.pk for item in sorted(rows.values(), key=lambda r: r.sort_order)]

    seen: list[int] = []
    for candidate in ordered_ids:
        if candidate in rows and candidate not in seen:
            seen.append(candidate)
    seen.extend(pk for pk in rows if pk not in seen)

    for index, pk in enumerate(seen):
        item = rows[pk]
        if item.sort_order != index:
            item.sort_order = index
            item.save(update_fields=["sort_order", "updated_at"])

    log_event(
        "marketing.file_reordered",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=MarketingAsset._meta.label_lower,
            target_id=str(asset.pk),
            target_label=asset.slug,
        ),
        before={"order": before, "role": role},
        after={"order": seen, "role": role},
    )


def clone_files_to(actor: User, source: MarketingAsset, target: MarketingAsset) -> None:
    """Copy active EXPORT and SOURCE bytes onto a new version draft.

    PREVIEW rows are skipped — they are regenerated when the cloned export
    images are processed.
    """
    for row in MarketingFile.objects.filter(
        asset=source, is_active=True, role__in=[Role.EXPORT, Role.SOURCE]
    ).order_by("role", "sort_order", "pk"):
        storage = row.file.storage
        if not row.file or not storage.exists(row.file.name):
            continue
        with storage.open(row.file.name, "rb") as handle:
            data = handle.read()
        clone = MarketingFile(
            asset=target,
            role=row.role,
            display_name=row.display_name,
            media_type=row.media_type,
            byte_size=len(data),
            checksum=row.checksum,
            processing_state=State.PENDING,
            sort_order=row.sort_order,
            uploaded_by=actor,
        )
        clone.file.save(row.display_name, ContentFile(data), save=False)
        clone.full_clean(exclude={"uploaded_by"})
        clone.save()
        transaction.on_commit(lambda pk=clone.pk: _queue_processing(pk))


# --------------------------------------------------------------------------- #
# Serving
# --------------------------------------------------------------------------- #


def export_url(row: MarketingFile) -> str:
    return reverse("marketing_resource_export", args=[row.pk])


def preview_url(row: MarketingFile) -> str:
    return reverse("marketing_resource_preview", args=[row.pk])


def source_url(row: MarketingFile) -> str:
    return reverse("marketing_resource_source", args=[row.pk])


def resolve_variant_key(row: MarketingFile, variant: str = "") -> str:
    if not variant:
        return row.file.name
    return (row.variants or {}).get(variant) or row.file.name


def stream_file(request, row: MarketingFile, *, variant: str = "", as_attachment=None):
    key = resolve_variant_key(row, variant)
    storage = row.file.storage
    if not key or not storage.exists(key):
        raise Http404("That file is no longer stored.")
    if as_attachment is None:
        as_attachment = not row.is_image
    response = FileResponse(
        storage.open(key, "rb"),
        as_attachment=as_attachment,
        filename=row.display_name,
        content_type=row.media_type,
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


def log_file_denial(actor: User, file_id: str, *, reason: str) -> None:
    log_event(
        "security.marketing.file_denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=MarketingFile._meta.label_lower, target_id=str(file_id)
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def assert_readable_export(actor: User, row: MarketingFile) -> None:
    from apps.marketing.audience import assert_visible

    assert_visible(actor, row.asset, reason="file_out_of_audience")
    if row.role != Role.EXPORT:
        log_file_denial(actor, str(row.pk), reason="not_export")
        raise PermissionDenied("That file is not available.")
    if not row.is_readable:
        log_file_denial(actor, str(row.pk), reason="file_not_ready")
        raise PermissionDenied("That file is not available.")


def assert_readable_preview(actor: User, row: MarketingFile) -> None:
    from apps.marketing.audience import assert_visible

    assert_visible(actor, row.asset, reason="file_out_of_audience")
    if row.role == Role.PREVIEW:
        if not row.is_readable:
            log_file_denial(actor, str(row.pk), reason="file_not_ready")
            raise PermissionDenied("That file is not available.")
        return
    if row.role == Role.EXPORT:
        if not row.is_readable:
            log_file_denial(actor, str(row.pk), reason="file_not_ready")
            raise PermissionDenied("That file is not available.")
        # Export images may serve thumb/card variants; non-images still preview
        # as the original when ready.
        return
    log_file_denial(actor, str(row.pk), reason="not_previewable")
    raise PermissionDenied("That file is not available.")


def assert_readable_source(actor: User, row: MarketingFile) -> None:
    from apps.marketing.administration import assert_can_author

    assert_can_author(actor, row.asset.owner_office)
    if not has_effective_permission(actor, DOWNLOAD_SOURCES):
        log_file_denial(actor, str(row.pk), reason="missing_download_sources")
        raise PermissionDenied("You cannot download marketing source files.")
    if row.role != Role.SOURCE:
        log_file_denial(actor, str(row.pk), reason="not_source")
        raise PermissionDenied("That file is not available.")
    if not row.is_readable:
        log_file_denial(actor, str(row.pk), reason="file_not_ready")
        raise PermissionDenied("That file is not available.")


def assert_admin_readable(actor: User, row: MarketingFile) -> None:
    assert_can_manage_media(actor, row.asset)
    if not row.is_active:
        raise PermissionDenied("That file is not available.")


# --------------------------------------------------------------------------- #
# Payloads + publish debt
# --------------------------------------------------------------------------- #


def _can_include_sources(actor: User | None) -> bool:
    if actor is None:
        return False
    return has_effective_permission(actor, DOWNLOAD_SOURCES)


def file_payload(
    row: MarketingFile,
    *,
    for_admin: bool = False,
    actor: User | None = None,
) -> dict[str, Any]:
    """camelCase file entry. Consumer payloads never include source URLs."""
    is_image = row.is_image
    url = ""
    if row.role == Role.EXPORT and (row.is_readable or for_admin):
        url = export_url(row)
    elif row.role == Role.PREVIEW and (row.is_readable or for_admin):
        url = preview_url(row)
    elif (
        row.role == Role.SOURCE
        and for_admin
        and _can_include_sources(actor)
        and (row.is_readable or for_admin)
    ):
        url = source_url(row)

    preview = ""
    previewable = row.role in {Role.EXPORT, Role.PREVIEW} and (
        row.is_readable or for_admin
    )
    if previewable:
        preview = preview_url(row)

    variants: dict[str, str] = {}
    if row.role == Role.EXPORT and row.variants:
        for label in row.variants:
            variants[label] = f"{preview_url(row)}?variant={label}"

    payload: dict[str, Any] = {
        "id": row.pk,
        "role": row.role,
        "displayName": row.display_name,
        "mediaType": row.media_type,
        "byteSize": row.byte_size,
        "width": row.width,
        "height": row.height,
        "isImage": is_image,
        "url": url,
        "previewUrl": preview,
        "variants": variants,
        "isReadable": row.is_readable,
    }
    if for_admin:
        payload["processingState"] = row.processing_state
        payload["processingNote"] = row.processing_note
        payload["isActive"] = row.is_active
        payload["checksum"] = row.checksum
        payload["sortOrder"] = row.sort_order
    return payload


def readable_files(asset: MarketingAsset, *, role: str | None = None):
    qs = MarketingFile.objects.filter(asset=asset).readable()
    if role is not None:
        qs = qs.filter(role=role)
    return list(qs.order_by("role", "sort_order", "pk"))


def export_files_payload(asset: MarketingAsset) -> list[dict]:
    return [file_payload(item) for item in readable_files(asset, role=Role.EXPORT)]


def admin_files_payload(
    asset: MarketingAsset, *, actor: User | None = None
) -> dict[str, Any]:
    rows = list(
        MarketingFile.objects.filter(asset=asset, is_active=True).order_by(
            "role", "sort_order", "pk"
        )
    )
    include_sources = _can_include_sources(actor)
    return {
        "exports": [
            file_payload(row, for_admin=True, actor=actor)
            for row in rows
            if row.role == Role.EXPORT
        ],
        "sources": [
            file_payload(row, for_admin=True, actor=actor)
            for row in rows
            if row.role == Role.SOURCE and include_sources
        ]
        if include_sources
        else [],
        "previews": [
            file_payload(row, for_admin=True, actor=actor)
            for row in rows
            if row.role == Role.PREVIEW
        ],
    }


def unprocessed_export_files(asset: MarketingAsset) -> list[MarketingFile]:
    return list(
        MarketingFile.objects.filter(
            asset=asset, is_active=True, role=Role.EXPORT
        ).exclude(processing_state=State.READY)
    )


def media_publish_debt(asset: MarketingAsset) -> list[tuple[str, Any]]:
    """Publish refuses pending/quarantined/failed *export* files only.

    Source files may still be processing — they are not a publish gate.
    """
    if asset.pk is None:
        return []
    blocked = unprocessed_export_files(asset)
    if not blocked:
        return []
    bad = [
        row
        for row in blocked
        if row.processing_state in {State.QUARANTINED, State.FAILED}
    ]
    if bad:
        names = ", ".join(row.display_name for row in bad[:3])
        return [
            (
                "files",
                _(f"Remove or replace the export files that failed checks: {names}."),
            )
        ]
    return [("files", _("Export files are still being processed. Try again shortly."))]


def allowed_matrix_payload() -> dict[str, Any]:
    export_ext = sorted(EXPORT_ALLOWED_MEDIA.keys())
    source_ext = sorted(SOURCE_ALLOWED_MEDIA.keys())
    return {
        "export": {
            "extensions": export_ext,
            "maxBytes": max(rule.max_bytes for rule in EXPORT_ALLOWED_MEDIA.values()),
            "maxCount": MAX_EXPORT_FILES,
        },
        "source": {
            "extensions": source_ext,
            "maxBytes": max(rule.max_bytes for rule in SOURCE_ALLOWED_MEDIA.values()),
            "maxCount": MAX_SOURCE_FILES,
        },
    }


__all__ = [
    "DOWNLOAD_SOURCES",
    "admin_files_payload",
    "allowed_matrix_payload",
    "assert_admin_readable",
    "assert_can_manage_media",
    "assert_can_mutate_media",
    "assert_readable_export",
    "assert_readable_preview",
    "assert_readable_source",
    "attach_file",
    "clone_files_to",
    "export_files_payload",
    "export_url",
    "file_payload",
    "log_file_denial",
    "media_publish_debt",
    "preview_url",
    "readable_files",
    "remove_file",
    "reorder_files",
    "replace_file",
    "resolve_variant_key",
    "source_url",
    "stream_file",
    "unprocessed_export_files",
]
