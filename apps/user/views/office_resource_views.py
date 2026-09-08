"""Agent-facing office resources — scoped, searchable, protected downloads."""

from __future__ import annotations

import mimetypes
from typing import cast

from django.http import FileResponse, Http404, HttpRequest
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.web.authorization import enforce_policy

from ..models import OfficeResource, User
from ..services.office_resources import (
    ResourceFilters,
    effective_resources,
    office_resources_page_payload,
)

__all__ = ["office_resources", "office_resource_download"]


@enforce_policy("office_resources")
@require_GET
@inertia("OfficeResources")
def office_resources(request: HttpRequest):
    """Effective resources for the signed-in user's primary office scope."""
    actor = cast(User, request.user)
    filters = ResourceFilters.from_params(request.GET)
    return office_resources_page_payload(actor, filters=filters)


@enforce_policy("office_resource_download")
@require_GET
def office_resource_download(request: HttpRequest, slug: str) -> FileResponse:
    """Stream a resource file after re-checking page visibility.

    The slug is resolved against the actor's own effective resources — never
    against a client-supplied office or resource id.
    """
    actor = cast(User, request.user)
    for resource in effective_resources(actor):
        if (
            resource.slug == slug
            and resource.resource_type == OfficeResource.ResourceType.FILE
            and resource.file
        ):
            break
    else:
        raise Http404

    content_type, _ = mimetypes.guess_type(resource.original_file_name)
    log_event(
        "office_resource.downloaded",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=OfficeResource._meta.label_lower,
            target_id=str(resource.pk),
            target_label=f"{resource.owner_office.name} / {resource.title}",
        ),
        metadata={"fileName": resource.original_file_name},
    )
    response = FileResponse(
        resource.file.open("rb"),
        as_attachment=True,
        filename=resource.original_file_name or f"{resource.slug}",
        content_type=content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    return response
