"""Attach, inspect, and serve document files."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.documents.media import (
    MAX_DOCUMENT_FILES,
    inspect_document_upload,
)
from apps.documents.models import DocumentFile, DocumentVersion
from apps.user.models import User

State = DocumentFile.ProcessingState

MANAGE_PERMISSION = "web.manage_documents"


def assert_can_manage_media(actor: User, version: DocumentVersion) -> None:
    from apps.documents.administration import assert_can_author

    assert_can_author(actor, version.owner_office)


def assert_can_mutate_media(actor: User, version: DocumentVersion) -> None:
    assert_can_manage_media(actor, version)
    if version.status in DocumentVersion.IMMUTABLE_STATUSES:
        raise ValidationError(
            {
                "file": _(
                    "Published documents cannot change files in place. "
                    "Create a new version first."
                )
            }
        )


def _target(row: DocumentFile) -> AuditTarget:
    return AuditTarget(
        target_type=DocumentFile._meta.label_lower,
        target_id=str(row.pk or ""),
        target_label=row.display_name,
    )


def _snapshot(row: DocumentFile) -> dict[str, Any]:
    return {
        "display_name": row.display_name,
        "media_type": row.media_type,
        "byte_size": row.byte_size,
        "checksum": row.checksum,
        "processing_state": row.processing_state,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
    }


def _next_sort_order(version: DocumentVersion) -> int:
    existing = (
        DocumentFile.objects.filter(document_version=version, is_active=True)
        .order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
    )
    return 0 if existing is None else existing + 1


def _assert_room(version: DocumentVersion) -> None:
    count = DocumentFile.objects.filter(
        document_version=version, is_active=True
    ).count()
    if count >= MAX_DOCUMENT_FILES:
        raise ValidationError(
            {"file": _(f"A document can carry at most {MAX_DOCUMENT_FILES} files.")}
        )


@transaction.atomic
def upload_document(
    actor: User,
    version: DocumentVersion,
    uploaded,
) -> DocumentFile:
    assert_can_mutate_media(actor, version)
    inspected, data = inspect_document_upload(uploaded)
    _assert_room(version)
    sort_order = _next_sort_order(version)

    row = DocumentFile(
        document_version=version,
        display_name=inspected.display_name,
        media_type=inspected.media_type,
        byte_size=inspected.byte_size,
        checksum=inspected.checksum,
        processing_state=State.READY,
        sort_order=sort_order,
        uploaded_by=actor,
    )
    row.file.save(inspected.display_name, ContentFile(data), save=False)
    row.full_clean(exclude={"uploaded_by"})
    row.save()

    log_event(
        "document.file_attached",
        actor=actor_from_user(actor),
        target=_target(row),
        after=_snapshot(row),
        metadata={"document_version_id": version.pk},
    )
    return row


def document_url(row: DocumentFile) -> str:
    return reverse("document_file", args=[row.pk])


def stream_file(request, row: DocumentFile, *, as_attachment: bool = True):
    storage = row.file.storage
    key = row.file.name
    if not key or not storage.exists(key):
        raise Http404("That file is no longer stored.")
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
        "security.documents.file_denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=DocumentFile._meta.label_lower, target_id=str(file_id)
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def assert_readable_document(actor: User, row: DocumentFile) -> None:
    from apps.documents.services import is_current_for

    if not is_current_for(actor, row.document_version):
        log_file_denial(actor, str(row.pk), reason="not_current_or_out_of_scope")
        raise Http404("No document matches that id.")
    if not row.is_readable:
        log_file_denial(actor, str(row.pk), reason="file_not_ready")
        raise Http404("No document matches that id.")


def file_payload(row: DocumentFile) -> dict[str, Any]:
    url = document_url(row) if row.is_readable else ""
    return {
        "id": row.pk,
        "displayName": row.display_name,
        "mediaType": row.media_type,
        "byteSize": row.byte_size,
        "checksum": row.checksum,
        "url": url,
        "isReadable": row.is_readable,
    }


def readable_files(version: DocumentVersion):
    cache = getattr(version, "_prefetched_objects_cache", {})
    cached = cache.get("files")
    if cached is not None:
        return [row for row in cached if row.is_readable]
    return list(
        DocumentFile.objects.filter(document_version=version)
        .readable()
        .order_by("sort_order", "pk")
    )


def document_files_payload(version: DocumentVersion) -> list[dict]:
    return [file_payload(item) for item in readable_files(version)]


def media_publish_debt(version: DocumentVersion) -> list[tuple[str, Any]]:
    if version.pk is None:
        return []
    ready = DocumentFile.objects.filter(
        document_version=version,
        is_active=True,
        processing_state=State.READY,
    ).exists()
    if not ready:
        return [
            (
                "files",
                _("Upload at least one ready file before publishing."),
            )
        ]
    blocked = list(
        DocumentFile.objects.filter(document_version=version, is_active=True).exclude(
            processing_state=State.READY
        )
    )
    if not blocked:
        return []
    names = ", ".join(row.display_name for row in blocked[:3])
    return [
        (
            "files",
            _(f"Remove or replace the files that failed checks: {names}."),
        )
    ]


def admin_file_url(row: DocumentFile) -> str:
    return reverse("document_admin_file", args=[row.pk])


def admin_file_payload(row: DocumentFile) -> dict[str, Any]:
    url = admin_file_url(row) if row.is_readable else ""
    return {
        "id": row.pk,
        "displayName": row.display_name,
        "mediaType": row.media_type,
        "byteSize": row.byte_size,
        "checksum": row.checksum,
        "url": url,
        "isReadable": row.is_readable,
        "processingState": row.processing_state,
        "isActive": row.is_active,
        "sortOrder": row.sort_order,
    }


def admin_files_payload(
    version: DocumentVersion, *, actor: User | None = None
) -> list[dict[str, Any]]:
    del actor
    rows = DocumentFile.objects.filter(
        document_version=version, is_active=True
    ).order_by("sort_order", "pk")
    return [admin_file_payload(row) for row in rows]


def allowed_matrix_payload() -> dict[str, Any]:
    from apps.documents.media import DOCUMENT_ALLOWED_MEDIA, MAX_DOCUMENT_FILES

    return {
        "document": {
            "extensions": sorted(DOCUMENT_ALLOWED_MEDIA.keys()),
            "maxBytes": max(rule.max_bytes for rule in DOCUMENT_ALLOWED_MEDIA.values()),
            "maxCount": MAX_DOCUMENT_FILES,
        }
    }


def assert_admin_readable(actor: User, row: DocumentFile) -> None:
    assert_can_manage_media(actor, row.document_version)
    if not row.is_readable:
        log_file_denial(actor, str(row.pk), reason="file_not_ready")
        raise Http404("No document matches that id.")


def _deactivate_file(actor: User, row: DocumentFile, *, reason: str) -> None:
    before = _snapshot(row)
    row.is_active = False
    row.save(update_fields=["is_active", "updated_at"])
    log_event(
        "document.file_retired",
        actor=actor_from_user(actor),
        target=_target(row),
        before=before,
        after=_snapshot(row),
        reason=reason,
        metadata={"document_version_id": row.document_version.pk},
    )


@transaction.atomic
def remove_file(actor: User, row: DocumentFile) -> None:
    assert_can_mutate_media(actor, row.document_version)
    _deactivate_file(actor, row, reason="removed_by_admin")


@transaction.atomic
def replace_file(actor: User, row: DocumentFile, uploaded) -> DocumentFile:
    assert_can_mutate_media(actor, row.document_version)
    inspected, data = inspect_document_upload(uploaded)
    before = _snapshot(row)
    row.display_name = inspected.display_name
    row.media_type = inspected.media_type
    row.byte_size = inspected.byte_size
    row.checksum = inspected.checksum
    row.processing_state = State.READY
    row.processing_note = ""
    row.file.save(inspected.display_name, ContentFile(data), save=False)
    row.full_clean(exclude={"uploaded_by"})
    row.save()
    log_event(
        "document.file_replaced",
        actor=actor_from_user(actor),
        target=_target(row),
        before=before,
        after=_snapshot(row),
        metadata={"document_version_id": row.document_version.pk},
    )
    return row


@transaction.atomic
def reorder_files(
    actor: User, version: DocumentVersion, ordered_ids: list[int]
) -> None:
    assert_can_mutate_media(actor, version)
    rows = {
        item.pk: item
        for item in DocumentFile.objects.filter(
            document_version=version, is_active=True
        )
    }
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


def clone_files_to(
    actor: User, source: DocumentVersion, target: DocumentVersion
) -> None:
    for row in DocumentFile.objects.filter(
        document_version=source, is_active=True
    ).order_by("sort_order", "pk"):
        storage = row.file.storage
        if not row.file or not storage.exists(row.file.name):
            continue
        with storage.open(row.file.name, "rb") as handle:
            data = handle.read()
        clone = DocumentFile(
            document_version=target,
            display_name=row.display_name,
            media_type=row.media_type,
            byte_size=len(data),
            checksum=row.checksum,
            processing_state=State.READY,
            sort_order=row.sort_order,
            uploaded_by=actor,
        )
        clone.file.save(row.display_name, ContentFile(data), save=False)
        clone.full_clean(exclude={"uploaded_by"})
        clone.save()
