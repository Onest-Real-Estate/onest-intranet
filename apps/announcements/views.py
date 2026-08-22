"""The announcements feed — one Inertia page, audience-scoped on the server."""

from __future__ import annotations

from typing import cast

from django.http import HttpRequest
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.announcements.services import (
    build_feed,
    category_filter_options,
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
