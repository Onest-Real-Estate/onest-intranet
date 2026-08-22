"""Announcement surfaces. Every one of them asks the same audience predicate.

The feed, the detail page, and the attachment download share
:mod:`apps.announcements.audience`, so a guessed URL is exactly as permissive
as the list the reader was actually shown — which is to say, not at all.
Audience is re-evaluated on each request; nothing here trusts a recipient set
computed when the announcement was published.
"""

from __future__ import annotations

from typing import cast

from django.http import FileResponse, Http404, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.announcements.audience import (
    assert_visible,
    describe_audience,
    search_recipients,
)
from apps.announcements.models import Announcement
from apps.announcements.services import (
    build_feed,
    category_filter_options,
    feed_row,
    priority_filter_options,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


@enforce_policy("announcements_feed")
@require_GET
@inertia("Announcements")
def announcements(request: HttpRequest):
    actor = cast(User, request.user)
    feed = build_feed(actor, params=request.GET, page=_page_param(request))
    selected_category = feed["filters"]["category"]
    return {
        "feed": feed,
        "filterOptions": {
            # A retired category the reader is filtering by stays listed so the
            # control can show the filter that is actually applied.
            "categories": category_filter_options(include_codes=(selected_category,)),
            "priorities": priority_filter_options(),
        },
    }


@enforce_policy("announcement_detail")
@require_GET
@inertia("AnnouncementDetail")
def announcement_detail(request: HttpRequest, announcement_id: int):
    actor = cast(User, request.user)
    # Fetched by id, then authorized by audience — never filtered by an office
    # the client named. ``assert_visible`` records the denial.
    announcement = get_object_or_404(
        Announcement.objects.select_related("category", "owner_office"),
        pk=announcement_id,
    )
    assert_visible(actor, announcement, reason="detail_out_of_audience")
    return {
        "announcement": {
            **feed_row(announcement),
            "audience": describe_audience(announcement),
            "hasAttachment": bool(announcement.attachment),
            "attachmentName": announcement.attachment_name,
        }
    }


@enforce_policy("announcement_attachment")
@require_GET
def announcement_attachment(request: HttpRequest, announcement_id: int):
    """Protected-storage download behind the same predicate as the feed.

    The file is streamed from private storage rather than linked, so there is
    no durable public URL that outlives the reader's place in the audience.
    """
    actor = cast(User, request.user)
    announcement = get_object_or_404(
        Announcement.objects.select_related("owner_office"), pk=announcement_id
    )
    assert_visible(actor, announcement, reason="attachment_out_of_audience")
    if not announcement.attachment:
        raise Http404("That announcement has no attachment.")
    return FileResponse(
        announcement.attachment.open("rb"),
        as_attachment=True,
        filename=announcement.attachment_name or announcement.attachment.name,
    )


@enforce_policy("announcement_recipient_search")
@require_GET
def recipient_search(request: HttpRequest):
    """Typeahead for individual recipients, bounded by the actor's own grant.

    JSON rather than an Inertia page: it is called from a compose control. The
    scope and the minimum query length are enforced in the service, so this
    view cannot widen either by passing something different.
    """
    actor = cast(User, request.user)
    return JsonResponse({"results": search_recipients(actor, request.GET.get("q", ""))})
