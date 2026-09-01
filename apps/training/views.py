"""Training library surfaces."""

from __future__ import annotations

from typing import cast

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.training.audience import assert_visible
from apps.training.media_service import assert_readable, stream_media
from apps.training.models import TrainingContent, TrainingMedia
from apps.training.services import (
    build_library,
    category_filter_options,
    completion_filter_options,
    content_type_filter_options,
    detail_payload,
    tool_filter_options,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


@enforce_policy("training_library")
@require_GET
@inertia("TrainingLearning")
def training_learning(request: HttpRequest):
    actor = cast(User, request.user)
    library = build_library(actor, params=request.GET, page=_page_param(request))
    selected_category = library["filters"]["category"]
    return {
        "library": library,
        "filterOptions": {
            "categories": category_filter_options(include_codes=(selected_category,)),
            "contentTypes": content_type_filter_options(),
            "tools": tool_filter_options(),
            "completions": completion_filter_options(),
        },
    }


@enforce_policy("training_detail")
@require_GET
@inertia("TrainingDetail")
def training_detail(request: HttpRequest, content_id: int):
    actor = cast(User, request.user)
    content = get_object_or_404(
        TrainingContent.objects.select_related(
            "category", "owner_office", "embed", "transcription"
        ),
        pk=content_id,
    )
    assert_visible(actor, content, reason="detail_out_of_audience")
    return {"content": detail_payload(content, user=actor)}


@enforce_policy("training_media")
@require_GET
def training_media(request: HttpRequest, media_id: int):
    actor = cast(User, request.user)
    media = get_object_or_404(
        TrainingMedia.objects.select_related("content"),
        pk=media_id,
    )
    assert_readable(actor, media)
    return stream_media(request, media)
