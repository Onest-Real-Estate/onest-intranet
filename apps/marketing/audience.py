"""The single audience predicate for assets.

Every surface that shows marketing assets — library, detail, dashboard,
notifications, search, attachment download — asks this module, and only this
module, whether a reader may see it. There is no second implementation to fall
out of step, and no materialized recipient list to go stale.

Union semantics
---------------
Selectors are **OR**. A reader who matches *any* selector on content
sees it; matching several still yields exactly one feed entry, because
membership is a set test against the audience table rather than a join that
can fan out. The same wording appears in ``docs/marketing-resources.md`` and in the
UI copy.

What each selector means
------------------------
=========  ==============================================================
company    Every user.
role       Every user holding that role code in a live assignment at
           ``at`` — validity windows honoured, multiple roles honoured.
region     Every user whose primary office is that node **or any office
           beneath it**.
office     Every user whose primary office is exactly that node. Never a
           sibling, never a parent.
user       That one person.
=========  ==============================================================

Evaluated at read time
----------------------
The predicate reads the user's *current* primary office and *current*
effective roles. Moving someone to another office, or ending their role
assignment, therefore changes what they can open from that moment on — for
assets published long before. That is the documented policy, and it is
why nothing here is cached against the asset.

Efficiency
----------
The reader's facts — office ancestor chain and live role codes — are gathered
once per request into an :class:`AudienceContext` and turned into a single
indexed subquery. Answering "can this person see these fifty assets"
costs the same as asking about two; ``visible_to`` reuses the identical
predicate for a single row, so a direct URL cannot be more permissive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.marketing.models import MarketingAsset, MarketingAudience
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import ROLE_BY_KEY, normalize_role_code
from apps.user.services.hierarchy import ancestors, descendant_queryset
from apps.user.services.role_assignments import get_effective_access

Kind = MarketingAudience.Kind

MANAGE_PERMISSION = "web.manage_marketing_resources"
#: Below this length a recipient search returns nothing at all. A one-character
#: query against a scoped directory is enumeration, not search.
MIN_RECIPIENT_QUERY = 2
RECIPIENT_SEARCH_LIMIT = 20


def selectors_for(asset: MarketingAsset) -> QuerySet[MarketingAudience]:
    """The stored selectors for one asset, targets already joined."""
    # Use the prefetch cache when the asset came from a prefetched queryset
    # (list pages); otherwise fall back to a targeted select_related query.
    cache = getattr(asset, "_prefetched_objects_cache", {})
    if "audiences" in cache:
        return cache["audiences"].all()
    return MarketingAudience.objects.filter(asset=asset).select_related(
        "office", "user"
    )


# --------------------------------------------------------------------------- #
# Reader facts, gathered once
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AudienceContext:
    """Everything about one reader that the predicate needs.

    ``office_chain_ids`` is the reader's own office plus its ancestors. A
    region selector matches when the targeted node is anywhere in that chain,
    which is the same thing as "the reader sits under that region" without
    expanding the region's descendants.
    """

    user_id: int | None
    office_id: int | None
    office_chain_ids: frozenset[int]
    role_codes: frozenset[str]
    is_authenticated: bool


def live_role_codes(user, *, at=None) -> frozenset[str]:
    """Role codes from assignments live at ``at``.

    Read-only on purpose: the status column is a cache that a background sync
    maintains, so the window predicate is applied here directly rather than
    trusting — or worse, writing — ``status`` on a page render.
    """
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    moment = at or timezone.now()
    rows = (
        UserRoleAssignment.objects.filter(user=user)
        .exclude(status=UserRoleAssignment.Status.REVOKED)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=moment))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=moment))
        .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=moment))
        .values_list("role", flat=True)
    )
    return frozenset(normalize_role_code(row) or row for row in rows)


def audience_context(user, *, at=None) -> AudienceContext:
    if not getattr(user, "is_authenticated", False):
        return AudienceContext(
            user_id=None,
            office_id=None,
            office_chain_ids=frozenset(),
            role_codes=frozenset(),
            is_authenticated=False,
        )
    office = getattr(user, "office", None)
    return AudienceContext(
        user_id=user.pk,
        office_id=office.pk if office else None,
        office_chain_ids=frozenset(node.pk for node in ancestors(office)),
        role_codes=live_role_codes(user, at=at),
        is_authenticated=True,
    )


# --------------------------------------------------------------------------- #
# The predicate
# --------------------------------------------------------------------------- #


def selector_q(context: AudienceContext) -> Q:
    """The union, expressed over :class:`MarketingAudience` rows.

    Each branch leads with ``kind`` and then the selector's own target column,
    which is exactly the shape of the three indexes on the table.
    """
    if not context.is_authenticated:
        return Q(pk__in=[])

    clauses = Q(kind=Kind.COMPANY)
    if context.role_codes:
        clauses |= Q(kind=Kind.ROLE, role__in=sorted(context.role_codes))
    if context.office_chain_ids:
        # A region selector reaches down; the reader's chain reaches up. They
        # meet exactly when the reader sits at or under the targeted region.
        clauses |= Q(kind=Kind.REGION, office_id__in=sorted(context.office_chain_ids))
    if context.office_id is not None:
        # Exactly this office. Not its parent, and never a sibling.
        clauses |= Q(kind=Kind.OFFICE, office_id=context.office_id)
    clauses |= Q(kind=Kind.USER, user_id=context.user_id)
    return clauses


def audience_q(context: AudienceContext) -> Q:
    """The union, as one ``Q`` over ``MarketingAsset``.

    A single ``IN`` against the audience table rather than one ``OR``-ed join
    per selector kind. Two things follow, and both matter:

    * **A reader cannot see duplicates.** Membership is a set test, so
      matching five selectors is still one row. That is structural — there is
      no ``.distinct()`` here compensating for a join that fans out.
    * **It is one indexed subquery** regardless of how many selectors exist,
      which is what keeps the feed off a per-content cost curve.

    An anonymous reader gets a never-matching ``Q`` rather than an empty one:
    an empty ``Q`` adds no restriction, which is the opposite of the intent.
    """
    if not context.is_authenticated:
        return Q(pk__in=[])
    return Q(
        pk__in=MarketingAudience.objects.filter(selector_q(context)).values("asset_id")
    )


def visible_assets(user, *, at=None, queryset=None) -> QuerySet[MarketingAsset]:
    """Published, in-window marketing assets whose audience includes ``user``."""
    moment = at or timezone.now()
    base = MarketingAsset.objects.all() if queryset is None else queryset
    return (
        base.published()
        .within_window(now=moment)
        .filter(audience_q(audience_context(user, at=moment)))
        .select_related("category", "owner_office")
    )


def visible_marketing_assets(
    user, *, at=None, queryset=None
) -> QuerySet[MarketingAsset]:
    return visible_assets(user, at=at, queryset=queryset)


def visible_to(user, asset: MarketingAsset, *, at=None) -> bool:
    """The same predicate, for one record.

    Detail pages, attachment downloads, and notification rendering all call
    this, so a direct URL can never be more permissive than the feed.
    """
    if asset.pk is None:
        return False
    return visible_assets(user, at=at).filter(pk=asset.pk).exists()


def assert_visible(user, asset: MarketingAsset, *, at=None, reason: str) -> None:
    """``visible_to`` with the denial recorded. Use on direct-object access."""
    if visible_to(user, asset, at=at):
        return
    log_event(
        "security.marketing.denied",
        actor=actor_from_user(user),
        target=AuditTarget(
            target_type=MarketingAsset._meta.label_lower,
            target_id=str(asset.pk or ""),
            target_label=asset.slug,
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )
    raise PermissionDenied("That marketing asset is not addressed to you.")


# --------------------------------------------------------------------------- #
# The other direction: who does this asset reach?
# --------------------------------------------------------------------------- #


def recipients_for(asset: MarketingAsset, *, at=None) -> QuerySet[User]:
    """Every user the asset's selectors reach, deduplicated.

    Used by notification fan-out. One queryset with a union filter rather than
    a loop over selectors, so a company-wide asset is one query and each
    person appears once however many selectors caught them.
    """
    moment = at or timezone.now()
    selectors = list(selectors_for(asset))
    if not selectors:
        return User.objects.none()

    # Company-wide subsumes every other selector, so stop rather than build a
    # union that can only reach the same set more expensively.
    if any(selector.kind == Kind.COMPANY for selector in selectors):
        return User.objects.filter(is_active=True)

    clauses = Q()
    matched = False

    role_codes = sorted(
        {selector.role for selector in selectors if selector.kind == Kind.ROLE}
    )
    if role_codes:
        live_holders = (
            UserRoleAssignment.objects.filter(role__in=role_codes)
            .exclude(status=UserRoleAssignment.Status.REVOKED)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=moment))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=moment))
            .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=moment))
            .values("user_id")
        )
        clauses |= Q(pk__in=live_holders)
        matched = True

    region_office_ids: set[int] = set()
    for selector in selectors:
        if selector.kind == Kind.REGION and selector.office is not None:
            region_office_ids.update(
                descendant_queryset(selector.office).values_list("pk", flat=True)
            )
    if region_office_ids:
        clauses |= Q(office_id__in=sorted(region_office_ids))
        matched = True

    exact_office_ids = sorted(
        {
            selector.office.pk
            for selector in selectors
            if selector.kind == Kind.OFFICE and selector.office is not None
        }
    )
    if exact_office_ids:
        clauses |= Q(office_id__in=exact_office_ids)
        matched = True

    named_user_ids = sorted(
        {
            selector.user.pk
            for selector in selectors
            if selector.kind == Kind.USER and selector.user is not None
        }
    )
    if named_user_ids:
        clauses |= Q(pk__in=named_user_ids)
        matched = True

    if not matched:
        return User.objects.none()
    # ``distinct`` is belt and braces: the clauses above are all subquery or
    # direct-column tests, so no join can duplicate a row. It stays because a
    # future selector that does join should not be able to introduce one.
    return User.objects.filter(is_active=True).filter(clauses).distinct()


# --------------------------------------------------------------------------- #
# Authoring: the publisher must own every selector they name
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AudienceSelector:
    """One requested selector, before it is trusted."""

    kind: str
    role: str = ""
    office: Office | None = None
    user: User | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "role": self.role,
            "officeId": self.office.pk if self.office else None,
            "userId": self.user.pk if self.user else None,
        }


def _deny(actor, *, reason: str, detail: dict | None = None) -> None:
    log_event(
        "security.marketing.audience_denied",
        actor=actor_from_user(actor),
        target=AuditTarget(target_type=MarketingAsset._meta.label_lower, target_id=""),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
        metadata=detail or {},
    )


def targetable_office_ids(actor) -> frozenset[int]:
    """Offices and regions this actor may name as an audience.

    Built from the actor's own grant, never from anything submitted. A branch
    admin's set is their branch; a regional admin's set is their region and
    everything beneath it. Neither contains a sibling or an ancestor.
    """
    from apps.web.authorization import scope_queryset_for_offices

    if getattr(actor, "is_superuser", False):
        return frozenset(Office.objects.values_list("pk", flat=True))
    access = get_effective_access(actor)
    if access.company_wide:
        return frozenset(Office.objects.values_list("pk", flat=True))
    reachable: set[int] = set()
    for node in scope_queryset_for_offices(actor, Office.objects.all()):
        reachable.update(descendant_queryset(node).values_list("pk", flat=True))
    return frozenset(reachable)


def targetable_role_codes(actor) -> frozenset[str]:
    """Roles this actor may address, which is the set they may delegate.

    Reusing the delegation catalog keeps one answer to "which roles is this
    administrator allowed to act on", instead of a second list that drifts.
    """
    from apps.user.services.agent_administration import delegable_role_options

    if getattr(actor, "is_superuser", False):
        return frozenset(ROLE_BY_KEY)
    return frozenset(option["value"] for option in delegable_role_options(actor))


def targetable_user_queryset(actor) -> QuerySet[User]:
    """People this actor may name individually — their administered set."""
    from apps.user.services.agent_administration import administered_user_queryset

    return administered_user_queryset(actor)


def assert_can_target(actor, selectors) -> None:
    """The publisher must hold the permission *and* own every selector.

    Checked against the actor's own querysets rather than against what was
    submitted, so a crafted office or user id fails on the server even when no
    control ever offered it.
    """
    from apps.user.services.role_assignments import has_effective_permission

    selectors = list(selectors)
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _deny(actor, reason="missing_permission")
        raise PermissionDenied("You cannot publish marketing assets.")
    if not selectors:
        raise ValidationError(
            {"audience": _("Choose at least one audience before publishing.")}
        )

    access = get_effective_access(actor)
    offices = targetable_office_ids(actor)
    roles = targetable_role_codes(actor)

    for selector in selectors:
        if selector.kind == Kind.COMPANY:
            if not (getattr(actor, "is_superuser", False) or access.company_wide):
                _deny(actor, reason="company_audience_outside_grant")
                raise PermissionDenied(
                    "Only a brokerage-wide administrator can address everyone."
                )
        elif selector.kind == Kind.ROLE:
            if selector.role not in roles:
                _deny(
                    actor,
                    reason="role_not_delegable",
                    detail={"role": selector.role},
                )
                raise PermissionDenied(
                    "That role is outside the roles you may address."
                )
        elif selector.kind in {Kind.REGION, Kind.OFFICE}:
            if selector.office is None or selector.office.pk not in offices:
                _deny(
                    actor,
                    reason="office_outside_grant",
                    detail={"office_id": getattr(selector.office, "pk", None)},
                )
                raise PermissionDenied(
                    "That office is outside the scope you may address."
                )
        elif selector.kind == Kind.USER:
            if selector.user is None or not (
                targetable_user_queryset(actor).filter(pk=selector.user.pk).exists()
            ):
                _deny(
                    actor,
                    reason="user_outside_grant",
                    detail={"user_id": getattr(selector.user, "pk", None)},
                )
                raise PermissionDenied(
                    "That person is outside the people you may address."
                )
        else:
            raise ValidationError({"audience": _("Unknown audience type.")})


def replace_audience(actor, asset: MarketingAsset, selectors) -> None:
    """Authorize, then make the stored selectors match exactly what was asked."""
    selectors = list(selectors)
    assert_can_target(actor, selectors)
    before = describe_audience(asset)
    selectors_for(asset).delete()
    MarketingAudience.objects.bulk_create(
        [
            MarketingAudience(
                asset=asset,
                kind=selector.kind,
                role=selector.role if selector.kind == Kind.ROLE else "",
                office=selector.office
                if selector.kind in {Kind.REGION, Kind.OFFICE}
                else None,
                user=selector.user if selector.kind == Kind.USER else None,
            )
            for selector in selectors
        ],
        ignore_conflicts=True,
    )
    log_event(
        "marketing.audience_changed",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=MarketingAsset._meta.label_lower,
            target_id=str(asset.pk),
            target_label=asset.slug,
        ),
        before={"audience": before},
        after={"audience": describe_audience(asset)},
    )


# --------------------------------------------------------------------------- #
# Description + recipient search
# --------------------------------------------------------------------------- #


def describe_audience(asset: MarketingAsset) -> list[dict[str, Any]]:
    """camelCase summary of the selectors, in a stable order.

    Ordered by kind then label so two assets with the same audience
    always describe it identically — the payload is compared in audit
    before/after snapshots.
    """
    order = {
        Kind.COMPANY: 0,
        Kind.ROLE: 1,
        Kind.REGION: 2,
        Kind.OFFICE: 3,
        Kind.USER: 4,
    }
    rows = [
        {
            "kind": selector.kind,
            "label": _selector_label(selector),
            "code": selector.role or "",
            "officeId": selector.office.pk if selector.office else None,
            "userId": selector.user.pk if selector.user else None,
        }
        for selector in selectors_for(asset)
    ]
    return sorted(rows, key=lambda row: (order.get(row["kind"], 9), row["label"]))


def _selector_label(selector: MarketingAudience) -> str:
    if selector.kind == Kind.COMPANY:
        return "Everyone at oNEST"
    if selector.kind == Kind.ROLE:
        definition = ROLE_BY_KEY.get(selector.role)
        return definition.label if definition else selector.role
    if selector.kind == Kind.REGION and selector.office is not None:
        return f"{selector.office.name} and offices under it"
    if selector.office is not None:
        return selector.office.name
    if selector.user is not None:
        return selector.user.get_full_name() or selector.user.email
    return ""


def search_recipients(actor, query: str, *, limit: int = RECIPIENT_SEARCH_LIMIT):
    """Look up individual recipients inside the actor's own grant.

    Three things stop this becoming a directory of the whole brokerage:
    the manage permission is required, the queryset starts from the actor's
    administered set, and a query shorter than
    :data:`MIN_RECIPIENT_QUERY` returns nothing — a browse-everything call
    dressed as a search is still enumeration.
    """
    from apps.user.services.role_assignments import has_effective_permission

    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _deny(actor, reason="missing_permission")
        raise PermissionDenied("You cannot address marketing assets.")

    term = (query or "").strip()[:120]
    if len(term) < MIN_RECIPIENT_QUERY:
        return []
    rows = (
        targetable_user_queryset(actor)
        .filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(email__icontains=term)
        )
        .filter(is_active=True)[: max(1, min(limit, RECIPIENT_SEARCH_LIMIT))]
    )
    return [
        {
            "id": row.pk,
            "name": row.get_full_name() or row.email,
            "email": row.email,
            "officeName": row.office.name if row.office else "",
        }
        for row in rows
    ]
