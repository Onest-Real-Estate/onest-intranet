"""Attach, replace, reorder, remove, and serve training media."""

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
from apps.training.media import MAX_ATTACHMENTS, inspect_training_upload
from apps.training.models import TrainingContent, TrainingMedia
from apps.user.models import User

State = TrainingMedia.ProcessingState
Role = TrainingMedia.Role


# --------------------------------------------------------------------------- #
# Authority
# --------------------------------------------------------------------------- #


def assert_can_manage_media(actor: User, content: TrainingContent) -> None:
    """Open the media manager for content in the actor's grant."""
    from apps.training.administration import assert_can_author

    assert_can_author(actor, content.owner_office)


def assert_can_mutate_media(actor: User, content: TrainingContent) -> None:
    """Attach/replace/remove files — drafts only."""
    assert_can_manage_media(actor, content)
    if content.status != TrainingContent.Status.DRAFT:
        raise ValidationError(
            {
                "file": _(
                    "Published training cannot change files in place. "
                    "Duplicate as a new version first."
                )
            }
        )


def _target(media: TrainingMedia) -> AuditTarget:
    return AuditTarget(
        target_type=TrainingMedia._meta.label_lower,
        target_id=str(media.pk or ""),
        target_label=media.display_name,
    )


def _snapshot(media: TrainingMedia) -> dict[str, Any]:
    return {
        "display_name": media.display_name,
        "role": media.role,
        "media_type": media.media_type,
        "byte_size": media.byte_size,
        "checksum": media.checksum,
        "processing_state": media.processing_state,
        "is_active": media.is_active,
        "sort_order": media.sort_order,
    }


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def _next_sort_order(content: TrainingContent) -> int:
    existing = (
        TrainingMedia.objects.filter(
            content=content, role=Role.ATTACHMENT, is_active=True
        )
        .order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
    )
    return 0 if existing is None else existing + 1


def _assert_attachment_room(content: TrainingContent) -> None:
    count = TrainingMedia.objects.filter(
        content=content, role=Role.ATTACHMENT, is_active=True
    ).count()
    if count >= MAX_ATTACHMENTS:
        raise ValidationError(
            {"file": _(f"Training can carry at most {MAX_ATTACHMENTS} attachments.")}
        )


@transaction.atomic
def attach_media(
    actor: User,
    content: TrainingContent,
    uploaded,
    *,
    role: str = Role.ATTACHMENT,
) -> TrainingMedia:
    assert_can_mutate_media(actor, content)
    inspected, data = inspect_training_upload(uploaded, primary=role == Role.PRIMARY)

    if role == Role.PRIMARY:
        _retire_current_primary(actor, content)
        sort_order = 0
    else:
        _assert_attachment_room(content)
        sort_order = _next_sort_order(content)

    media = TrainingMedia(
        content=content,
        role=role,
        display_name=inspected.display_name,
        media_type=inspected.media_type,
        byte_size=inspected.byte_size,
        checksum=inspected.checksum,
        processing_state=State.PENDING,
        sort_order=sort_order,
        uploaded_by=actor,
    )
    media.file.save(inspected.display_name, ContentFile(data), save=False)
    media.full_clean(exclude={"uploaded_by"})
    media.save()

    log_event(
        "training.media_attached",
        actor=actor_from_user(actor),
        target=_target(media),
        after=_snapshot(media),
        metadata={"content_id": content.pk},
    )
    transaction.on_commit(lambda: _queue_processing(media.pk))
    return media


def _queue_processing(media_id: int) -> None:
    from apps.training.tasks import process_training_media

    process_training_media.delay(media_id)


def _retire_current_primary(actor: User, content: TrainingContent) -> None:
    current = (
        TrainingMedia.objects.filter(content=content, role=Role.PRIMARY, is_active=True)
        .select_for_update()
        .first()
    )
    if current is None:
        return
    _deactivate_or_delete(actor, current, reason="replaced")


