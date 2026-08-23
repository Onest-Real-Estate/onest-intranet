"""Reading, classifying, filtering, and publishing announcements.

The order of operations in this module is the security contract, and it is
deliberately one-directional:

1. :func:`visible_queryset` decides **which rows exist for this reader** —
   audience scope first, then lifecycle status, then the publication window.
2. :func:`apply_filters` narrows that set with reader-supplied, validated
   values. A filter can only ever remove rows.
3. :func:`order_for_feed` **sorts what step 1 and 2 produced**. It does not
   filter, and it never re-queries.

Priority participates in step 3 only. An urgent announcement outside its
window, or owned by a node the reader does not sit under, is simply not in the
set that reaches the sort — which is why "priority cannot override audience or
lifecycle" is a property of the code shape here, not a rule someone has to
remember. The tests in ``test_announcements.py`` assert it directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.db.models.functions import Least
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.announcements.audience import (
    assert_can_target,
    describe_audience,
    selectors_for,
    visible_announcements,
)
from apps.announcements.media_service import media_publish_debt
from apps.announcements.models import (
    Announcement,
    AnnouncementCategory,
    ProtectedCategoryError,
)
from apps.announcements.policy import notification_behavior
from apps.announcements.presentation import present_category, present_priority
from apps.announcements.richtext import body_payload
from apps.announcements.taxonomy import (
    PRIORITIES,
    PRIORITY_BY_CODE,
    PRIORITY_CODES,
    PRIORITY_IMPORTANT,
    SYSTEM_CATEGORY_CODES,
    is_known_priority,
    resolve_priority,
)
from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import Office, User
from apps.user.services.role_assignments import has_effective_permission

MANAGE_PERMISSION = "web.manage_announcements"
PAGE_SIZE = 12
MAX_PAGE_SIZE = 50

_SCOPE_LABELS = {
    "company": "Brokerage-wide",
    "region": "Region",
    "office": "Office",
}


# --------------------------------------------------------------------------- #
# 1. Audience + lifecycle — the set a reader is allowed to see
# --------------------------------------------------------------------------- #


def visible_queryset(user: User, *, now=None) -> QuerySet[Announcement]:
    """Delegates to the one audience predicate. Do not reimplement it here.

    Kept as a thin alias so every existing caller — feed, dashboard, tests —
    goes through :func:`apps.announcements.audience.visible_announcements`,
    which is also what the detail page and the attachment download use.
    """
    return visible_announcements(user, at=now)


# --------------------------------------------------------------------------- #
# 2. Filters — typed, validated, and stable in the URL
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AnnouncementFilters:
    """Validated feed filters.

    ``category`` and ``priority`` hold **stable codes**, which is what appears
    in the URL: ``?category=compliance_update&priority=urgent``. A value that
    is not a live code is dropped rather than applied, and recorded in
    ``rejected`` so the page can say the filter was ignored instead of
    quietly returning a set the reader did not ask for.
    """

    category: str = ""
    priority: str = ""
    rejected: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_params(cls, params, *, known_category_codes) -> AnnouncementFilters:
        rejected: list[str] = []

        raw_category = (params.get("category") or "").strip()[:40]
        category = raw_category if raw_category in known_category_codes else ""
        if raw_category and not category:
            rejected.append("category")

        raw_priority = (params.get("priority") or "").strip()[:16]
        priority = raw_priority if raw_priority in PRIORITY_CODES else ""
        if raw_priority and not priority:
            rejected.append("priority")

        return cls(category=category, priority=priority, rejected=tuple(rejected))

    def as_payload(self) -> dict[str, Any]:
        """Echoed back so the page can rebuild the exact URL it came from."""
        return {
            "category": self.category,
            "priority": self.priority,
            "rejected": list(self.rejected),
        }

    @property
    def active_count(self) -> int:
        return sum(1 for value in (self.category, self.priority) if value)


def apply_filters(
    queryset: QuerySet[Announcement], filters: AnnouncementFilters
) -> QuerySet[Announcement]:
    """Narrow only. Called after :func:`visible_queryset`, never instead."""
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.priority:
        queryset = queryset.filter(priority=filters.priority)
    return queryset


# --------------------------------------------------------------------------- #
# 3. Ordering — the documented feed order
# --------------------------------------------------------------------------- #

#: ``Case``/``When`` rather than a stored integer: rank is code-owned, so the
#: database should not hold a second copy of it that can drift. A stored code
#: outside the catalog falls through to the fallback rank, matching
#: ``taxonomy.priority_rank`` exactly.
_RANK_EXPRESSION = Case(
    *[
        When(priority=definition.code, then=definition.rank)
        for definition in PRIORITIES
    ],
    default=resolve_priority(None).rank,
    output_field=IntegerField(),
)

#: The best rank a pin can buy. Pinning **promotes** an announcement to the
#: *important* tier — it does not lift it above everything.
#:
#: This is the rule that stops an old pinned notice burying newer critical
#: content. A pinned routine notice sorts with important news; a genuinely
#: urgent announcement published this morning still sorts above it, because
#: urgent outranks important and no amount of pinning changes that. Without the
#: cap, "pinned" would be an ordering trump card and the only way to be heard
#: over a stale pin would be to un-pin it.
PIN_PROMOTED_RANK: int = PRIORITY_BY_CODE[PRIORITY_IMPORTANT].rank

_EFFECTIVE_RANK = Case(
    When(is_pinned=True, then=Least(_RANK_EXPRESSION, Value(PIN_PROMOTED_RANK))),
    default=_RANK_EXPRESSION,
    output_field=IntegerField(),
)


def order_for_feed(queryset: QuerySet[Announcement]) -> QuerySet[Announcement]:
    """The documented feed order.

    1. **effective rank** — priority rank, with a pin promoting the row to at
       most :data:`PIN_PROMOTED_RANK` (see there for why it is a cap and not a
       trump card);
    2. **``published_at``** descending — recency inside a tier;
    3. **``pk``** descending — a stable tiebreak, so two announcements
       published in the same instant always order the same way.

    Step 3 is what makes pagination stable: the sort is a *total* order, so
    page 2 cannot repeat or skip a row that page 1 already showed just because
    two rows compared equal. Sorting only — the row set is whatever the caller
    already narrowed it to, so pinning lifts an announcement within the
    reader's own set and never adds one to it.
    """
    return queryset.annotate(
        priority_rank=_RANK_EXPRESSION, effective_rank=_EFFECTIVE_RANK
    ).order_by("effective_rank", "-published_at", "-pk")


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #


def _scope_payload(announcement: Announcement) -> dict[str, str]:
    level = announcement.scope_level
    return {
        "level": level,
        "label": _SCOPE_LABELS[level],
        "officeName": announcement.owner_office.name,
    }


def feed_row(announcement: Announcement) -> dict[str, Any]:
    """One camelCase feed entry. Codes and meanings only — no styling."""
    return {
        "id": announcement.pk,
        "slug": announcement.slug,
        "title": announcement.title,
        "summary": announcement.summary,
        "body": announcement.body,
        "publishedAt": (
            announcement.published_at.isoformat() if announcement.published_at else None
        ),
        "expiresAt": (
            announcement.expires_at.isoformat() if announcement.expires_at else None
        ),
        "category": present_category(announcement.category),
        "priority": present_priority(announcement.priority),
        "scope": _scope_payload(announcement),
        "isPinned": announcement.is_pinned,
        "cta": cta_payload(announcement),
        # The body as a structured block tree. The raw source travels too, for
        # the workspace's editor; the reader-facing renderer only ever walks
        # ``bodyBlocks``, so no announcement text reaches the browser as markup.
        "bodyBlocks": body_payload(announcement.body),
    }


def cta_payload(announcement: Announcement) -> dict[str, str] | None:
    """The optional call-to-action button, or nothing.

    Both halves are required by ``announcement_cta_is_complete``, so a renderer
    that receives a payload here can draw it without checking for a missing
    label or a missing destination.
    """
    if not (announcement.cta_label and announcement.cta_url):
        return None
    return {"label": announcement.cta_label, "url": announcement.cta_url}


def category_filter_options(*, include_codes=()) -> list[dict[str, str]]:
    """Active categories, plus any inactive code the reader is filtering by.

    Keeping a retired code selectable while it sits in the URL is what makes a
    bookmarked filter survive that category's retirement, instead of silently
    resetting to "any" and showing more than the reader asked for.
    """
    extra = {code for code in include_codes if code}
    rows = AnnouncementCategory.objects.filter(Q(is_active=True) | Q(code__in=extra))
    return [{"value": row.code, "label": row.label} for row in rows]


def priority_filter_options() -> list[dict[str, str]]:
    return [
        {"value": definition.code, "label": definition.label}
        for definition in sorted(PRIORITIES, key=lambda item: item.rank)
    ]


def build_feed(
    user: User,
    *,
    params,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    now=None,
) -> dict[str, Any]:
    """The paginated, filtered, ordered feed payload for one reader."""
    from apps.web.contracts import list_response

    known_codes = set(AnnouncementCategory.objects.values_list("code", flat=True))
    filters = AnnouncementFilters.from_params(params, known_category_codes=known_codes)
    visible = visible_queryset(user, now=now)
    narrowed = apply_filters(visible, filters)
    ordered = order_for_feed(narrowed)

    size = max(1, min(page_size, MAX_PAGE_SIZE))
    total = ordered.count()
    total_pages = max(1, (total + size - 1) // size)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * size
    rows = [feed_row(item) for item in ordered[start : start + size]]

    return list_response(
        rows,
        page=current,
        page_size=size,
        total_items=total,
        filters=filters.as_payload(),
        sort_key="priority",
        sort_direction="asc",
    )


# --------------------------------------------------------------------------- #
# Validation debt + publishing
# --------------------------------------------------------------------------- #


def validation_debt(announcement: Announcement) -> list[tuple[str, Any]]:
    """What still stands between this draft and publication.

    Returned as ``(field, message)`` pairs so the same list can raise as a
    ``ValidationError`` on publish and render as a checklist on a draft.
    """
    debt: list[tuple[str, Any]] = []
    if announcement.category is None:
        debt.append(("category", _("Choose a category before publishing.")))
    elif not announcement.category.is_active:
        debt.append(("category", _("This category is retired. Choose an active one.")))
    if not is_known_priority(announcement.priority):
        debt.append(("priority", _("Choose a priority before publishing.")))
    if not announcement.title.strip():
        debt.append(("title", _("Give the announcement a title.")))
    if not announcement.body.strip():
        debt.append(("body", _("Write the announcement body.")))
    # Only once the row exists: selectors are related rows, so an unsaved
    # announcement has no way to carry one yet. ``publish_announcement`` is the
    # gate that always sees a saved row, and it refuses an empty audience.
    if announcement.pk is not None and not selectors_for(announcement).exists():
        debt.append(("audience", _("Choose who this announcement is for.")))
    # Nothing publishes while a file is still being checked or has failed:
    # an unscanned upload must never become readable by a recipient.
    debt.extend(media_publish_debt(announcement))
    return debt


def validation_debt_payload(announcement: Announcement) -> dict[str, Any]:
    debt = validation_debt(announcement)
    return {
        "isPublishable": not debt,
        "items": [
            {"field": field_name, "message": str(msg)} for field_name, msg in debt
        ],
    }


def assert_can_manage(actor: User, office: Office) -> None:
    """Manage permission plus the office being inside the actor's grant."""
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _log_denial(actor, reason="missing_permission")
        raise PermissionDenied("You cannot manage announcements.")
    if office.pk not in _manageable_office_ids(actor):
        _log_denial(actor, reason="out_of_scope_office")
        raise PermissionDenied("That office is outside your announcement scope.")


