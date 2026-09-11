"""Canonical organization hierarchy queries and membership changes.

The Office tree (head office → region → regional office → branch) is the single
source of organizational truth. Role assignments *consume* this hierarchy for
permission scopes; membership here never grants a capability by itself.

Callers that need ancestors, descendants, primary/secondary membership, org
snapshots, or auditable transfers should use this module instead of custom
parent joins.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import Office, User, UserOfficeMembership

# ---------------------------------------------------------------------------
# Tree queries
# ---------------------------------------------------------------------------


def brokerage_root() -> Office:
    """The single ONEST head-office node."""
    root = (
        Office.objects.filter(kind=Office.Kind.HEAD_OFFICE, parent__isnull=True)
        .order_by("pk")
        .first()
    )
    if root is None:
        raise ValidationError(_("The brokerage root organization is missing."))
    return root


def ancestors(office: Office | None) -> list[Office]:
    """Root-first ancestor chain including ``office`` itself."""
    if office is None:
        return []
    chain: list[Office] = []
    node: Office | None = office
    seen: set[int] = set()
    while node is not None and node.pk not in seen:
        seen.add(node.pk)
        chain.append(node)
        node = node.parent
    chain.reverse()
    return chain


def ancestor_ids(office: Office | None) -> frozenset[int]:
    return frozenset(node.pk for node in ancestors(office))


def agent_scope_office_ids(office: Office | None) -> frozenset[int]:
    """Offices whose agent-facing catalogue a member of ``office`` may browse.

    The office itself plus its ancestors up to the head office — the same chain
    ``apps.user.services.office_resources`` resolves, so a room, an inventory
    item, and an office resource published at the region reach the same people.

    Without it every catalogue was an exact ``owner_office`` match, which meant
    there was no way to publish one record for the whole brokerage: an
    administrator had to re-create it per branch (the Space table still carries
    two copies of every room for exactly that reason), and any office with no
    records of its own showed an empty catalogue to its agents.

    Inheritance runs one way. A branch never sees a sibling branch, and a
    reader at the head office does not acquire every branch's stock — that is
    manager reach, and it lives behind ``view_inventory`` / ``view_spaces`` on
    the administration surfaces.

    A reader whose own office is inactive or not assignable has no chain at all.
    """
    if office is None or not office.is_active or not office.is_assignable:
        return frozenset()
    return ancestor_ids(office)


def reader_scope_office_ids(user) -> frozenset[int]:
    """:func:`agent_scope_office_ids` for a reader, memoized on the instance.

    Per-row visibility checks ask this once per record they serialize, and the
    chain costs one indexed ``parent_id`` lookup per level. The answer cannot
    change within a request, so it is resolved once.
    """
    cached = getattr(user, "_reader_scope_office_ids", None)
    if cached is not None:
        return cached
    scope = agent_scope_office_ids(getattr(user, "office", None))
    # AnonymousUser and other read-only stand-ins refuse the attribute; they
    # simply pay the lookup again rather than failing the request.
    with contextlib.suppress(AttributeError):
        user._reader_scope_office_ids = scope
    return scope


def descendant_queryset(office: Office) -> QuerySet[Office]:
    """Offices at or under ``office``, without loading the full org into memory.

    Walks ``parent_id`` breadth-first using indexed lookups so simple
    authorization checks never materialize the whole tree.
    """
    if office.pk is None:
        return Office.objects.none()
    pending = [office.pk]
    found: set[int] = {office.pk}
    while pending:
        children = list(
            Office.objects.filter(parent_id__in=pending).values_list("pk", flat=True)
        )
        pending = [pk for pk in children if pk not in found]
        found.update(pending)
    return Office.objects.filter(pk__in=found).order_by("sort_order", "name")


def descendant_ids(office: Office) -> frozenset[int]:
    return frozenset(descendant_queryset(office).values_list("pk", flat=True))


def breadcrumb_segments(office: Office | None) -> list[dict]:
    """Display segments for hierarchy breadcrumbs."""
    return [
        {
            "id": node.pk,
            "name": node.name,
            "kind": node.kind,
            "stableKey": node.stable_key,
            "isActive": node.is_active,
        }
        for node in ancestors(office)
    ]


def organization_snapshot(office: Office | None) -> dict | None:
    """Frozen org context for records that must retain creation-time facts."""
    if office is None:
        return None
    region = office.region or office._nearest_region()
    return {
        "officeId": office.pk,
        "officeStableKey": office.stable_key,
        "officeName": office.name,
        "officeKind": office.kind,
        "pathLabel": office.path_label(),
        "regionId": region.pk if region else None,
        "regionStableKey": region.stable_key if region else None,
        "regionName": region.name if region else None,
        "isActive": office.is_active,
        "capturedAt": timezone.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Consistency / fail-closed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HierarchyInconsistency:
    office_id: int | None
    reason: str


def hierarchy_inconsistency(office: Office | None) -> HierarchyInconsistency | None:
    """Return the first structural problem, or None when the node is sound.

    Kept deliberately cheap for authorization hot paths: only denormalized
    ``region`` / kind checks run here so permission evaluation never walks the
    parent chain. Full tree validation remains on ``Office.clean()`` / ``save()``.
    """
    if office is None:
        return HierarchyInconsistency(None, "missing_office")
    if office.pk is None:
        return HierarchyInconsistency(None, "unsaved_office")
    if office.kind == Office.Kind.HEAD_OFFICE:
        return None
    if office.kind == Office.Kind.REGION:
        if office.region_id not in {None, office.pk}:
            return HierarchyInconsistency(office.pk, "region_mismatch")
        return None
    if office.region_id is None:
        return HierarchyInconsistency(office.pk, "missing_region")
    region = office.region
    if region is not None and region.kind != Office.Kind.REGION:
        return HierarchyInconsistency(office.pk, "region_mismatch")
    return None


def is_hierarchy_consistent(office: Office | None) -> bool:
    return hierarchy_inconsistency(office) is None


def require_hierarchy_consistent(office: Office | None) -> Office:
    problem = hierarchy_inconsistency(office)
    if problem is not None or office is None:
        raise ValidationError(
            _("Organization hierarchy is inconsistent and cannot be used for scope.")
        )
    return office


# ---------------------------------------------------------------------------
# Membership queries
# ---------------------------------------------------------------------------


def primary_office(user: User) -> Office | None:
    return getattr(user, "office", None)


def primary_region(user: User) -> Office | None:
    office = primary_office(user)
    if office is None:
        return None
    return office.region or office._nearest_region()


def active_memberships(
    user: User, *, at: dt.date | None = None
) -> QuerySet[UserOfficeMembership]:
    day = at or timezone.localdate()
    return (
        UserOfficeMembership.objects.filter(user=user)
        .filter(
            Q(status=UserOfficeMembership.Status.ACTIVE)
            | Q(
                status=UserOfficeMembership.Status.SCHEDULED,
                starts_on__lte=day,
            )
        )
        .exclude(ends_on__lt=day)
        .select_related("office", "office__region")
        .order_by("kind", "starts_on", "pk")
    )


def active_primary_membership(
    user: User, *, at: dt.date | None = None
) -> UserOfficeMembership | None:
    return (
        active_memberships(user, at=at)
        .filter(kind=UserOfficeMembership.Kind.PRIMARY)
        .first()
    )


def secondary_offices(user: User, *, at: dt.date | None = None) -> list[Office]:
    return [
        row.office
        for row in active_memberships(user, at=at).filter(
            kind=UserOfficeMembership.Kind.SECONDARY
        )
        if row.office is not None
    ]


def offices_for_keys(
    *,
    company_wide: bool,
    region_keys: Iterable[str],
    office_keys: Iterable[str],
) -> QuerySet[Office]:
    """Resolve scoped office keys without loading the whole tree."""
    if company_wide:
        return Office.visible_queryset()
    region_keys = list(region_keys)
    office_keys = list(office_keys)
    if not region_keys and not office_keys:
        return Office.objects.none()
    filters = Q()
    if office_keys:
        filters |= Q(stable_key__in=office_keys)
    if region_keys:
        filters |= Q(region__stable_key__in=region_keys) | Q(stable_key__in=region_keys)
    return Office.visible_queryset().filter(filters).distinct()


# ---------------------------------------------------------------------------
# Membership mutations
# ---------------------------------------------------------------------------


def _membership_target(membership: UserOfficeMembership) -> AuditTarget:
    return AuditTarget(
        target_type="user.office_membership",
        target_id=str(membership.pk or ""),
        target_label=(f"{membership.user.pk}:{membership.kind}:{membership.office.pk}"),
        target_snapshot={
            "user_id": membership.user.pk,
            "office_id": membership.office.pk,
            "kind": membership.kind,
            "status": membership.status,
        },
    )


def _overlap_exists(
    *,
    user: User,
    office: Office,
    kind: str,
    starts_on: dt.date,
    ends_on: dt.date | None,
    excluding_pk: int | None = None,
) -> bool:
    rows = UserOfficeMembership.objects.filter(
        user=user,
        office=office,
        kind=kind,
        status__in=[
            UserOfficeMembership.Status.SCHEDULED,
            UserOfficeMembership.Status.ACTIVE,
        ],
    )
    if excluding_pk is not None:
        rows = rows.exclude(pk=excluding_pk)
    for row in rows:
        row_end = row.ends_on or dt.date.max
        new_end = ends_on or dt.date.max
        if row.starts_on <= new_end and starts_on <= row_end:
            return True
    return False


@transaction.atomic
def sync_primary_membership(
    user: User,
    *,
    actor: User | None = None,
    effective_on: dt.date | None = None,
    business_reason: str = "",
) -> UserOfficeMembership | None:
    """Align primary membership history with ``user.office``.

    Prefer calling this after any write that changes ``User.office``. Does not
    mutate the user row itself.
    """
    # ``of=("self",)`` is load-bearing: ``office`` is nullable, so
    # ``select_related`` reaches it through a LEFT OUTER JOIN, and PostgreSQL
    # refuses a bare ``FOR UPDATE`` that spans the nullable side of an outer
    # join.
    locked = (
        User.objects.select_for_update(of=("self",))
        .select_related("office", "office__region")
        .get(pk=user.pk)
    )
    day = effective_on or timezone.localdate()
    office = locked.office

    current = (
        UserOfficeMembership.objects.select_for_update(of=("self",))
        .select_related("office")
        .filter(
            user=locked,
            kind=UserOfficeMembership.Kind.PRIMARY,
            status__in=[
                UserOfficeMembership.Status.SCHEDULED,
                UserOfficeMembership.Status.ACTIVE,
            ],
        )
        .order_by("-starts_on", "-pk")
        .first()
    )

    if office is None:
        if current is None:
            return None
        before = {
            "office_id": current.office.pk,
            "status": current.status,
            "ends_on": current.ends_on.isoformat() if current.ends_on else None,
        }
        current.status = UserOfficeMembership.Status.ENDED
        current.ends_on = day
        current.full_clean()
        current.save(update_fields=["status", "ends_on", "updated_at"])
        log_event(
            "user.office_membership.ended",
            actor=actor_from_user(actor) if actor else actor_from_user(locked),
            target=_membership_target(current),
            before=before,
            after={
                "office_id": current.office.pk,
                "status": current.status,
                "ends_on": day.isoformat(),
            },
            metadata={"business_reason": business_reason, "kind": "primary"},
        )
        return current

    if not office.is_assignable:
        raise ValidationError(
            {"office": _("Primary membership requires an assignable office.")}
        )
    require_hierarchy_consistent(office)

    if current is not None and current.office.pk == office.pk:
        scheduled = current.status == UserOfficeMembership.Status.SCHEDULED
        if scheduled and current.starts_on <= day:
            current.status = UserOfficeMembership.Status.ACTIVE
            current.save(update_fields=["status", "updated_at"])
        return current

    if current is not None:
        before = {
            "office_id": current.office.pk,
            "status": current.status,
            "ends_on": current.ends_on.isoformat() if current.ends_on else None,
        }
        current.status = UserOfficeMembership.Status.ENDED
        current.ends_on = day
        current.full_clean()
        current.save(update_fields=["status", "ends_on", "updated_at"])
        log_event(
            "user.office_membership.ended",
            actor=actor_from_user(actor) if actor else actor_from_user(locked),
            target=_membership_target(current),
            before=before,
            after={
                "office_id": current.office.pk,
                "status": current.status,
                "ends_on": day.isoformat(),
            },
            metadata={"business_reason": business_reason, "kind": "primary"},
        )

    membership = UserOfficeMembership(
        user=locked,
        office=office,
        kind=UserOfficeMembership.Kind.PRIMARY,
        status=UserOfficeMembership.Status.ACTIVE,
        starts_on=day,
        changed_by=actor,
        business_reason=business_reason,
    )
    membership.full_clean()
    membership.save()
    log_event(
        "user.office_membership.created",
        actor=actor_from_user(actor) if actor else actor_from_user(locked),
        target=_membership_target(membership),
        after={
            "user_id": locked.pk,
            "office_id": office.pk,
            "kind": membership.kind,
            "status": membership.status,
            "starts_on": membership.starts_on.isoformat(),
        },
        office_id=office.stable_key,
        region_id=(office.region.stable_key if office.region else ""),
        metadata={"business_reason": business_reason},
    )
    return membership


@transaction.atomic
def set_primary_office(
    *,
    actor: User,
    user: User,
    office: Office | None,
    effective_on: dt.date | None = None,
    business_reason: str = "",
) -> User:
    """Transfer a user's primary office with history and audit."""
    locked = (
        User.objects.select_for_update(of=("self",))
        .select_related("office", "office__region")
        .get(pk=user.pk)
    )
    if office is not None:
        require_hierarchy_consistent(office)
        if not office.is_active or not office.is_assignable:
            raise ValidationError(
                {"office": _("Pick an active office from the locations we serve.")}
            )
    before = {
        "office_id": locked.office.stable_key if locked.office else None,
    }
    locked.office = office
    locked.full_clean()
    locked.save(update_fields=["office"])
    sync_primary_membership(
        locked,
        actor=actor,
        effective_on=effective_on,
        business_reason=business_reason,
    )
    log_event(
        "user.primary_office.transferred",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(locked.pk),
            target_label=locked.email,
        ),
        before=before,
        after={"office_id": office.stable_key if office else None},
        office_id=office.stable_key if office else "",
        region_id=(office.region.stable_key if office and office.region else ""),
        metadata={"business_reason": business_reason},
    )
    return locked


