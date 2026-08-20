"""Audience resolution and dashboard-cache freshness.

One function decides whether a link reaches a reader, and both the dashboard
provider and the administrator's preview call it. A second implementation would
be a second answer, and the preview would stop meaning anything.

The rules, in the order they are applied:

1. **Lifecycle.** Archived links are gone. Inactive links are hidden.
2. **Publish window.** ``publish_start_at`` (inclusive) and ``publish_end_at``
   (exclusive) bracket visibility; either may be null for an open end.
3. **Role audience.** No role rows means every role. Otherwise the reader must
   hold at least one named role — the same stable codes ``apps.user.roles``
   defines, resolved through effective assignments, never a group label.
4. **Office audience.** ``company_wide`` short-circuits to visible. Otherwise
   the reader's own office must match an audience row: the row's office
   exactly, or an ancestor node whose row includes descendants. A reader with
   no office therefore only ever sees company-wide links.

Dimensions are ANDed, values within a dimension are ORed. "Agent" is not a
special case: it is the ``realtor`` role code, matched by rule 3 like any other.

Freshness. The Quick Access widget is cached per user, so a save has to reach
readers who already have a cached payload. Every cache key carries
:func:`configuration_version`, a stamp derived from the links table. Saving
recomputes it, which retires every previously cached key at once instead of
deleting an unbounded set of per-user entries. If the cache is cold or was
evicted, the stamp is recomputed from the database, so a lost cache entry
degrades to a slower answer rather than a stale one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Q, QuerySet
from django.utils import timezone

from apps.user.models import Office, User
from apps.user.services.hierarchy import ancestors
from apps.user.services.role_assignments import (
    EffectiveAccess,
    get_effective_role_keys,
)
from apps.web.models import (
    QuickAccessLink,
    QuickAccessLinkOfficeAudience,
    QuickAccessLinkRoleAudience,
)

CONFIGURATION_VERSION_CACHE_KEY = "quick_access:configuration_version"
#: The stamp is recomputed on write; the timeout only bounds a cache that
#: somehow missed an invalidation, and never makes a fresh stamp go stale.
CONFIGURATION_VERSION_TTL = 900


# --------------------------------------------------------------------------- #
# Freshness
# --------------------------------------------------------------------------- #


def _compute_configuration_version() -> str:
    """Digest of everything that can change what a reader sees.

    Row counts alone would miss an in-place edit and a maximum timestamp alone
    would miss a delete of the newest row, so the stamp carries both, plus the
    audience tables, which change without touching a link's ``updated_at``.
    """
    links = QuickAccessLink.objects.aggregate(
        count=Count("pk"), latest=Max("updated_at")
    )
    roles = QuickAccessLinkRoleAudience.objects.count()
    offices = QuickAccessLinkOfficeAudience.objects.count()
    latest = links["latest"].isoformat() if links["latest"] else ""
    payload = f"{links['count']}:{latest}:{roles}:{offices}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def configuration_version() -> str:
    stamp = cache.get(CONFIGURATION_VERSION_CACHE_KEY)
    if stamp is None:
        stamp = _compute_configuration_version()
        cache.set(CONFIGURATION_VERSION_CACHE_KEY, stamp, CONFIGURATION_VERSION_TTL)
    return stamp


def invalidate_configuration_cache() -> None:
    """Retire every cached Quick Access payload, immediately.

    Called after the transaction commits. Recomputing rather than deleting is
    deliberate: a delete would let a concurrent read repopulate the key from
    the pre-commit state.
    """
    cache.set(
        CONFIGURATION_VERSION_CACHE_KEY,
        _compute_configuration_version(),
        CONFIGURATION_VERSION_TTL,
    )


def invalidate_on_commit() -> None:
    transaction.on_commit(invalidate_configuration_cache)


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def office_ancestor_ids(office: Office | None) -> frozenset[int]:
    """Ids of ``office`` and every node above it, root included."""
    return frozenset(node.pk for node in ancestors(office))


def _published_q(at) -> Q:
    return (
        Q(is_archived=False, is_active=True)
        & (Q(publish_start_at__isnull=True) | Q(publish_start_at__lte=at))
        & (Q(publish_end_at__isnull=True) | Q(publish_end_at__gt=at))
    )


def visible_links_queryset(
    *,
    role_keys: Iterable[str],
    office: Office | None,
    at=None,
) -> QuerySet[QuickAccessLink]:
    """Links a reader with these roles, in this office, may launch.

    Written as ``EXISTS`` subqueries rather than joins so the result needs no
    ``distinct()`` — a link with four audience rows must not appear four times,
    and a ``distinct()`` on a nullable-join query is the kind of thing that
    quietly stops working when a column is added.
    """
    at = at or timezone.now()
    roles = sorted({key for key in role_keys if key})
    ancestor_ids = office_ancestor_ids(office)

    has_role_audience = Exists(
        QuickAccessLinkRoleAudience.objects.filter(link=OuterRef("pk"))
    )
    matches_role = Exists(
        QuickAccessLinkRoleAudience.objects.filter(
            link=OuterRef("pk"), role_code__in=roles
        )
    )
    matches_office = Exists(
        QuickAccessLinkOfficeAudience.objects.filter(
            Q(office_id=office.pk if office else None)
            | Q(office_id__in=ancestor_ids, include_descendants=True),
            link=OuterRef("pk"),
        )
    )
    return (
        QuickAccessLink.objects.filter(_published_q(at))
        .filter(Q(company_wide=True) | matches_office)
        .filter(~has_role_audience | matches_role)
        .order_by("sort_order", "name", "pk")
    )


def visible_links_for(
    user: User,
    *,
    access: EffectiveAccess | None = None,
    at=None,
) -> QuerySet[QuickAccessLink]:
    """The reader's own launchers. Never accepts a client-supplied office."""
    role_keys: Sequence[str] = (
        access.role_keys if access is not None else get_effective_role_keys(user)
    )
    return visible_links_queryset(role_keys=role_keys, office=user.office, at=at)


