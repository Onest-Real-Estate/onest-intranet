"""Attach, remove, and serve policy files."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.announcements.media import checksum_of
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.compliance.media import (
    DOCUMENT_ALLOWED_MEDIA,
    MAX_DOCUMENT_FILES,
    MAX_SOURCE_FILES,
    SOURCE_ALLOWED_MEDIA,
    inspect_policy_upload,
)
from apps.compliance.models import PolicyFile, PolicyVersion
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

State = PolicyFile.ProcessingState
Role = PolicyFile.Role

MANAGE_PERMISSION = "web.manage_policies"


def assert_can_manage_media(actor: User, version: PolicyVersion) -> None:
    from apps.compliance.administration import assert_can_author

    assert_can_author(actor, version.owner_office)


def assert_can_mutate_media(actor: User, version: PolicyVersion) -> None:
    assert_can_manage_media(actor, version)
    if version.status in PolicyVersion.IMMUTABLE_STATUSES:
        raise ValidationError(
            {
                "file": _(
                    "Published policies cannot change files in place. "
                    "Duplicate as a new version first."
                )
            }
        )


def _target(row: PolicyFile) -> AuditTarget:
    return AuditTarget(
        target_type=PolicyFile._meta.label_lower,
        target_id=str(row.pk or ""),
        target_label=row.display_name,
    )


def _snapshot(row: PolicyFile) -> dict[str, Any]:
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


def _next_sort_order(version: PolicyVersion, *, role: str) -> int:
    existing = (
        PolicyFile.objects.filter(policy_version=version, role=role, is_active=True)
        .order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
    )
    return 0 if existing is None else existing + 1


def _assert_role_room(version: PolicyVersion, *, role: str) -> None:
    if role == Role.DOCUMENT:
        limit = MAX_DOCUMENT_FILES
        label = "document files"
    elif role == Role.SOURCE:
        limit = MAX_SOURCE_FILES
        label = "source files"
    else:
        raise ValidationError({"file": _("That file role cannot be uploaded.")})
    count = PolicyFile.objects.filter(
        policy_version=version, role=role, is_active=True
    ).count()
    if count >= limit:
        raise ValidationError(
            {"file": _(f"A policy can carry at most {limit} {label}.")}
        )


@transaction.atomic
def upload_document(
    actor: User,
    version: PolicyVersion,
    uploaded,
    *,
    role: str = Role.DOCUMENT,
) -> PolicyFile:
    assert_can_mutate_media(actor, version)
    if role not in {Role.DOCUMENT, Role.SOURCE}:
        raise ValidationError({"file": _("Unknown file role.")})

    inspected, data = inspect_policy_upload(uploaded, role=role)
    _assert_role_room(version, role=role)
    sort_order = _next_sort_order(version, role=role)

    row = PolicyFile(
        policy_version=version,
        role=role,
        display_name=inspected.display_name,
        media_type=inspected.media_type,
        byte_size=inspected.byte_size,
        checksum=inspected.checksum,
        # Inspection already verified bytes; mark ready immediately.
        processing_state=State.READY,
        sort_order=sort_order,
        uploaded_by=actor,
    )
    row.file.save(inspected.display_name, ContentFile(data), save=False)
    row.full_clean(exclude={"uploaded_by"})
    row.save()

    log_event(
        "compliance.file_attached",
        actor=actor_from_user(actor),
        target=_target(row),
        after=_snapshot(row),
        metadata={"policy_version_id": version.pk},
    )
    return row


def _delete_stored_objects(row: PolicyFile) -> None:
    storage = row.file.storage
    if row.file:
        storage.delete(row.file.name)


def _deactivate_or_delete(actor: User, row: PolicyFile, *, reason: str) -> None:
    before = _snapshot(row)
    published = row.policy_version.status in PolicyVersion.IMMUTABLE_STATUSES
    if published:
        row.is_active = False
        row.save(update_fields=["is_active", "updated_at"])
        action = "compliance.file_retired"
        after = _snapshot(row)
    else:
        _delete_stored_objects(row)
        row.delete()
        action = "compliance.file_deleted"
        after = {}
    log_event(
        action,
        actor=actor_from_user(actor),
        target=_target(row),
        before=before,
        after=after,
        reason=reason,
        metadata={"policy_version_id": row.policy_version.pk},
    )


@transaction.atomic
def remove_file(actor: User, row: PolicyFile) -> None:
    assert_can_mutate_media(actor, row.policy_version)
    _deactivate_or_delete(actor, row, reason="removed_by_admin")


def clone_files_to(actor: User, source: PolicyVersion, target: PolicyVersion) -> None:
    for row in PolicyFile.objects.filter(
        policy_version=source, is_active=True
    ).order_by("role", "sort_order", "pk"):
        storage = row.file.storage
        if not row.file or not storage.exists(row.file.name):
            continue
        with storage.open(row.file.name, "rb") as handle:
            data = handle.read()
        clone = PolicyFile(
            policy_version=target,
            role=row.role,
            display_name=row.display_name,
            media_type=row.media_type,
            byte_size=len(data),
            checksum=row.checksum or checksum_of(data),
            processing_state=State.READY,
            sort_order=row.sort_order,
            uploaded_by=actor,
        )
        clone.file.save(row.display_name, ContentFile(data), save=False)
        clone.full_clean(exclude={"uploaded_by"})
        clone.save()


def document_url(row: PolicyFile) -> str:
    return reverse("policy_document_file", args=[row.pk])


def stream_file(request, row: PolicyFile, *, as_attachment: bool = True):
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
        "security.compliance.file_denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=PolicyFile._meta.label_lower, target_id=str(file_id)
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def assert_readable_document(actor: User, row: PolicyFile) -> None:
    from apps.compliance.audience import assert_visible

    assert_visible(actor, row.policy_version, reason="file_out_of_audience")
    if row.role != Role.DOCUMENT:
        log_file_denial(actor, str(row.pk), reason="not_document")
        raise PermissionDenied("That file is not available.")
    if not row.is_readable:
        log_file_denial(actor, str(row.pk), reason="file_not_ready")
        raise PermissionDenied("That file is not available.")


def assert_readable_source(actor: User, row: PolicyFile) -> None:
    from apps.compliance.administration import assert_can_author

    assert_can_author(actor, row.policy_version.owner_office)
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        log_file_denial(actor, str(row.pk), reason="missing_manage")
        raise PermissionDenied("You cannot download policy source files.")
    if row.role != Role.SOURCE:
        log_file_denial(actor, str(row.pk), reason="not_source")
        raise PermissionDenied("That file is not available.")
    if not row.is_readable:
        log_file_denial(actor, str(row.pk), reason="file_not_ready")
        raise PermissionDenied("That file is not available.")


def file_payload(row: PolicyFile, *, for_admin: bool = False) -> dict[str, Any]:
    url = ""
    if (
        row.role == Role.DOCUMENT
        and (row.is_readable or for_admin)
        or row.role == Role.SOURCE
        and for_admin
        and (row.is_readable or for_admin)
    ):
        url = document_url(row)
    payload: dict[str, Any] = {
        "id": row.pk,
        "role": row.role,
        "displayName": row.display_name,
        "mediaType": row.media_type,
        "byteSize": row.byte_size,
        "url": url,
        "isReadable": row.is_readable,
    }
    if for_admin:
        payload["processingState"] = row.processing_state
        payload["processingNote"] = row.processing_note
        payload["isActive"] = row.is_active
        payload["checksum"] = row.checksum
        payload["sortOrder"] = row.sort_order
    return payload


def readable_files(version: PolicyVersion, *, role: str | None = None):
    qs = PolicyFile.objects.filter(policy_version=version).readable()
    if role is not None:
        qs = qs.filter(role=role)
    return list(qs.order_by("role", "sort_order", "pk"))


def document_files_payload(version: PolicyVersion) -> list[dict]:
    return [file_payload(item) for item in readable_files(version, role=Role.DOCUMENT)]


def admin_files_payload(version: PolicyVersion) -> dict[str, Any]:
    rows = list(
        PolicyFile.objects.filter(policy_version=version, is_active=True).order_by(
            "role", "sort_order", "pk"
        )
    )
    return {
        "documents": [
            file_payload(row, for_admin=True)
            for row in rows
            if row.role == Role.DOCUMENT
        ],
        "sources": [
            file_payload(row, for_admin=True) for row in rows if row.role == Role.SOURCE
        ],
    }


def seal_content_checksum(version: PolicyVersion) -> str:
    """Seal body + ready document file checksums into one content digest."""
    parts = [version.body or ""]
    for row in readable_files(version, role=Role.DOCUMENT):
        parts.append(row.checksum or "")
    return checksum_of("\n".join(parts).encode("utf-8"))


def media_publish_debt(version: PolicyVersion) -> list[tuple[str, Any]]:
    if version.pk is None:
        return []
    blocked = list(
        PolicyFile.objects.filter(
            policy_version=version, is_active=True, role=Role.DOCUMENT
        ).exclude(processing_state=State.READY)
    )
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
                _(f"Remove or replace the document files that failed checks: {names}."),
            )
        ]
    return [
        ("files", _("Document files are still being processed. Try again shortly."))
    ]


def allowed_matrix_payload() -> dict[str, Any]:
    return {
        "document": {
            "extensions": sorted(DOCUMENT_ALLOWED_MEDIA.keys()),
            "maxBytes": max(rule.max_bytes for rule in DOCUMENT_ALLOWED_MEDIA.values()),
            "maxCount": MAX_DOCUMENT_FILES,
        },
        "source": {
            "extensions": sorted(SOURCE_ALLOWED_MEDIA.keys()),
            "maxBytes": max(rule.max_bytes for rule in SOURCE_ALLOWED_MEDIA.values()),
            "maxCount": MAX_SOURCE_FILES,
        },
    }