@transaction.atomic
def grant_secondary_membership(
    *,
    actor: User,
    user: User,
    office: Office,
    starts_on: dt.date | None = None,
    ends_on: dt.date | None = None,
    business_reason: str = "",
) -> UserOfficeMembership:
    """Approve a secondary affiliation without changing primary membership."""
    require_hierarchy_consistent(office)
    if not office.is_active:
        raise ValidationError({"office": _("Cannot assign an inactive office.")})
    day = starts_on or timezone.localdate()
    if ends_on is not None and ends_on < day:
        raise ValidationError({"ends_on": _("End date cannot precede the start date.")})
    if user.office is not None and user.office.pk == office.pk:
        raise ValidationError(
            {"office": _("Secondary membership cannot duplicate the primary office.")}
        )
    if _overlap_exists(
        user=user,
        office=office,
        kind=UserOfficeMembership.Kind.SECONDARY,
        starts_on=day,
        ends_on=ends_on,
    ):
        raise ValidationError(
            {"office": _("An overlapping secondary membership already exists.")}
        )

    membership = UserOfficeMembership(
        user=user,
        office=office,
        kind=UserOfficeMembership.Kind.SECONDARY,
        status=(
            UserOfficeMembership.Status.ACTIVE
            if day <= timezone.localdate()
            else UserOfficeMembership.Status.SCHEDULED
        ),
        starts_on=day,
        ends_on=ends_on,
        changed_by=actor,
        business_reason=business_reason,
    )
    membership.full_clean()
    membership.save()
    log_event(
        "user.office_membership.created",
        actor=actor_from_user(actor),
        target=_membership_target(membership),
        after={
            "user_id": user.pk,
            "office_id": office.pk,
            "kind": membership.kind,
            "status": membership.status,
            "starts_on": membership.starts_on.isoformat(),
            "ends_on": ends_on.isoformat() if ends_on else None,
        },
        office_id=office.stable_key,
        region_id=(office.region.stable_key if office.region else ""),
        metadata={"business_reason": business_reason},
    )
    return membership