def _deactivate_or_delete(actor: User, media: TrainingMedia, *, reason: str) -> None:
    before = _snapshot(media)
    published = media.content.status != TrainingContent.Status.DRAFT
    if published:
        media.is_active = False
        media.save(update_fields=["is_active", "updated_at"])
        action = "training.media_retired"
        after = _snapshot(media)
    else:
        _delete_stored_objects(media)
        media.delete()
        action = "training.media_deleted"
        after = {}
    log_event(
        action,
        actor=actor_from_user(actor),
        target=_target(media),
        before=before,
        after=after,
        reason=reason,
        metadata={"content_id": media.content.pk},
    )


def _delete_stored_objects(media: TrainingMedia) -> None:
    storage = media.file.storage
    if media.file:
        storage.delete(media.file.name)


@transaction.atomic
def replace_media(actor: User, media: TrainingMedia, uploaded) -> TrainingMedia:
    assert_can_mutate_media(actor, media.content)
    content = media.content
    role = media.role
    if role == Role.PRIMARY:
        return attach_media(actor, content, uploaded, role=Role.PRIMARY)
    order = media.sort_order
    _deactivate_or_delete(actor, media, reason="replaced")
    replacement = attach_media(actor, content, uploaded, role=Role.ATTACHMENT)
    replacement.sort_order = order
    replacement.save(update_fields=["sort_order", "updated_at"])
    return replacement


@transaction.atomic
def remove_media(actor: User, media: TrainingMedia) -> None:
    assert_can_mutate_media(actor, media.content)
    _deactivate_or_delete(actor, media, reason="removed_by_admin")


@transaction.atomic
def reorder_attachments(
    actor: User, content: TrainingContent, ordered_ids: list[int]
) -> None:
    assert_can_mutate_media(actor, content)
    rows = {
        row.pk: row
        for row in TrainingMedia.objects.filter(
            content=content, role=Role.ATTACHMENT, is_active=True
        )
    }
    before = [row.pk for row in sorted(rows.values(), key=lambda r: r.sort_order)]

    seen: list[int] = []
    for candidate in ordered_ids:
        if candidate in rows and candidate not in seen:
            seen.append(candidate)
    seen.extend(pk for pk in rows if pk not in seen)

    for index, pk in enumerate(seen):
        row = rows[pk]
        if row.sort_order != index:
            row.sort_order = index
            row.save(update_fields=["sort_order", "updated_at"])

    log_event(
        "training.media_reordered",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=TrainingContent._meta.label_lower,
            target_id=str(content.pk),
            target_label=content.slug,
        ),
        before={"order": before},
        after={"order": seen},
    )


def clone_media_to(
    actor: User, source: TrainingContent, target: TrainingContent
) -> None:
    """Copy active media bytes onto a new version draft."""
    for media in TrainingMedia.objects.filter(content=source, is_active=True).order_by(
        "role", "sort_order", "pk"
    ):
        storage = media.file.storage
        if not media.file or not storage.exists(media.file.name):
            continue
        with storage.open(media.file.name, "rb") as handle:
            data = handle.read()
        clone = TrainingMedia(
            content=target,
            role=media.role,
            display_name=media.display_name,
            media_type=media.media_type,
            byte_size=len(data),
            checksum=media.checksum,
            processing_state=State.PENDING,
            sort_order=media.sort_order,
            uploaded_by=actor,
        )
        clone.file.save(media.display_name, ContentFile(data), save=False)
        clone.full_clean(exclude={"uploaded_by"})
        clone.save()
        transaction.on_commit(lambda pk=clone.pk: _queue_processing(pk))


# --------------------------------------------------------------------------- #
# Serving
# --------------------------------------------------------------------------- #


def media_url(media: TrainingMedia) -> str:
    return reverse("training_media", args=[media.pk])


