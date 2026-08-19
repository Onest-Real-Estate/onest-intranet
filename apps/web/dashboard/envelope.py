"""Versioned envelope every dashboard widget speaks.

A widget prop is never a bare payload. It is an envelope that says what
happened, so the page can tell the difference between three things a bare
payload conflates:

* ``ready`` — the provider ran and has something to show.
* ``empty`` — the provider ran and there is genuinely nothing. Carries the next
  action, because a new agent's blank dashboard should tell them what to do.
* ``unavailable`` — no figure exists to show. Either the backing module is not
  built yet (``retryable=False``) or the provider failed on this request
  (``retryable=True``, and the page offers a reload of just that prop).

The rule that makes the dashboard trustworthy: a provider that cannot answer
returns ``unavailable``. It never invents a record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class WidgetStatus:
    READY = "ready"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class WidgetEmptyState:
    """What to show, and what to do next, when there is nothing to show."""

    title: str
    description: str = ""
    #: Optional call to action. ``href`` is server-reversed, never a literal.
    action_label: str = ""
    action_href: str = ""

    def payload(self) -> dict[str, str]:
        data = {"title": self.title, "description": self.description}
        if self.action_label and self.action_href:
            data["actionLabel"] = self.action_label
            data["actionHref"] = self.action_href
        return data


@dataclass(frozen=True)
class WidgetUnavailable:
    """Why there is no data, and whether asking again could help."""

    reason: str
    retryable: bool = False
    #: Optional destination where this will live once it ships.
    action_label: str = ""
    action_href: str = ""

    def payload(self) -> dict[str, Any]:
        data: dict[str, Any] = {"reason": self.reason, "retryable": self.retryable}
        if self.action_label and self.action_href:
            data["actionLabel"] = self.action_label
            data["actionHref"] = self.action_href
        return data


@dataclass(frozen=True)
class Widget[T]:
    """One widget's answer, before it is serialized for Inertia."""

    status: str
    version: int
    generated_at: datetime
    data: T | None = None
    empty_state: WidgetEmptyState | None = None
    unavailable: WidgetUnavailable | None = None
    #: Provider-supplied notes for the payload, e.g. a feed's truncation flag.
    meta: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "version": self.version,
            "generatedAt": self.generated_at.isoformat(),
            "data": self.data,
            "emptyState": self.empty_state.payload() if self.empty_state else None,
            "unavailable": self.unavailable.payload() if self.unavailable else None,
            "meta": self.meta,
        }


@dataclass(frozen=True)
class ProviderResult[T]:
    """What a provider returns. The registry stamps on version and timestamp.

    Providers deliberately do not build envelopes themselves: keeping the
    version and clock out of their hands is what stops one widget drifting from
    the contract the rest of the page speaks.
    """

    status: str
    data: T | None = None
    empty_state: WidgetEmptyState | None = None
    unavailable: WidgetUnavailable | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def ready[T](data: T, **meta: Any) -> ProviderResult[T]:
    return ProviderResult(status=WidgetStatus.READY, data=data, meta=dict(meta))


def empty(
    title: str,
    description: str = "",
    *,
    action_label: str = "",
    action_href: str = "",
    **meta: Any,
) -> ProviderResult[Any]:
    return ProviderResult(
        status=WidgetStatus.EMPTY,
        empty_state=WidgetEmptyState(
            title=title,
            description=description,
            action_label=action_label,
            action_href=action_href,
        ),
        meta=dict(meta),
    )


def unavailable(
    reason: str,
    *,
    retryable: bool = False,
    action_label: str = "",
    action_href: str = "",
    **meta: Any,
) -> ProviderResult[Any]:
    return ProviderResult(
        status=WidgetStatus.UNAVAILABLE,
        unavailable=WidgetUnavailable(
            reason=reason,
            retryable=retryable,
            action_label=action_label,
            action_href=action_href,
        ),
        meta=dict(meta),
    )
