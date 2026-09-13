"""Marketing resource library surfaces and protected file downloads."""

from __future__ import annotations

from typing import cast

from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.marketing.media_service import (
    assert_readable_export,
    assert_readable_preview,
    assert_readable_source,
    stream_file,
)
from apps.marketing.models import MarketingFile
from apps.marketing.services import (
    asset_type_filter_options,
    build_library,
    category_filter_options,
    detail_payload,
    library_summary,
    resolve_consumer_asset,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


@enforce_policy("marketing_library")
@require_GET
@inertia("MarketingResources")
def marketing_resources(request: HttpRequest):
    actor = _actor(request)
    library = build_library(actor, params=request.GET, page=_page_param(request))
    selected_category = library["filters"]["category"]
    return {
        "library": library,
        "summary": library_summary(actor),
        "filterOptions": {
            "categories": category_filter_options(include_codes=(selected_category,)),
            "assetTypes": asset_type_filter_options(),
        },
    }


@enforce_policy("marketing_detail")
@require_GET
@inertia("MarketingResourceDetail")
def marketing_resource_detail(request: HttpRequest, asset_id: int):
    actor = _actor(request)
    outcome, asset = resolve_consumer_asset(actor, asset_id)
    if outcome == "redirect":
        return redirect("marketing_resource_detail", asset_id=asset.pk)
    return {
        "asset": detail_payload(asset),
    }


@enforce_policy("marketing_export")
@require_GET
def marketing_resource_export(request: HttpRequest, file_id: int):
    actor = _actor(request)
    row = get_object_or_404(
        MarketingFile.objects.select_related("asset", "asset__owner_office"),
        pk=file_id,
    )
    assert_readable_export(actor, row)
    return stream_file(request, row, as_attachment=True)


@enforce_policy("marketing_preview")
@require_GET
def marketing_resource_preview(request: HttpRequest, file_id: int):
    actor = _actor(request)
    row = get_object_or_404(
        MarketingFile.objects.select_related("asset", "asset__owner_office"),
        pk=file_id,
    )
    assert_readable_preview(actor, row)
    variant = (request.GET.get("variant") or "").strip()
    variants = row.variants or {}
    needs_thumb = (variant and variant not in variants) or (
        not variant and row.role == MarketingFile.Role.EXPORT
    )
    if needs_thumb:
        variant = "thumb" if "thumb" in variants else ""
    return stream_file(request, row, variant=variant, as_attachment=False)


@enforce_policy("marketing_source")
@require_GET
def marketing_resource_source(request: HttpRequest, file_id: int):
    actor = _actor(request)
    row = get_object_or_404(
        MarketingFile.objects.select_related("asset", "asset__owner_office"),
        pk=file_id,
    )
    assert_readable_source(actor, row)
    return stream_file(request, row, as_attachment=True)
