"""Action-item source registry and dashboard composer.

Each domain registers a collector that returns :class:`ActionItem` rows for
the signed-in user. Contract, inventory, transaction, training, and CRM
modules add rows here as they ship — the dashboard view never grows domain
rules. A raising collector is logged and skipped so one broken module cannot
take the whole queue down, and the client only learns that a partial failure
occurred, never which hidden records were involved.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from django.urls import reverse

from apps.inventory.action_items import collect_inventory_actions
from apps.operational_tasks.action_items import collect_task_actions
from apps.web.action_items.contract import ActionItem, ActionSourceContext
from apps.web.action_items.ordering import order_items
from apps.web.action_items.payloads import serialize_queue
from apps.web.action_items.sources import collect_profile_actions
from apps.web.dashboard.envelope import ProviderResult, empty, ready, unavailable

logger = logging.getLogger(__name__)

ActionCollector = Callable[[ActionSourceContext], list[ActionItem]]


@dataclass(frozen=True)
class ActionSourceDefinition:
    """One domain feed that can contribute action items."""

    key: str
    collector: ActionCollector
    #: Flip false while the module is registered but not yet connected; the
    #: collector is not called and cannot invent placeholder rows.
    available: bool = True


ACTION_SOURCE_DEFINITIONS: tuple[ActionSourceDefinition, ...] = (
    ActionSourceDefinition(key="profile", collector=collect_profile_actions),
    ActionSourceDefinition(key="operational_tasks", collector=collect_task_actions),
    ActionSourceDefinition(key="inventory", collector=collect_inventory_actions),
    # Remaining domains register here as their models ship (contracts,
    # transactions, documents/checklists, training, leads, commissions,
    # compliance corrections). Until then they stay out of
    # the tuple so the queue never fabricates their work.
)


def _validate_sources() -> None:
    seen: set[str] = set()
    for definition in ACTION_SOURCE_DEFINITIONS:
        if definition.key in seen:
            raise ValueError(f"Duplicate action source key: {definition.key}")
        seen.add(definition.key)


_validate_sources()


def collect_items(context: ActionSourceContext) -> tuple[list[ActionItem], bool]:
    """Run every available source; isolate failures per source.

    Returns ``(items, partial_failure)``. ``partial_failure`` is true when at
    least one available source raised. Exception detail stays in the log.
    """
    items: list[ActionItem] = []
    partial_failure = False
    for definition in ACTION_SOURCE_DEFINITIONS:
        if not definition.available:
            continue
        try:
            items.extend(definition.collector(context))
        except Exception:
            partial_failure = True
            logger.exception(
                "action_source_failed source=%s user_id=%s",
                definition.key,
                context.user.pk,
            )
    return items, partial_failure


def build_queue(
    context: ActionSourceContext,
    *,
    feed_limit: int = 0,
) -> ProviderResult:
    """Merge sources into the dashboard (or full-queue) payload.

    ``feed_limit`` of ``0`` means uncapped — used by the full filtered queue
    page. The dashboard widget passes the registry feed cap; the composer also
    enforces that cap on the ``items`` list so a forgetful caller cannot ship
    an unbounded feed.
    """
    collected, partial_failure = collect_items(context)
    ordered = order_items(collected, now=context.now)

    if not ordered and partial_failure:
        return unavailable(
            "Action items could not be loaded just now.",
            retryable=True,
        )
    if not ordered:
        return empty(
            "You're all caught up",
            "Nothing needs your attention right now. New items appear here "
            "when a profile gap, contract, transaction, or other assigned "
            "task is waiting on you.",
        )

    view_all_href = reverse("action_items_queue")
    payload = serialize_queue(ordered, now=context.now, view_all_href=view_all_href)
    meta: dict = {}
    if partial_failure:
        # Deliberately opaque: naming the failed source or records would leak
        # existence of work the reader may not be entitled to see.
        meta["partialFailure"] = True
    if feed_limit and len(payload["items"]) > feed_limit:
        payload = {
            **payload,
            "items": payload["items"][:feed_limit],
        }
        meta["truncated"] = True
    return ready(payload, **meta)


def queue_for_user(user, access, *, now, feed_limit: int = 0) -> ProviderResult:
    return build_queue(
        ActionSourceContext(user=user, access=access, now=now),
        feed_limit=feed_limit,
    )
