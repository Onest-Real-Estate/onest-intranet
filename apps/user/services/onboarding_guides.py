"""Which activation guide the agent may open, and when.

The Hub cannot see an agent's Outlook inbox. What it can prove is that an
authorized administrator recorded a vendor invitation as sent, and that a
published activation guide exists which this agent may watch. This module joins
those two facts and nothing else, which is why the wording it drives never says
"you have received the link".

The gate, per tool, in one sentence: **a tool's guide unlocks on that tool's
own invitation.** SkySlope being sent does not reveal the Lofty guide, because
each row reads only its own ``invitation_sent_at``. A self-serve tool has no
invitation to wait for, so its guide is available immediately; a tool already
ready keeps its guide as a replay.

Completing a guide writes ``TrainingProgress`` and means only that — the agent
watched it. A vendor account becomes ready when the tool lifecycle says so, and
only an authorized administrator moves that.
"""

from __future__ import annotations

from enum import StrEnum
from importlib import import_module
from typing import Any

from apps.user.models import User
from apps.user.services.onboarding_state import (
    AgentOnboardingJourney,
    JourneyToolState,
    ToolInvitationStatus,
)


class GuideState(StrEnum):
    """What the agent's row shows where an activation guide would go."""

    #: The tool's own invitation has not been recorded as sent.
    LOCKED = "locked"
    #: Unlocked, and a guide this agent may watch exists.
    AVAILABLE = "available"
    #: Unlocked, watched, and finished. Still replayable.
    COMPLETED = "completed"
    #: Unlocked, but no published guide this agent may see. The row falls back
    #: to vendor help or a support request rather than a button that opens
    #: nothing.
    UNAVAILABLE = "unavailable"
    #: Somebody switched this tool off for this agent.
    NOT_APPLICABLE = "not_applicable"


def _training_guides(user: User, tool_codes: list[str]) -> dict[str, Any]:
    """Bulk adapter contract for ``apps.training.tool_guides``.

    Absent module means no guides, never an error: the activation center still
    renders its waiting state and its fallbacks.
    """
    try:
        module = import_module("apps.training.tool_guides")
    except ModuleNotFoundError as exc:  # pragma: no cover - defensive seam
        if exc.name not in {"apps.training", "apps.training.tool_guides"}:
            raise
        return {}
    return module.activation_guides_for(user, tool_codes)


def guide_unlocked(tool: JourneyToolState) -> bool:
    """Whether this tool has reached the point of offering its guide.

    Reads one row. A tool is unlocked by its own recorded invitation, by having
    no invitation to wait for at all, or by already being ready — never by
    anything another tool did.
    """
    if not tool.applicable:
        return False
    if tool.self_service:
        return True
    if tool.invitation_status == ToolInvitationStatus.SENT:
        return True
    return tool.complete


def activation_guide_payloads(
    user: User, journey: AgentOnboardingJourney
) -> dict[str, dict[str, Any]]:
    """One guide block per tool key, keyed the same way the journey keys tools.

    Locked rows are serialized too — the agent should see that a guide is
    coming — but they carry no content id, title, or link, so a locked row has
    nothing to open even if the markup were tampered with. The server resolves
    guides only for tools that are already unlocked, so an unsent invitation
    never reaches the training query at all.
    """
    tools = list(journey.tools.items)
    unlocked = [tool for tool in tools if guide_unlocked(tool)]
    guides = _training_guides(user, [tool.key for tool in unlocked])

    payloads: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if not tool.applicable:
            payloads[tool.key] = {"state": str(GuideState.NOT_APPLICABLE)}
            continue
        if not guide_unlocked(tool):
            payloads[tool.key] = {"state": str(GuideState.LOCKED)}
            continue
        guide = guides.get(tool.key)
        if guide is None:
            payloads[tool.key] = {"state": str(GuideState.UNAVAILABLE)}
            continue
        payloads[tool.key] = {
            "state": str(
                GuideState.COMPLETED if guide.completed else GuideState.AVAILABLE
            ),
            "contentId": guide.content_id,
            "title": guide.title,
            "summary": guide.summary,
            "estimatedMinutes": guide.estimated_minutes,
            "href": guide.href,
            "hasTranscript": guide.has_transcript,
            "inProgress": guide.in_progress,
        }
    return payloads
