"""Agent Directory HTTP surfaces — list, detail, gated headshot."""

from __future__ import annotations

import mimetypes

from django.http import FileResponse, Http404, HttpRequest
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.user.services.agent_directory import (
    build_agent_directory_detail,
    build_agent_directory_page,
    get_visible_user,
    parse_filters,
    parse_page,
)
from apps.web.authorization import enforce_policy

__all__ = [
    "agent_directory",
    "agent_directory_detail",
    "agent_directory_headshot",
]


@enforce_policy("agent_directory")
@require_GET
@inertia("AgentDirectory")
def agent_directory(request: HttpRequest):
    """Company-wide peer directory with privacy-aware field projection."""
    filters = parse_filters(request.GET)
    return build_agent_directory_page(
        filters=filters,
        page=parse_page(request.GET),
    )


@enforce_policy("agent_directory_detail")
@require_GET
@inertia("AgentDirectoryDetail")
def agent_directory_detail(request: HttpRequest, user_id: int):
    """One directory-visible person; out-of-policy ids are 404."""
    payload = build_agent_directory_detail(user_id)
    if payload is None:
        raise Http404
    return payload


@enforce_policy("agent_directory_headshot")
@require_GET
def agent_directory_headshot(request: HttpRequest, user_id: int) -> FileResponse:
    """Stream a directory-visible headshot after re-checking visibility.

    Never serves photos for inactive, prospective, suspended, or departed
    accounts. Cache is private and short-lived so a revoked visibility change
    is not sticky in shared caches.
    """
    user = get_visible_user(user_id)
    if user is None or not user.headshot:
        raise Http404

    content_type, _ = mimetypes.guess_type(user.headshot.name)
    response = FileResponse(
        user.headshot.open("rb"),
        as_attachment=False,
        filename=user.headshot.name.rsplit("/", 1)[-1],
        content_type=content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, max-age=300"
    return response
