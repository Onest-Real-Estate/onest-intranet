"""Resolving a notification's detail from its source record, at view time.

A notification is a pointer, not a copy. The row says *that* something needs
attention; what it concerns is read back from the owning domain each time the
reader opens their inbox, through the resolver registered for that module.

This is what makes revocation work. When somebody loses a permission, changes
office, or the source record is deleted, the resolver stops returning detail
and stops offering the action — including on notifications delivered months
earlier. Nothing has to go back and rewrite old rows.

Resolvers are **batched**: one call per source module per page, never one per
row, so a page of notifications costs a bounded number of queries.

Registering a resolver::

    from apps.notifications.sources import SourceResolution, register_resolver

    def resolve(user, notifications):
        return {n.public_id: SourceResolution(available=True, detail="…")
                for n in notifications}

    register_resolver("contract", resolve)
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

logger = logging.getLogger("apps.notifications")

#: Copy shown when a source will not vouch for a notification any more. It is
#: deliberately identical for "you lost the grant", "it moved out of your
#: scope", and "it was deleted": distinguishing them would answer a question
#: about a record the reader is no longer allowed to ask about.
UNAVAILABLE_REASON = "The record this refers to is no longer available to you."


@dataclass(frozen=True)
class SourceResolution:
    """What a source domain is willing to say to this reader, right now."""

    available: bool
    detail: str = ""
    action_available: bool = False
    unavailable_reason: str = ""

    @classmethod
    def unavailable(cls, reason: str = UNAVAILABLE_REASON) -> SourceResolution:
        return cls(available=False, unavailable_reason=reason)


#: A notification with no source module is self-contained — "your account was
#: reactivated" refers to the reader themselves. Its title is the whole story,
#: and its action (if any) re-authorizes at the destination like every other.
SELF_CONTAINED = SourceResolution(available=True, action_available=True)

ResolverFn = Callable[..., dict[UUID, SourceResolution]]

_resolvers: dict[str, ResolverFn] = {}


def register_resolver(module: str, fn: ResolverFn) -> None:
    if module in _resolvers:
        raise ValueError(f"Source resolver '{module}' is already registered.")
    _resolvers[module] = fn


def registered_modules() -> list[str]:
    return sorted(_resolvers)


def clear_resolvers_for_tests() -> None:
    _resolvers.clear()


def resolve_sources(user, notifications: Sequence) -> dict[UUID, SourceResolution]:
    """Resolve every notification on a page, one batch per source module.

    Unknown modules fail closed. A domain that has not shipped its resolver
    yet — or has been removed — produces notifications that still list, with
    no detail and no action, rather than notifications that leak.
    """
    resolutions: dict[UUID, SourceResolution] = {}
    grouped: dict[str, list] = {}
    for notification in notifications:
        if not notification.source_module:
            resolutions[notification.public_id] = SELF_CONTAINED
            continue
        grouped.setdefault(notification.source_module, []).append(notification)

    for module, rows in grouped.items():
        resolver = _resolvers.get(module)
        if resolver is None:
            for row in rows:
                resolutions[row.public_id] = SourceResolution.unavailable()
            continue
        try:
            resolved = resolver(user, rows)
        except Exception:
            # One broken domain must not take down the whole inbox; the reader
            # sees those rows without detail, and the failure is logged.
            logger.exception("notifications.source_resolver_failed module=%s", module)
            resolved = {}
        for row in rows:
            resolutions[row.public_id] = resolved.get(
                row.public_id, SourceResolution.unavailable()
            )
    return resolutions
