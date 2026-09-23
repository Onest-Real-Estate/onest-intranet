"""Serialization for the Inertia surface (camelCase).

Nothing here filters. Rows arrive already resolved by
``services.checklist_for`` and already scoped by ``for_reader``; a payload
builder that could decide visibility would be a second authorization path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from django.urls import reverse

from apps.onboarding_tools.models import (
    COMPLETE_STATES,
    OnboardingTool,
    Provisioning,
    ToolGroup,
    ToolState,
    invitation_presentation,
)
from apps.onboarding_tools.services import Readiness, ToolProgress

if TYPE_CHECKING:
    from apps.training.tool_guides import ActivationGuide

#: State → chip tone. Presentation lives here rather than on the model so a
#: design change never becomes a data migration.
STATE_TONES: dict[str, str] = {
    ToolState.NOT_STARTED: "neutral",
    ToolState.IN_PROGRESS: "info",
    ToolState.READY: "success",
    ToolState.BLOCKED: "destructive",
    ToolState.NOT_APPLICABLE: "neutral",
}

STATE_LABELS: dict[str, str] = dict(ToolState.choices)
GROUP_LABELS: dict[str, str] = dict(ToolGroup.choices)
PROVISIONING_LABELS: dict[str, str] = dict(Provisioning.choices)


def support_href(tool: OnboardingTool) -> str:
    """Where "Support" goes for this tool.

    A catalog row may name its own request path; otherwise the IT support form
    opens already about this tool, so the agent does not retype its name.
    """
    if tool.request_path:
        return tool.request_path
    return f"{reverse('it_support')}?{urlencode({'tool': tool.slug})}"


def training_payload(guide: ActivationGuide | None) -> dict[str, Any] | None:
    """The one training item linked to a tool, or nothing.

    Narrow on purpose: the typed route opens the item under the training
    surface's own permission check, so no media URL or audience travels here.
    """
    if guide is None:
        return None
    return {
        "href": guide.href,
        "title": guide.title,
        "minutes": guide.estimated_minutes,
        "completed": guide.completed,
        "inProgress": guide.in_progress,
    }


def tool_payload(
    item: ToolProgress, guide: ActivationGuide | None = None
) -> dict[str, Any]:
    tool: OnboardingTool = item.tool
    return {
        "slug": tool.slug,
        "name": tool.name,
        "description": tool.description,
        "group": tool.group,
        "provisioning": tool.provisioning,
        "provisioningLabel": str(PROVISIONING_LABELS.get(tool.provisioning, "")),
        "selfServe": tool.is_self_serve,
        "required": tool.is_required,
        "openUrl": tool.open_url,
        "helpUrl": tool.help_url,
        # The guide. Both halves travel: a tool can be self-serve *and* still
        # have somebody to chase when a step fails.
        "steps": [str(step) for step in (tool.setup_steps or [])],
        "contact": tool.contact_label,
        "requestPath": tool.request_path,
        "state": {
            "code": item.state,
            "label": str(STATE_LABELS.get(item.state, item.state)),
            "tone": STATE_TONES.get(item.state, "neutral"),
        },
        "complete": item.is_complete,
        "note": item.note,
        # Whether the office has actually sent the vendor invitation. The agent
        # asking "has anybody done anything about my Lofty seat" reads this.
        "invitation": {
            **invitation_presentation(
                provisioning=tool.provisioning,
                invitation_sent_at=item.invitation_sent_at,
            ),
            "sentAt": (
                item.invitation_sent_at.isoformat() if item.invitation_sent_at else None
            ),
        },
        "updatedAt": item.updated_at.isoformat() if item.updated_at else None,
        # The agent's own claim, separate from ``state`` (what oNEST confirmed).
        "haveIt": item.agent_confirmed_at is not None,
        "haveItAt": (
            item.agent_confirmed_at.isoformat() if item.agent_confirmed_at else None
        ),
        "supportHref": support_href(tool),
        "training": training_payload(guide),
    }


def readiness_payload(readiness: Readiness) -> dict[str, Any]:
    return {
        "ready": readiness.ready,
        "total": readiness.total,
        "percent": readiness.percent,
        "complete": readiness.is_complete,
    }


def grouped_payload(
    items: list[ToolProgress],
    guides: Mapping[str, ActivationGuide] | None = None,
) -> list[dict[str, Any]]:
    """The catalog in its three shelves, each with its own count.

    Grouped **server-side** so the order, the counts, and the empty groups are
    the same fact the readiness figure is reading. A client-side `groupBy`
    would silently drop a group the server knows about.
    """
    groups: list[dict[str, Any]] = []
    for code, label in ToolGroup.choices:
        rows = [item for item in items if item.tool.group == code]
        if not rows:
            continue
        required = [item for item in rows if item.tool.is_required]
        groups.append(
            {
                "code": code,
                "label": str(label),
                "tools": [
                    tool_payload(item, (guides or {}).get(item.tool.slug))
                    for item in rows
                ],
                "ready": sum(1 for item in required if item.state in COMPLETE_STATES),
                "total": len(required),
            }
        )
    return groups


def state_options() -> list[dict[str, str]]:
    return [{"value": code, "label": str(label)} for code, label in ToolState.choices]
