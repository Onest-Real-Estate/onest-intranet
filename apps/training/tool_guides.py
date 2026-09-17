"""The activation guide one onboarding tool unlocks.

A "Watch how to activate Lofty" button is not a URL in a React file. It is a
published training item tagged with that tool's stable code, offered only when
the reader may actually open it. This module owns that join — the catalog's
``slug`` on one side, :mod:`apps.training.audience`'s single visibility
predicate on the other — so a new tool is a catalog row plus a training item,
never a deploy.

Three rules decide whether a guide is offered at all:

**Visible.**
    Published, inside its publication window, and addressed to this reader.
    The predicate is ``visible_training_content``; there is no second copy of
    it here, so a guide surfaced beside a tool can never be more permissive
    than the same item in the library.

**Playable.**
    A ready primary recording, or an approved embed. A guide whose video is
    still processing, quarantined, or missing would render a button that opens
    nothing — the exact broken affordance the caller falls back from.

**Current.**
    One row per tool: the lowest-ordered family, and within it the highest
    version number that is still visible. A superseded guide stops being
    offered the moment its replacement publishes, and un-publishing the
    replacement falls back to the version before it rather than to nothing.

Whether the agent has *finished* the guide is a separate fact, read from
``TrainingProgress``. Finishing a guide never marks a vendor account ready —
only the tool lifecycle does that, and only an authorized administrator moves
it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from django.db.models import Exists, OuterRef, Q
from django.urls import reverse

from apps.training.audience import visible_training_content
from apps.training.models import (
    TrainingContent,
    TrainingEmbed,
    TrainingMedia,
    TrainingTranscription,
)
from apps.training.progress import completion_state
from apps.training.taxonomy import (
    COMPLETION_COMPLETED,
    COMPLETION_IN_PROGRESS,
    CONTENT_TYPE_TOOL_ONBOARDING,
)


@dataclass(frozen=True)
class ActivationGuide:
    """One tool's current activation guide, as an agent surface may read it.

    Deliberately narrow. The caller gets an id, wording, and the typed route
    that opens the item under its own permission check — never a media URL, a
    storage key, or an audience, all of which belong to the training detail
    surface and its own authorization.
    """

    tool_code: str
    content_id: int
    title: str
    summary: str
    estimated_minutes: int | None
    href: str
    completed: bool
    in_progress: bool
    #: Whether the item carries a transcript, so a caller can say so before the
    #: agent commits to opening a video.
    has_transcript: bool
    version_number: int


def _playable() -> Q:
    """A ready primary recording, or an approved embed."""
    ready_media = TrainingMedia.objects.filter(
        content=OuterRef("pk"),
        is_active=True,
        role=TrainingMedia.Role.PRIMARY,
        processing_state=TrainingMedia.ProcessingState.READY,
    )
    embed = TrainingEmbed.objects.filter(content=OuterRef("pk")).exclude(url="")
    return Q(Exists(ready_media)) | Q(Exists(embed))


def activation_guides_for(
    user, tool_codes: Iterable[str], *, now=None
) -> dict[str, ActivationGuide]:
    """The current, visible, playable guide for each of ``tool_codes``.

    Codes with no offerable guide are simply absent from the result — the
    caller shows its fallback rather than a button that opens nothing. Costs
    two queries beyond the visibility predicate's own, whatever the number of
    codes asked about.
    """
    codes = sorted({code for code in tool_codes if code})
    if not codes or not getattr(user, "is_authenticated", False):
        return {}

    candidates = list(
        visible_training_content(user, at=now)
        .filter(
            content_type=CONTENT_TYPE_TOOL_ONBOARDING,
            tool_code__in=codes,
        )
        .filter(_playable())
        .annotate(
            guide_has_transcript=Exists(
                TrainingTranscription.objects.filter(content=OuterRef("pk"))
            )
        )
        # Lowest display order wins the tool, then the newest version of that
        # family. ``-pk`` only breaks a genuine tie, so the choice is stable
        # across requests.
        .order_by("tool_code", "display_order", "-version_number", "-pk")
    )

    current: dict[str, TrainingContent] = {}
    for content in candidates:
        current.setdefault(content.tool_code, content)
    if not current:
        return {}

    completion = completion_state(user, [item.pk for item in current.values()])
    return {
        code: ActivationGuide(
            tool_code=code,
            content_id=content.pk,
            title=content.title,
            summary=content.summary,
            estimated_minutes=content.estimated_minutes,
            href=reverse("training_detail", args=[content.pk]),
            completed=completion.get(content.pk) == COMPLETION_COMPLETED,
            in_progress=completion.get(content.pk) == COMPLETION_IN_PROGRESS,
            has_transcript=bool(getattr(content, "guide_has_transcript", False)),
            version_number=content.version_number,
        )
        for code, content in current.items()
    }
