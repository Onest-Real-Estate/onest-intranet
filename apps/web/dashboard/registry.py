"""Widget registry and request composer.

The dashboard view returns a dict of deferred props. *Which* props, in which
defer group, at which contract version, under which cache policy, is this
registry — not a hand-maintained literal in the view.

Three properties the registry buys:

* **Independent failure.** Every provider is wrapped. One raising provider
  becomes a retryable ``unavailable`` envelope for its own prop; the shell and
  every other group still render.
* **Bounded payloads.** ``feed_limit`` caps list-shaped data centrally, so no
  future provider can put an unbounded feed on the page by forgetting a slice.
* **Cache safety by construction.** A widget that reads user data may not
  declare a shared cache, and a cached widget's key always carries the user and
  their effective-access version. Both are enforced at import.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from django.core.cache import cache
from django.utils import timezone
from inertia import defer

from apps.user.services.role_assignments import get_effective_access
from apps.web.dashboard import providers
from apps.web.dashboard.envelope import ProviderResult, Widget, WidgetStatus
from apps.web.dashboard.providers import DashboardContext
from apps.web.shell import authorization_version

logger = logging.getLogger("apps.dashboard")


class CacheScope:
    #: Recomputed every request. The default, and the only safe answer for
    #: anything derived from a user's records or effective scope.
    NONE = "none"
    #: Cacheable, keyed by user identity *and* effective-access version.
    PER_USER = "per_user"
    #: Cacheable across users. Legal only for rows declaring no user data.
    SHARED = "shared"


@dataclass(frozen=True)
class CachePolicy:
    scope: str = CacheScope.NONE
    ttl_seconds: int = 0
    #: Why this freshness is right for this widget. Read by humans in review.
    rationale: str = "Recomputed per request."


@dataclass(frozen=True)
class WidgetDefinition:
    key: str
    #: Inertia prop name — camelCase, and the string the page passes to
    #: ``router.reload({only: [...]})`` when the reader retries.
    prop: str
    #: Inertia defer group. Widgets in one group arrive in one request.
    group: str
    #: Bump whenever the shape of ``data`` changes, so a stale client can tell.
    contract_version: int
    provider: Callable[[DashboardContext], ProviderResult]
    #: True when the payload is derived from this user's records or scope.
    user_specific: bool
    cache: CachePolicy = CachePolicy()
    #: Cap for list-shaped payloads. 0 means the payload is not a feed.
    feed_limit: int = 0


WIDGET_DEFINITIONS: tuple[WidgetDefinition, ...] = (
    WidgetDefinition(
        key="performance",
        prop="metrics",
        group="metrics",
        contract_version=1,
        provider=providers.performance,
        user_specific=True,
        cache=CachePolicy(
            rationale=(
                "Commission and pipeline totals are sensitive and scope-derived; "
                "never cached, never shared."
            )
        ),
    ),
    WidgetDefinition(
        key="quick_access",
        prop="quickApps",
        group="pipeline",
        contract_version=1,
        provider=providers.quick_access,
        user_specific=False,
        cache=CachePolicy(
            scope=CacheScope.SHARED,
            ttl_seconds=300,
            rationale=(
                "Reviewed vendor configuration, identical for every user and "
                "changed only by deploy. Five minutes bounds a rollback."
            ),
        ),
        feed_limit=8,
    ),
    WidgetDefinition(
        key="announcements",
        prop="announcements",
        group="pipeline",
        contract_version=1,
        provider=providers.announcements,
        user_specific=True,
        cache=CachePolicy(
            rationale="Audience targeting is per user once publishing lands."
        ),
    ),
    WidgetDefinition(
        key="active_transactions",
        prop="transactions",
        group="pipeline",
        contract_version=1,
        provider=providers.active_transactions,
        user_specific=True,
        cache=CachePolicy(rationale="Owned records; must reflect the last write."),
        feed_limit=5,
    ),
    WidgetDefinition(
        key="training",
        prop="training",
        group="pipeline",
        contract_version=1,
        provider=providers.training,
        user_specific=True,
        cache=CachePolicy(
            rationale="Per-user completion; must reflect the last write."
        ),
    ),
    WidgetDefinition(
        key="my_day",
        prop="schedule",
        group="widgets",
        contract_version=1,
        provider=providers.my_day,
        user_specific=True,
        cache=CachePolicy(
            rationale="A calendar cached for even a minute can show a stale meeting."
        ),
        feed_limit=6,
    ),
    WidgetDefinition(
        key="action_items",
        prop="actionItems",
        group="widgets",
        contract_version=1,
        provider=providers.action_items,
        user_specific=True,
        cache=CachePolicy(rationale="Assigned work; must reflect the last write."),
        feed_limit=5,
    ),
    WidgetDefinition(
        key="market",
        prop="market",
        group="widgets",
        contract_version=1,
        provider=providers.market,
        user_specific=False,
        cache=CachePolicy(
            rationale=(
                "Rates are the same for everyone and move slowly; the policy "
                "becomes shared with a ttl once a feed is connected."
            )
        ),
        feed_limit=4,
    ),
    WidgetDefinition(
        key="quick_documents",
        prop="documents",
        group="widgets",
        contract_version=1,
        provider=providers.quick_documents,
        user_specific=True,
        cache=CachePolicy(rationale="Visibility is office- and role-scoped."),
        feed_limit=5,
    ),
)

WIDGET_BY_KEY = {definition.key: definition for definition in WIDGET_DEFINITIONS}
WIDGET_BY_PROP = {definition.prop: definition for definition in WIDGET_DEFINITIONS}


def _validate_registry() -> None:
    seen_keys: set[str] = set()
    seen_props: set[str] = set()
    for definition in WIDGET_DEFINITIONS:
        if definition.key in seen_keys:
            raise ValueError(f"Duplicate widget key: {definition.key}")
        if definition.prop in seen_props:
            raise ValueError(f"Duplicate widget prop: {definition.prop}")
        seen_keys.add(definition.key)
        seen_props.add(definition.prop)
        if definition.contract_version < 1:
            raise ValueError(f"{definition.key}: contract_version starts at 1")
        if definition.feed_limit < 0:
            raise ValueError(f"{definition.key}: feed_limit cannot be negative")
        policy = definition.cache
        if policy.scope not in {
            CacheScope.NONE,
            CacheScope.PER_USER,
            CacheScope.SHARED,
        }:
            raise ValueError(f"{definition.key}: unknown cache scope {policy.scope!r}")
        if policy.scope == CacheScope.SHARED and definition.user_specific:
            raise ValueError(
                f"{definition.key}: a user-specific widget cannot use a shared "
                "cache — its payload would leak between accounts"
            )
        if policy.scope != CacheScope.NONE and policy.ttl_seconds <= 0:
            raise ValueError(
                f"{definition.key}: a cached widget needs a positive ttl_seconds"
            )
        if policy.scope == CacheScope.NONE and policy.ttl_seconds:
            raise ValueError(
                f"{definition.key}: ttl_seconds is meaningless without a cache scope"
            )
        if not policy.rationale:
            raise ValueError(f"{definition.key}: cache policy needs a rationale")


_validate_registry()


def widget_cache_key(definition: WidgetDefinition, context: DashboardContext) -> str:
    """Cache key for a cacheable widget.

    A per-user key carries both the user id *and* the effective-access version,
    so granting or revoking a role invalidates that user's cached widgets
    instead of serving them a payload computed under their old scope.
    """
    parts = ["dashboard", definition.key, str(definition.contract_version)]
    if definition.cache.scope == CacheScope.PER_USER:
        parts += [str(context.user.pk), authorization_version(context.access)]
    return ":".join(parts)


def _apply_feed_limit(
    definition: WidgetDefinition, result: ProviderResult
) -> ProviderResult:
    """Cap list payloads centrally, so no provider can ship an unbounded feed."""
    if not definition.feed_limit or not isinstance(result.data, list):
        return result
    if len(result.data) <= definition.feed_limit:
        return result
    return replace(
        result,
        data=result.data[: definition.feed_limit],
        meta={**result.meta, "truncated": True},
    )


def load_widget(definition: WidgetDefinition, context: DashboardContext) -> Widget:
    """Run one provider and seal the result in its envelope.

    Failure is contained here: a provider that raises yields a retryable
    ``unavailable`` envelope for its own prop and nothing else. The reason is
    deliberately generic — an exception message can carry query fragments or
    record identifiers, and this string is rendered in the browser.
    """
    try:
        result = _apply_feed_limit(definition, definition.provider(context))
    except Exception:
        logger.exception(
            "dashboard_widget_failed widget=%s prop=%s user_id=%s",
            definition.key,
            definition.prop,
            context.user.pk,
        )
        from apps.web.dashboard.envelope import unavailable

        result = unavailable(
            "This widget could not be loaded just now.", retryable=True
        )
    return Widget(
        status=result.status,
        version=definition.contract_version,
        generated_at=context.now,
        data=result.data,
        empty_state=result.empty_state,
        unavailable=result.unavailable,
        meta=result.meta,
    )


def _cached_widget(definition: WidgetDefinition, context: DashboardContext) -> Widget:
    if definition.cache.scope == CacheScope.NONE:
        return load_widget(definition, context)
    key = widget_cache_key(definition, context)
    cached = cache.get(key)
    if cached is not None:
        return cached
    widget = load_widget(definition, context)
    # Only a settled answer is worth keeping; caching a transient failure would
    # pin the outage in place for the whole ttl.
    if widget.status != WidgetStatus.UNAVAILABLE or not (
        widget.unavailable and widget.unavailable.retryable
    ):
        cache.set(key, widget, definition.cache.ttl_seconds)
    return widget


def build_context(user, *, at=None) -> DashboardContext:
    """One effective-access lookup for the whole page."""
    return DashboardContext(
        user=user,
        access=get_effective_access(user),
        now=at or timezone.now(),
    )


def widget_payload(definition: WidgetDefinition, context: DashboardContext) -> dict:
    return _cached_widget(
        definition, replace(context, feed_limit=definition.feed_limit)
    ).payload()


def deferred_widget_props(user, *, at=None) -> dict[str, Any]:
    """The dashboard's deferred props, one per registered widget.

    The context is built lazily and memoized across the closures: Inertia only
    calls the loaders for the props it is actually sending, while a response
    containing several widgets still resolves effective access exactly once.
    """
    context: DashboardContext | None = None

    def request_context() -> DashboardContext:
        nonlocal context
        if context is None:
            context = build_context(user, at=at)
        return context

    return {
        definition.prop: defer(
            (
                lambda definition=definition: widget_payload(
                    definition, request_context()
                )
            ),
            group=definition.group,
        )
        for definition in WIDGET_DEFINITIONS
    }
