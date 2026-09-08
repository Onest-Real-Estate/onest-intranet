"""Dashboard composition layer.

``apps.web.views.dashboard`` asks this package for the page's props and does
nothing else. Query work lives in :mod:`apps.web.dashboard.providers`, the
prop/version/cache contract in :mod:`apps.web.dashboard.registry`, and the
envelope every widget speaks in :mod:`apps.web.dashboard.envelope`.

See ``docs/dashboard.md`` for the widget contracts and freshness policy.
See ``docs/dashboard-action-items.md`` for the action-item source registry.
"""

from apps.web.dashboard.envelope import (
    ProviderResult,
    Widget,
    WidgetEmptyState,
    WidgetStatus,
    WidgetUnavailable,
    empty,
    ready,
    unavailable,
)
from apps.web.dashboard.providers import DashboardContext
from apps.web.dashboard.registry import (
    WIDGET_BY_KEY,
    WIDGET_BY_PROP,
    WIDGET_DEFINITIONS,
    CachePolicy,
    CacheScope,
    WidgetDefinition,
    build_context,
    deferred_widget_props,
    load_widget,
    widget_cache_key,
    widget_payload,
)
from apps.web.dashboard.sections import HUB_SECTIONS
from apps.web.dashboard.timeframes import greeting_payload, user_timezone

__all__ = [
    "HUB_SECTIONS",
    "WIDGET_BY_KEY",
    "WIDGET_BY_PROP",
    "WIDGET_DEFINITIONS",
    "CachePolicy",
    "CacheScope",
    "DashboardContext",
    "ProviderResult",
    "Widget",
    "WidgetDefinition",
    "WidgetEmptyState",
    "WidgetStatus",
    "WidgetUnavailable",
    "build_context",
    "deferred_widget_props",
    "empty",
    "greeting_payload",
    "load_widget",
    "ready",
    "unavailable",
    "user_timezone",
    "widget_cache_key",
    "widget_payload",
]
