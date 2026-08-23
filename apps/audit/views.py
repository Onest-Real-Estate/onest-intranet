"""HTTP surfaces for the activity timeline projection."""

from __future__ import annotations

from typing import cast

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.audit.activity.access import SUPPORTED_RECORD_TYPES
from apps.audit.activity.projection import (
    ActivityProjectionError,
    project_record_activity,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy


@enforce_policy("activity_timeline")
@require_GET
def activity_timeline(
    request: HttpRequest, record_type: str, record_id: str
) -> JsonResponse:
    """Cursor-paginated activity for one authorized record.

    Always filters to ``(record_type, record_id)``. Cross-record leakage is a
    hard failure, not an empty page that might leak existence.
    """
    if record_type not in SUPPORTED_RECORD_TYPES:
        raise Http404("Unknown activity record type.")

    viewer = cast(User, request.user)
    cursor = request.GET.get("cursor") or None
    limit = request.GET.get("limit")
    try:
        page = project_record_activity(
            viewer,
            record_type,
            record_id,
            cursor=cursor,
            limit=int(limit) if limit is not None else None,
        )
    except ActivityProjectionError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except PermissionDenied:
        raise
    except Http404:
        raise
    return JsonResponse(page.to_payload())