@transaction.atomic
def end_secondary_membership(
    *,
    actor: User,
    membership: UserOfficeMembership,
    ends_on: dt.date | None = None,
    business_reason: str = "",
) -> UserOfficeMembership:
    if membership.kind != UserOfficeMembership.Kind.SECONDARY:
        raise ValidationError(_("Only secondary memberships can be ended this way."))
    locked = UserOfficeMembership.objects.select_for_update(of=("self",)).get(
        pk=membership.pk
    )
    if locked.status == UserOfficeMembership.Status.ENDED:
        return locked
    before = {
        "status": locked.status,
        "ends_on": locked.ends_on.isoformat() if locked.ends_on else None,
    }
    locked.status = UserOfficeMembership.Status.ENDED
    locked.ends_on = ends_on or timezone.localdate()
    locked.business_reason = business_reason or locked.business_reason
    locked.changed_by = actor
    locked.full_clean()
    locked.save()
    log_event(
        "user.office_membership.ended",
        actor=actor_from_user(actor),
        target=_membership_target(locked),
        before=before,
        after={
            "status": locked.status,
            "ends_on": locked.ends_on.isoformat() if locked.ends_on else None,
        },
        metadata={"business_reason": business_reason},
    )
    return locked


# ---------------------------------------------------------------------------
# Office restructuring
# ---------------------------------------------------------------------------


