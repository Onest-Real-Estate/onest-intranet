"""Agent-facing office inventory HTTP surface."""

from __future__ import annotations

import mimetypes
from typing import cast
from uuid import UUID

from django.http import FileResponse, Http404, HttpRequest
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.inventory.browser import (
    build_agent_inventory_page,
    build_agent_item_detail,
    parse_agent_filters,
)
from apps.inventory.queries import item_for_agent
from apps.user.models import User
from apps.web.authorization import enforce_policy

__all__ = [
    "office_inventory",
    "office_inventory_item",
    "office_inventory_photo",
]


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


@enforce_policy("office_inventory")
@require_GET
@inertia("OfficeInventory")
def office_inventory(request: HttpRequest):
    """Reservable inventory for the signed-in user's primary office."""
    actor = cast(User, request.user)
    filters = parse_agent_filters(request.GET)
    return build_agent_inventory_page(
        actor,
        filters=filters,
        page=_page_param(request),
    )


@enforce_policy("office_inventory_item")
@require_GET
@inertia("OfficeInventoryItem")
def office_inventory_item(request: HttpRequest, public_id: str):
    """One reservable item within the reader's office scope."""
    actor = cast(User, request.user)
    try:
        item_id = UUID(str(public_id))
    except ValueError as exc:
        raise Http404 from exc
    filters = parse_agent_filters(request.GET)
    payload = build_agent_item_detail(actor, item_id, filters=filters)
    if payload is None:
        raise Http404
    return payload


@enforce_policy("office_inventory_photo")
@require_GET
def office_inventory_photo(request: HttpRequest, public_id: str) -> FileResponse:
    """Stream an agent-visible item photo after re-checking office scope.

    Only photos marked ``photo_is_public`` are served here. Non-public photos
    remain admin-only through the management surface.
    """
    actor = cast(User, request.user)
    try:
        item_id = UUID(str(public_id))
    except ValueError as exc:
        raise Http404 from exc
    item = item_for_agent(actor, public_id=item_id)
    if item is None or not item.photo or not item.photo_is_public:
        raise Http404

    content_type, _ = mimetypes.guess_type(item.photo.name)
    response = FileResponse(
        item.photo.open("rb"),
        as_attachment=False,
        filename=item.photo.name.rsplit("/", 1)[-1],
        content_type=content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, max-age=0, no-store"
    return response