def stream_media(request, media: TrainingMedia):
    storage = media.file.storage
    key = media.file.name
    if not key or not storage.exists(key):
        raise Http404("That file is no longer stored.")
    response = FileResponse(
        storage.open(key, "rb"),
        as_attachment=not media.media_type.startswith("video/"),
        filename=media.display_name,
        content_type=media.media_type,
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


def log_media_denial(actor: User, media_id: str, *, reason: str) -> None:
    log_event(
        "security.training.media_denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=TrainingMedia._meta.label_lower, target_id=str(media_id)
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def assert_readable(actor: User, media: TrainingMedia) -> None:
    from apps.training.audience import assert_visible

    assert_visible(actor, media.content, reason="media_out_of_audience")
    if not media.is_readable:
        log_media_denial(actor, str(media.pk), reason="media_not_ready")
        raise PermissionDenied("That file is not available.")


def assert_admin_readable(actor: User, media: TrainingMedia) -> None:
    """Administrators may inspect non-ready uploads on drafts they manage."""
    from apps.training.administration import assert_can_author

    assert_can_author(actor, media.content.owner_office)
    if not media.is_active:
        raise PermissionDenied("That file is not available.")


# --------------------------------------------------------------------------- #
# Payloads + publish debt
# --------------------------------------------------------------------------- #


def media_payload(media: TrainingMedia, *, for_admin: bool = False) -> dict[str, Any]:
    is_image = media.media_type.startswith("image/")
    payload: dict[str, Any] = {
        "id": media.pk,
        "role": media.role,
        "displayName": media.display_name,
        "mediaType": media.media_type,
        "byteSize": media.byte_size,
        "width": None,
        "height": None,
        "isImage": is_image,
        "url": media_url(media) if media.is_readable or for_admin else "",
        "variants": {},
        "processingState": media.processing_state,
        "isReadable": media.is_readable,
    }
    if for_admin:
        payload["processingNote"] = media.processing_note
        payload["isActive"] = media.is_active
        payload["checksum"] = media.checksum
        payload["sortOrder"] = media.sort_order
    return payload


def readable_media(content: TrainingContent) -> list[TrainingMedia]:
    return list(
        TrainingMedia.objects.filter(content=content)
        .readable()
        .order_by("role", "sort_order", "pk")
    )


def primary_media_payload(content: TrainingContent) -> dict | None:
    primary = next(
        (item for item in readable_media(content) if item.role == Role.PRIMARY),
        None,
    )
    return media_payload(primary) if primary else None


def primary_media_detail_payload(content: TrainingContent) -> dict | None:
    primary = (
        TrainingMedia.objects.filter(content=content, role=Role.PRIMARY, is_active=True)
        .order_by("pk")
        .first()
    )
    if primary is None:
        return None
    return {
        "id": primary.pk,
        "role": primary.role,
        "displayName": primary.display_name,
        "mediaType": primary.media_type,
        "byteSize": primary.byte_size,
        "processingState": primary.processing_state,
        "isReadable": primary.is_readable,
        "url": media_url(primary) if primary.is_readable else "",
    }


def attachments_payload(content: TrainingContent) -> list[dict]:
    return [
        media_payload(item)
        for item in readable_media(content)
        if item.role == Role.ATTACHMENT
    ]


def admin_media_payload(content: TrainingContent) -> dict[str, Any]:
    rows = list(
        TrainingMedia.objects.filter(content=content, is_active=True).order_by(
            "role", "sort_order", "pk"
        )
    )
    primary = next((row for row in rows if row.role == Role.PRIMARY), None)
    attachments = [row for row in rows if row.role == Role.ATTACHMENT]
    return {
        "primary": media_payload(primary, for_admin=True) if primary else None,
        "attachments": [media_payload(row, for_admin=True) for row in attachments],
    }


def unprocessed_media(content: TrainingContent) -> list[TrainingMedia]:
    return list(
        TrainingMedia.objects.filter(content=content, is_active=True).exclude(
            processing_state=State.READY
        )
    )


def media_publish_debt(content: TrainingContent) -> list[tuple[str, Any]]:
    if content.pk is None:
        return []
    blocked = unprocessed_media(content)
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
                "media",
                _(f"Remove or replace the files that failed checks: {names}."),
            )
        ]
    return [("media", _("Files are still being processed. Try again shortly."))]


__all__ = [
    "admin_media_payload",
    "assert_admin_readable",
    "assert_can_manage_media",
    "assert_can_mutate_media",
    "assert_readable",
    "attach_media",
    "attachments_payload",
    "clone_media_to",
    "log_media_denial",
    "media_payload",
    "media_publish_debt",
    "media_url",
    "primary_media_detail_payload",
    "primary_media_payload",
    "readable_media",
    "remove_media",
    "reorder_attachments",
    "replace_media",
    "stream_media",
    "unprocessed_media",
]