def _actor_may_restructure(actor: User) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    from apps.user.services.role_assignments import get_effective_access

    access = get_effective_access(actor)
    return access.company_wide


@transaction.atomic
def transfer_office(
    *,
    actor: User,
    office: Office,
    new_parent: Office,
    business_reason: str = "",
) -> Office:
    """Move an office under a new parent (e.g. region transfer) with audit.

    Only brokerage-wide administrators may restructure. Descendants keep their
    relative parent links; denormalized ``region`` is refreshed on save.
    """
    if not _actor_may_restructure(actor):
        log_event(
            "user.office.transfer.denied",
            actor=actor_from_user(actor),
            target=AuditTarget(
                target_type=Office._meta.label_lower,
                target_id=str(office.pk),
                target_label=office.stable_key,
            ),
            outcome=AuditEvent.Outcome.DENIED,
            reason="not_brokerage_admin",
        )
        raise PermissionDenied(
            _("Only brokerage administrators can restructure regions.")
        )

    locked = (
        Office.objects.select_for_update(of=("self",))
        .select_related("parent", "region")
        .get(pk=office.pk)
    )
    parent = Office.objects.select_for_update(of=("self",)).get(pk=new_parent.pk)
    if locked.kind == Office.Kind.HEAD_OFFICE:
        raise ValidationError({"parent": _("The head office cannot be moved.")})
    before = {
        "parent_id": locked.parent.pk if locked.parent else None,
        "parent_stable_key": locked.parent.stable_key if locked.parent else None,
        "region_id": locked.region.stable_key if locked.region else None,
        "path_label": locked.path_label(),
    }
    locked.parent = parent
    locked.full_clean()
    locked.save()
    # Refresh denormalized region on every descendant after the move.
    for node in descendant_queryset(locked):
        node.save()
    locked.refresh_from_db()
    log_event(
        "user.office.transferred",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=Office._meta.label_lower,
            target_id=str(locked.pk),
            target_label=locked.stable_key,
        ),
        before=before,
        after={
            "parent_id": locked.parent.pk if locked.parent else None,
            "parent_stable_key": locked.parent.stable_key if locked.parent else None,
            "region_id": locked.region.stable_key if locked.region else None,
            "path_label": locked.path_label(),
        },
        office_id=locked.stable_key,
        region_id=(locked.region.stable_key if locked.region else ""),
        metadata={"business_reason": business_reason},
    )
    return locked
