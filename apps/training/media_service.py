"""Read paths for protected training media."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.training.models import TrainingContent, TrainingMedia
from apps.user.models import User

State = TrainingMedia.ProcessingState
Role = TrainingMedia.Role


def media_url(media: TrainingMedia) -> str:
    return reverse("training_media", args=[media.pk])


def media_payload(media: TrainingMedia) -> dict[str, Any]:
    return {
        "id": media.pk,
        "role": media.role,
        "displayName": media.display_name,
        "mediaType": media.media_type,
        "byteSize": media.byte_size,
        "url": media_url(media),
        "processingState": media.processing_state,
        "isReadable": media.is_readable,
    }


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
    """Primary media for detail, including not-yet-readable uploads."""
    primary = (
        TrainingMedia.objects.filter(content=content, role=Role.PRIMARY, is_active=True)
        .order_by("pk")
        .first()
    )
    if primary is None:
        return None
    payload = {
        "id": primary.pk,
        "role": primary.role,
        "displayName": primary.display_name,
        "mediaType": primary.media_type,
        "byteSize": primary.byte_size,
        "processingState": primary.processing_state,
        "isReadable": primary.is_readable,
        "url": media_url(primary) if primary.is_readable else "",
    }
    return payload


def attachments_payload(content: TrainingContent) -> list[dict]:
    return [
        media_payload(item)
        for item in readable_media(content)
        if item.role == Role.ATTACHMENT
    ]


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