def _manageable_office_ids(actor: User) -> set[int]:
    from apps.web.authorization import scope_queryset_for_offices

    return set(
        scope_queryset_for_offices(actor, Office.objects.all()).values_list(
            "pk", flat=True
        )
    )


def _log_denial(actor: User, *, reason: str) -> None:
    log_event(
        "security.announcement.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(target_type=Announcement._meta.label_lower, target_id=""),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def _snapshot(announcement: Announcement) -> dict[str, Any]:
    return {
        "slug": announcement.slug,
        "title": announcement.title,
        "status": announcement.status,
        "category": announcement.category.code if announcement.category else None,
        "priority": announcement.priority,
        "owner_office_id": announcement.owner_office.pk,
        "is_pinned": announcement.is_pinned,
        "publish_at": announcement.publish_at,
        "expires_at": announcement.expires_at,
        "audience": describe_audience(announcement),
    }


def _stored_selectors(actor: User, announcement: Announcement):
    """Stored audience rows as selector objects, for re-authorization."""
    from apps.announcements.audience import AudienceSelector

    return [
        AudienceSelector(
            kind=row.kind,
            role=row.role,
            office=row.office,
            user=row.user,
        )
        for row in selectors_for(announcement)
    ]


@transaction.atomic
def publish_announcement(actor: User, announcement: Announcement, *, now=None):
    """Move a draft to published, refusing while validation debt remains.

    The domain event carries the taxonomy codes and the resolved notification
    behaviour so a consumer never has to re-derive policy from the row.
    """
    # Order matters. The permission and publishing-office scope come first, so
    # an unauthorized caller learns nothing about the draft. Then the author
    # gets the whole checklist at once — including a missing audience — rather
    # than one item per attempt. Only then is authority over each named
    # selector re-checked, which by that point is guaranteed non-empty.
    assert_can_manage(actor, announcement.owner_office)
    before = _snapshot(announcement)
    debt = validation_debt(announcement)
    if debt:
        raise ValidationError(dict(debt))
    # Authority over the publishing office is not authority over the audience.
    # Re-checked here rather than trusted from whenever the draft was composed:
    # the author's grant may have narrowed since.
    assert_can_target(actor, _stored_selectors(actor, announcement))

    announcement.status = Announcement.Status.PUBLISHED
    announcement.published_at = announcement.published_at or (now or timezone.now())
    announcement.archived_at = None
    announcement.updated_by = actor
    announcement.full_clean()
    announcement.save()

    behavior = notification_behavior(announcement.priority)
    # A future ``publish_at`` means the row is published but not yet visible, so
    # the event says *scheduled*. A consumer that fans notifications out on
    # ``announcement.published`` would otherwise interrupt people about news
    # they cannot open until next week.
    moment = now or timezone.now()
    visible_from = announcement.publish_at or announcement.published_at
    scheduled = announcement.publish_at is not None and announcement.publish_at > moment
    event_name = "announcement.scheduled" if scheduled else "announcement.published"
    log_event(
        event_name,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=Announcement._meta.label_lower,
            target_id=str(announcement.pk),
            target_label=announcement.slug,
        ),
        before=before,
        after=_snapshot(announcement),
    )
    publish_event(
        event_name,
        actor_id=str(actor.pk),
        subject=str(announcement.pk),
        payload={
            "announcement_id": announcement.pk,
            "category_code": announcement.category.code
            if announcement.category
            else None,
            "priority_code": announcement.priority,
            "owner_office_id": announcement.owner_office.pk,
            "scope_level": announcement.scope_level,
            "audience": describe_audience(announcement),
            "notify": behavior.notify,
            "notification_priority": behavior.priority,
            "visible_from": visible_from.isoformat() if visible_from else None,
            "expires_at": announcement.expires_at.isoformat()
            if announcement.expires_at
            else None,
        },
    )
    return announcement


def delete_category(actor: User, category: AnnouncementCategory) -> None:
    """Governance gate for destroying vocabulary.

    Three guards, cheapest first: the permission, the seeded-category rule,
    and the reference count. ``PROTECT`` on the foreign key is the backstop if
    any caller reaches the row without coming through here.
    """
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _log_denial(actor, reason="missing_permission")
        raise PermissionDenied("You cannot manage announcement categories.")
    if category.is_system or category.code in SYSTEM_CATEGORY_CODES:
        raise ProtectedCategoryError(
            f"System category {category.code!r} cannot be deleted. "
            "Deactivate it instead."
        )
    if Announcement.objects.filter(category=category).exists():
        raise ProtectedCategoryError(
            f"Category {category.code!r} is referenced by announcements. "
            "Deactivate it instead."
        )
    category.delete()
