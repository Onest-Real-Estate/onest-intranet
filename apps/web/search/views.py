"""Global search endpoints: the header dialog's JSON, and the full-results page.

Both answer from the same aggregator, so the popover and the page can never
disagree about what somebody may see. Neither of them decides anything: every
result was already authorized by the domain that produced it, and every
destination re-enforces its own policy when followed.
"""

from __future__ import annotations

from typing import cast

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.search.service import RateLimited, run_search


@enforce_policy("search_suggestions")
@require_GET
def search_suggestions(request: HttpRequest):
    """Grouped results for the header dialog.

    JSON rather than an Inertia page: it is polled while somebody types, and a
    page visit per keystroke would push history entries and re-render the shell.
    """
    actor = cast(User, request.user)
    try:
        # Counted before the work, so a refused request costs a cache read
        # rather than four scoped queries.
        from apps.web.search.service import check_rate_limit

        check_rate_limit(actor)
    except RateLimited:
        return JsonResponse(
            {"error": "rate_limited", "detail": "Too many searches. Wait a moment."},
            status=429,
        )
    return JsonResponse(run_search(actor, request.GET.get("q", "")))


@enforce_policy("search_page")
@require_GET
@inertia("Search")
def search_page(request: HttpRequest):
    """The full-results page — a real destination, linkable and bookmarkable.

    Deliberately not rate limited: it is one navigation, not a keystroke, and a
    reader following "see all results" must never meet a 429.
    """
    actor = cast(User, request.user)
    return {"results": run_search(actor, request.GET.get("q", ""), limit=20)}
