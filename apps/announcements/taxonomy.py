"""Governed announcement taxonomy: priority and category.

Governance split (decided here, documented in ``docs/announcements.md``)
-----------------------------------------------------------------------
**Priority is code-owned.** The set is deliberately small and closed —
``normal``, ``important``, ``urgent`` — because two things read it as a
contract: the documented feed ordering and the notification policy adapter.
An administrator who could add a fourth value, reorder ranks, or relabel
``urgent`` would be editing behaviour, not vocabulary, so labels live here and
governance does not permit editing them at runtime.

**Category is admin-managed.** Categories are vocabulary: which kinds of news
a brokerage publishes changes without any behaviour changing with it. They are
rows (:class:`~apps.announcements.models.AnnouncementCategory`) with an
immutable stable ``code``, an editable ``label``, and an ``is_active`` flag.
The eight codes seeded from :data:`CATEGORY_SEED` are marked ``is_system`` and
can never be deleted; any category is protected from deletion while an
announcement references it, and deactivating one keeps history readable.

Unknown codes fail safely
-------------------------
Read paths never raise on an unrecognized code. :func:`resolve_priority`
returns the documented fallback (``normal``) with ``known=False`` and the
original code preserved in ``requested_code`` so the surface can say so in
words; :func:`resolve_category` does the same with an ``uncategorized``
placeholder. Write paths are strict: :func:`require_priority` raises
``ValidationError``, so an unknown code can be read but never stored.

This module is deliberately free of database imports so the vocabulary can be
imported from migrations, adapters, and tests without an app registry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("apps.announcements")

# --------------------------------------------------------------------------- #
# Priority — code-owned, closed set
# --------------------------------------------------------------------------- #

PRIORITY_NORMAL = "normal"
PRIORITY_IMPORTANT = "important"
PRIORITY_URGENT = "urgent"


@dataclass(frozen=True)
class PriorityDefinition:
    """One priority level.

    ``rank`` is the sort key and the only ordering meaning the code carries:
    lower sorts first, matching ``apps.notifications.contract`` so the two
    scales never drift in opposite directions. It is not an authorization
    input — see :mod:`apps.announcements.services`.
    """

    code: str
    label: str
    rank: int
    description: str


PRIORITIES: tuple[PriorityDefinition, ...] = (
    PriorityDefinition(
        code=PRIORITY_URGENT,
        label="Urgent",
        rank=1,
        description=(
            "Act today. Sorts to the top of the feed and notifies immediately."
        ),
    ),
    PriorityDefinition(
        code=PRIORITY_IMPORTANT,
        label="Important",
        rank=2,
        description="Read soon. Sorts above normal news and notifies in-app.",
    ),
    PriorityDefinition(
        code=PRIORITY_NORMAL,
        label="Normal",
        rank=3,
        description="Routine news. Sorts by recency and does not notify.",
    ),
)

PRIORITY_BY_CODE: dict[str, PriorityDefinition] = {
    definition.code: definition for definition in PRIORITIES
}
PRIORITY_CODES: frozenset[str] = frozenset(PRIORITY_BY_CODE)
#: Ranks ordered as the feed orders them, for readable assertions and docs.
PRIORITY_CODES_BY_RANK: tuple[str, ...] = tuple(
    definition.code for definition in sorted(PRIORITIES, key=lambda item: item.rank)
)
#: ``choices`` for the model field. Stored values are the stable codes.
PRIORITY_CHOICES: list[tuple[str, str]] = [
    (definition.code, _(definition.label)) for definition in PRIORITIES
]
#: Where an unknown or missing priority lands on read.
FALLBACK_PRIORITY: PriorityDefinition = PRIORITY_BY_CODE[PRIORITY_NORMAL]


@dataclass(frozen=True)
class ResolvedPriority:
    """A priority safe to render.

    ``known`` is false when the stored code is not in the catalog; ``code``
    then holds the fallback that ordering and policy actually used, and
    ``requested_code`` holds what the row stored, so the surface can name the
    substitution in words instead of silently pretending.
    """

    code: str
    label: str
    rank: int
    known: bool
    requested_code: str


def is_known_priority(code: str | None) -> bool:
    return (code or "") in PRIORITY_CODES


def resolve_priority(code: str | None) -> ResolvedPriority:
    """Never raises. Unknown or missing codes become the documented fallback."""
    requested = (code or "").strip()
    definition = PRIORITY_BY_CODE.get(requested)
    if definition is not None:
        return ResolvedPriority(
            code=definition.code,
            label=definition.label,
            rank=definition.rank,
            known=True,
            requested_code=definition.code,
        )
    if requested:
        # Loud in the log, quiet on the page: a legacy code is an operational
        # problem, not a reason to fail a reader's request.
        logger.warning("announcements: unknown priority code %r", requested)
    return ResolvedPriority(
        code=FALLBACK_PRIORITY.code,
        label=FALLBACK_PRIORITY.label,
        rank=FALLBACK_PRIORITY.rank,
        known=False,
        requested_code=requested,
    )


def priority_rank(code: str | None) -> int:
    """Sort key for one stored code, with unknown codes ranked as normal."""
    return resolve_priority(code).rank


def require_priority(code: str | None) -> str:
    """Strict write-path check. Returns the stable code or raises."""
    if not is_known_priority(code):
        raise ValidationError(
            _("Select a valid priority."),
            code="unknown_priority",
        )
    return (code or "").strip()


# --------------------------------------------------------------------------- #
# Category — admin-managed rows, seeded from this catalog
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CategorySeed:
    code: str
    label: str
    description: str
    display_order: int


CATEGORY_SEED: tuple[CategorySeed, ...] = (
    CategorySeed(
        code="company_announcement",
        label="Company Announcement",
        description="Brokerage-wide news from leadership.",
        display_order=10,
    ),
    CategorySeed(
        code="market_update",
        label="Market Update",
        description="Market conditions, pricing, and inventory commentary.",
        display_order=20,
    ),
    CategorySeed(
        code="event",
        label="Event",
        description="Meetings, celebrations, and brokerage events.",
        display_order=30,
    ),
    CategorySeed(
        code="training_notice",
        label="Training Notice",
        description="Course announcements, deadlines, and certification news.",
        display_order=40,
    ),
    CategorySeed(
        code="compliance_update",
        label="Compliance Update",
        description="Regulatory, legal, and policy changes agents must follow.",
        display_order=50,
    ),
    CategorySeed(
        code="office_notice",
        label="Office Notice",
        description="Building, parking, hours, and other location news.",
        display_order=60,
    ),
    CategorySeed(
        code="technology_notice",
        label="Technology Notice",
        description="System availability, releases, and tooling changes.",
        display_order=70,
    ),
    CategorySeed(
        code="urgent_operational_notice",
        label="Urgent Operational Notice",
        description="Outages, closures, and incidents needing action today.",
        display_order=80,
    ),
)

CATEGORY_SEED_BY_CODE: dict[str, CategorySeed] = {
    seed.code: seed for seed in CATEGORY_SEED
}
#: Seeded codes are ``is_system`` rows: relabel and deactivate, never delete.
SYSTEM_CATEGORY_CODES: frozenset[str] = frozenset(CATEGORY_SEED_BY_CODE)

#: Where a missing category lands on read. Not a stored code — no row uses it.
FALLBACK_CATEGORY_CODE = "uncategorized"
FALLBACK_CATEGORY_LABEL = "Uncategorized"


@dataclass(frozen=True)
class ResolvedCategory:
    """A category safe to render, including for a draft that has none yet."""

    code: str
    label: str
    known: bool
    is_active: bool
    requested_code: str


def resolve_category(category) -> ResolvedCategory:
    """Never raises. ``None`` (an incomplete draft) becomes the placeholder.

    An inactive category still resolves to its real label: retiring a category
    stops new use, it does not rewrite what was already published.
    """
    if category is None:
        return ResolvedCategory(
            code=FALLBACK_CATEGORY_CODE,
            label=FALLBACK_CATEGORY_LABEL,
            known=False,
            is_active=False,
            requested_code="",
        )
    return ResolvedCategory(
        code=category.code,
        label=category.label,
        known=True,
        is_active=category.is_active,
        requested_code=category.code,
    )
