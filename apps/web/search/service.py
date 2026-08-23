"""Running the providers: isolation, caps, a time budget, and a rate limit.

The aggregator's whole job is to ask each permitted provider and assemble the
answer without ever widening it. It holds three guarantees:

* **Capability first.** A provider whose permission the actor lacks is not
  called and its label is not returned, so an unauthorized source is invisible
  rather than empty — "no results in Transactions" would still tell you there
  is a Transactions.
* **Failures are contained.** One provider raising does not empty the response.
  Its group comes back marked ``failed`` and the reader is told which source is
  missing, which is more honest than a shorter list that looks complete.
* **The response is bounded.** Every provider has a cap, and the run has a wall
  clock. Past the budget the remaining providers are skipped and reported,
  rather than the request hanging on the slowest domain.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.cache import cache
from django.urls import NoReverseMatch, reverse

from apps.user.services.role_assignments import has_effective_permission
from apps.web.search.contract import (
    MIN_QUERY_LENGTH,
    ProviderResult,
    SearchProvider,
    is_searchable,
    normalize_query,
)
from apps.web.search.providers import SEARCH_PROVIDERS

logger = logging.getLogger("apps.search")

#: Wall clock for one search across all providers. Past it, the providers not
#: yet started are skipped: a reader waiting on the slowest domain gets nothing,
#: while a partial answer now is useful.
TIME_BUDGET_SECONDS = 1.5

#: Sliding window rate limit, per actor. Generous enough that typing with a
#: debounce never trips it, tight enough that a scripted sweep does.
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60


class RateLimited(Exception):
    """The actor has asked too often inside the window."""


def _rate_limit_key(user) -> str:
    return f"search:rate:{getattr(user, 'pk', 'anon')}"


def check_rate_limit(user, *, now: float | None = None) -> None:
    """Count this request, refusing past the window's allowance.

    Keyed by user rather than by IP: the hub is authenticated, so the actor is
    the meaningful subject, and an office behind one NAT should not share a
    budget. Cache-backed, so a restart forgives — the limit exists to stop a
    scripted sweep, not to punish.
    """
    key = _rate_limit_key(user)
    moment = now if now is not None else time.monotonic()
    window = cache.get(key) or []
    recent = [stamp for stamp in window if moment - stamp < RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= RATE_LIMIT_REQUESTS:
        raise RateLimited()
    recent.append(moment)
    cache.set(key, recent, RATE_LIMIT_WINDOW_SECONDS)


def permitted_providers(actor) -> list[SearchProvider]:
    """Providers this actor may search at all.

    The gate runs before any query, so an unauthorized domain is never asked and
    never named. Its absence is the disclosure control; its emptiness would not
    be.
    """
    if not getattr(actor, "is_authenticated", False):
        return []
    allowed: list[SearchProvider] = []
    for provider in sorted(SEARCH_PROVIDERS, key=lambda item: (item.order, item.key)):
        if provider.permission and not has_effective_permission(
            actor, provider.permission
        ):
            continue
        allowed.append(provider)
    return allowed


def _all_results_href(provider: SearchProvider, query: str) -> str:
    if not provider.all_results_route:
        return ""
    try:
        path = reverse(provider.all_results_route)
    except NoReverseMatch:
        return ""
    from django.utils.http import urlencode

    return f"{path}?{urlencode({provider.all_results_query: query})}"


def run_search(
    actor,
    raw_query: str | None,
    *,
    limit: int | None = None,
    budget: float = TIME_BUDGET_SECONDS,
) -> dict[str, Any]:
    """Search every permitted provider and assemble one payload.

    Providers run in registry order and each is timed against the shared budget.
    The order is deterministic, so the same query returns the same groups in the
    same sequence — which is what makes "the third result" a stable thing to
    click and a stable thing to assert on.
    """
    query = normalize_query(raw_query)
    if not is_searchable(query):
        return {
            "query": query,
            "groups": [],
            "total": 0,
            "tooShort": bool(query),
            "minLength": MIN_QUERY_LENGTH,
            "partial": False,
        }

    started = time.monotonic()
    groups: list[ProviderResult] = []
    partial = False

    for provider in permitted_providers(actor):
        result = ProviderResult(
            key=provider.key, label=provider.label, icon=provider.icon
        )
        if time.monotonic() - started > budget:
            # Not started rather than cut off mid-flight: a provider either ran
            # or is reported as missing, never half-reported.
            result.failed = True
            partial = True
            groups.append(result)
            continue
        cap = limit or provider.cap
        try:
            # One extra row than the cap, purely to know whether to offer "see
            # all" — the extra is never serialized.
            hits = list(provider.search(actor, query, cap + 1))
        except Exception:  # noqa: BLE001 - isolation is the point
            logger.exception("search provider %s failed", provider.key)
            result.failed = True
            partial = True
        else:
            result.truncated = len(hits) > cap
            result.hits = sorted(hits[:cap], key=lambda hit: (hit.rank, hit.title))
            result.all_results_href = _all_results_href(provider, query)
        groups.append(result)

    populated = [group for group in groups if group.hits or group.failed]
    return {
        "query": query,
        "groups": [group.payload() for group in populated],
        "total": sum(len(group.hits) for group in populated),
        "tooShort": False,
        "minLength": MIN_QUERY_LENGTH,
        "partial": partial,
    }