# --------------------------------------------------------------------------- #
# Explained resolution, for the administrator's preview
# --------------------------------------------------------------------------- #

HIDDEN_ARCHIVED = "Archived."
HIDDEN_INACTIVE = "Deactivated."
HIDDEN_NOT_YET_PUBLISHED = "Publish window has not started."
HIDDEN_EXPIRED = "Publish window has ended."
HIDDEN_ROLE = "This role is not in the link's role audience."
HIDDEN_OFFICE = "This office is not in the link's office audience."


def explain_visibility(
    link: QuickAccessLink,
    *,
    role_keys: Iterable[str],
    office: Office | None,
    ancestor_ids: frozenset[int] | None = None,
    at=None,
) -> list[str]:
    """Every reason this link stays hidden. Empty means it is visible.

    Returning all reasons rather than the first keeps the preview honest: a
    link that is both inactive *and* out of audience should not look like it
    only needs a switch flipped.
    """
    at = at or timezone.now()
    roles = {key for key in role_keys if key}
    if ancestor_ids is None:
        ancestor_ids = office_ancestor_ids(office)
    reasons: list[str] = []

    if link.is_archived:
        reasons.append(HIDDEN_ARCHIVED)
    if not link.is_active:
        reasons.append(HIDDEN_INACTIVE)
    if link.publish_start_at and link.publish_start_at > at:
        reasons.append(HIDDEN_NOT_YET_PUBLISHED)
    if link.publish_end_at and link.publish_end_at <= at:
        reasons.append(HIDDEN_EXPIRED)

    audience_roles = {row.role_code for row in link.role_audiences.all()}
    if audience_roles and not (audience_roles & roles):
        reasons.append(HIDDEN_ROLE)

    if not link.company_wide:
        matched = any(
            row.office_id == (office.pk if office else None)
            or (row.include_descendants and row.office_id in ancestor_ids)
            for row in link.office_audiences.all()
        )
        if not matched:
            reasons.append(HIDDEN_OFFICE)
    return reasons
