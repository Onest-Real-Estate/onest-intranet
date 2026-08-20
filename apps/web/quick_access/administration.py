"""Quick Access administration: scope, authority, persistence, and audit.

Three questions are answered here and nowhere else, so no view has to re-derive
them:

* **who** may manage which links — capability plus office scope, and the extra
  grant a *company-owned* definition needs;
* **what audience** an administrator may hand out — never a wider one than
  they hold themselves;
* **what happens afterwards** — an audit row carrying before/after values, and
  a cache stamp that retires every reader's cached panel.

The React pages mirror these rules so the person using them is not surprised.
Nothing in the frontend is load-bearing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import Office, User
from apps.user.services.hierarchy import descendant_ids
from apps.user.services.role_assignments import EffectiveAccess, get_effective_access
from apps.web.capability import has_capability
from apps.web.models import (
    QuickAccessLink,
    QuickAccessLinkOfficeAudience,
    QuickAccessLinkRoleAudience,
)
from apps.web.quick_access.resolution import invalidate_on_commit

MANAGE_PERMISSION = "web.manage_quick_access"
MANAGE_COMPANY_PERMISSION = "web.manage_company_quick_access"

#: Fields the administration form owns. Nothing else is writable through it —
#: ``stable_key`` is create-only, and lifecycle flags move through their own
#: endpoint so an activation is never a side effect of an edit.
EDITABLE_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "destination_type",
    "destination_value",
    "icon",
    "sort_order",
    "publish_start_at",
    "publish_end_at",
    "sso_capability",
    "integration_health",
    "setup_behavior",
)

#: Values kept in the audit trail. Every one of them is configuration, not
#: personal data, so the whole set is safe to record verbatim.
AUDIT_FIELDS: tuple[str, ...] = (
    "stable_key",
    *EDITABLE_FIELDS,
    "is_active",
    "is_archived",
    "company_wide",
    "owner_scope",
)


class BroadExposureNotAcknowledged(ValidationError):
    """Raised when a widening change arrives without an explicit confirmation."""

    def __init__(self, changes: list[dict[str, str]]):
        self.changes = changes
        super().__init__(
            _(
                "This change widens who can see the tool. Confirm the new "
                "audience and destination before saving."
            )
        )


class StaleQuickAccessVersion(ValidationError):
    def __init__(self):
        self.message = str(
            _("Somebody else changed this link. Review the current values first.")
        )
        super().__init__(self.message)


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GrantScope:
    """The office nodes an administrator may aim a link at.

    ``company_wide`` short-circuits everything else, exactly as it does in
    ``EffectiveAccess``: a brokerage-wide administrator has no node list to
    check against, and treating an empty list as "nothing" would lock them out
    of their own module.
    """

    company_wide: bool
    office_ids: frozenset[int] = field(default_factory=frozenset)

    @property
    def is_empty(self) -> bool:
        return not (self.company_wide or self.office_ids)

    def covers(self, office_id: int) -> bool:
        return self.company_wide or office_id in self.office_ids


@dataclass(frozen=True)
class ManagementContext:
    """One resolution of the actor's authority, shared across a whole page.

    Both halves are expensive to derive — effective access reads role
    assignments and permissions, and the grant scope walks the office tree — and
    a list page needs the same answer for every row. Resolving once here is what
    keeps the row count off the query count.
    """

    access: EffectiveAccess
    scope: GrantScope


def management_context(actor: User) -> ManagementContext:
    access = get_effective_access(actor)
    return ManagementContext(access=access, scope=grant_scope(actor, access=access))


def grant_scope(actor: User, *, access: EffectiveAccess | None = None) -> GrantScope:
    """Which offices ``actor`` may target, expanded through the office tree.

    A region manager holds a region key; the offices under it are the ones a
    link can actually be aimed at, so the region node *and* its descendants are
    both in scope. The expansion is deliberate: the alternative is an
    administrator who can name a region they manage but none of its branches.
    """
    if getattr(actor, "is_superuser", False):
        return GrantScope(company_wide=True)
    if access is None:
        access = get_effective_access(actor)
    if access.company_wide:
        return GrantScope(company_wide=True)
    keys = set(access.region_keys) | set(access.office_keys)
    if not keys:
        return GrantScope(company_wide=False)
    nodes = list(Office.objects.filter(stable_key__in=sorted(keys)))
    reachable: set[int] = set()
    for node in nodes:
        reachable |= set(descendant_ids(node))
    return GrantScope(company_wide=False, office_ids=frozenset(reachable))


def targetable_office_queryset(
    actor: User, *, scope: GrantScope | None = None
) -> QuerySet[Office]:
    """Offices an administrator may add to an audience, in tree order.

    The parent chain is joined three deep because the picker labels each option
    with ``path_label()``, which walks it — the org tree is head office → region
    → regional office → branch, so three covers the deepest node.
    """
    if scope is None:
        scope = grant_scope(actor)
    base = Office.objects.filter(is_active=True).select_related(
        "parent", "parent__parent", "parent__parent__parent", "region"
    )
    if scope.company_wide:
        return base.order_by("sort_order", "name")
    if not scope.office_ids:
        return base.none()
    return base.filter(pk__in=scope.office_ids).order_by("sort_order", "name")


def manageable_link_queryset(
    actor: User, *, context: ManagementContext | None = None
) -> QuerySet[QuickAccessLink]:
    """Links ``actor`` may open. Company-owned rows need the company grant.

    A scoped administrator sees a link when every office it names is inside
    their own scope. A link that also reaches offices they do not manage is
    not theirs to edit, and is filtered out rather than shown read-only: the
    list is a work queue, not a directory.
    """
    base = QuickAccessLink.objects.select_related("owner_office")
    resolved = management_context(actor) if context is None else context
    if not has_capability(actor, MANAGE_PERMISSION, access=resolved.access):
        return base.none()
    scope = resolved.scope
    if scope.company_wide:
        return base
    if scope.is_empty:
        return base.none()
    return (
        base.filter(owner_scope=QuickAccessLink.OwnerScope.SCOPED, company_wide=False)
        # A link is manageable only when *no* audience row falls outside the
        # actor's scope, so the check is an exclusion of the offending rows
        # rather than a match on the permitted ones.
        .exclude(
            pk__in=QuickAccessLinkOfficeAudience.objects.exclude(
                office_id__in=scope.office_ids
            ).values("link_id")
        )
        # …and it must name at least one office, or "every office it names is
        # in scope" would be vacuously true for a link nobody owns.
        .filter(
            pk__in=QuickAccessLinkOfficeAudience.objects.values("link_id"),
        )
    )


def can_manage(
    actor: User, link: QuickAccessLink, *, context: ManagementContext | None = None
) -> bool:
    """Whether ``actor`` may edit this link.

    ``context`` may be passed in by a caller looping over rows; without it the
    actor's access and scope are re-derived once per row.
    """
    resolved = management_context(actor) if context is None else context
    if not has_capability(actor, MANAGE_PERMISSION, access=resolved.access):
        return False
    if link.owner_scope == QuickAccessLink.OwnerScope.COMPANY or link.company_wide:
        return has_capability(actor, MANAGE_COMPANY_PERMISSION, access=resolved.access)
    scope = resolved.scope
    if scope.company_wide:
        return True
    if scope.is_empty:
        return False
    audience_ids = {row.office_id for row in link.office_audiences.all()}
    return bool(audience_ids) and audience_ids <= set(scope.office_ids)


def _deny(actor: User, *, reason: str, link: QuickAccessLink | None = None) -> None:
    log_event(
        "security.quick_access.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=QuickAccessLink._meta.label_lower,
            target_id=str(link.pk) if link is not None else "",
            target_label=link.stable_key if link is not None else "quick_access",
        ),
        outcome=AuditEvent.Outcome.DENIED,
        source="app",
        channel="quick_access_administration",
        reason=reason,
    )


def ensure_manage_authority(actor: User, link: QuickAccessLink) -> None:
    if not can_manage(actor, link):
        _deny(actor, reason="not_authorized_for_link", link=link)
        raise PermissionDenied("You may not manage this Quick Access link.")


def ensure_can_create(actor: User) -> None:
    if not has_capability(actor, MANAGE_PERMISSION):
        _deny(actor, reason="missing_manage_permission")
        raise PermissionDenied("You may not manage Quick Access links.")
    if grant_scope(actor).is_empty:
        _deny(actor, reason="empty_grant_scope")
        raise PermissionDenied("Your role does not scope you to any office.")


def ensure_audience_within_grant(
    actor: User,
    *,
    company_wide: bool,
    office_ids: list[int],
) -> None:
    """The grant boundary: never hand out visibility you do not hold.

    Checked on the server for every write. The form hides what the actor
    cannot pick, but a hidden option is a courtesy, not a control.
    """
    scope = grant_scope(actor)
    if company_wide and not has_capability(actor, MANAGE_COMPANY_PERMISSION):
        raise ValidationError(
            {"company_wide": _("You may not publish a link to the whole brokerage.")}
        )
    if scope.company_wide:
        return
    outside = [item for item in office_ids if not scope.covers(item)]
    if outside:
        raise ValidationError(
            {"offices": _("You may only target offices inside your own scope.")}
        )
    if not company_wide and not office_ids:
        raise ValidationError(
            {"offices": _("Choose at least one office, or publish company-wide.")}
        )


# --------------------------------------------------------------------------- #
# Snapshots, versioning, and exposure diffs
# --------------------------------------------------------------------------- #


def link_version(link: QuickAccessLink) -> str:
    """Opaque token for optimistic concurrency on the edit form."""
    return link.updated_at.isoformat() if link.updated_at else ""


def audience_snapshot(link: QuickAccessLink) -> dict[str, Any]:
    return {
        "companyWide": link.company_wide,
        "roles": sorted(link.role_audiences.values_list("role_code", flat=True)),
        "offices": sorted(
            link.office_audiences.values_list("office__stable_key", flat=True)
        ),
    }


def prospective_audience(
    *, company_wide: bool, role_codes: list[str], office_ids: list[int]
) -> dict[str, Any]:
    """The audience a submission *would* produce, before anything is written.

    Computed from the request rather than from a saved row so the exposure
    check runs before the write, not as a rollback after it.
    """
    keys = list(
        Office.objects.filter(pk__in=office_ids).values_list("stable_key", flat=True)
    )
    return {
        "companyWide": company_wide,
        "roles": sorted(set(role_codes)),
        "offices": sorted(keys),
    }


def link_snapshot(link: QuickAccessLink) -> dict[str, Any]:
    snapshot: dict[str, Any] = {name: getattr(link, name) for name in AUDIT_FIELDS}
    snapshot["ownerOffice"] = link.owner_office.stable_key if link.owner_office else ""
    snapshot["audience"] = audience_snapshot(link)
    return snapshot


def exposure_changes(
    before: dict[str, Any] | None, after: dict[str, Any]
) -> list[dict[str, str]]:
    """Changes that can put a tool in front of people who could not see it.

    Narrowing changes are not listed: removing an office or deactivating a link
    takes access away, and taking access away does not need a confirmation
    step. Creating a link is itself an exposure, so a create with any audience
    at all is reported.
    """
    changes: list[dict[str, str]] = []
    previous = before or {}
    empty_audience: dict[str, Any] = {
        "companyWide": False,
        "roles": [],
        "offices": [],
    }
    prior_audience = previous.get("audience", empty_audience)
    next_audience = after["audience"]

    if before is None:
        changes.append(
            {
                "label": "New link",
                "from": "Not published",
                "to": _audience_label(next_audience),
                "impact": (
                    "Everyone in this audience gets the launcher on their dashboard."
                ),
            }
        )
        return changes

    moved_destination = previous.get("destination_value") != after.get(
        "destination_value"
    ) or previous.get("destination_type") != after.get("destination_type")
    if moved_destination:
        changes.append(
            {
                "label": "Destination",
                "from": str(previous.get("destination_value") or ""),
                "to": str(after.get("destination_value") or ""),
                "impact": "Everyone who can see this link goes somewhere new.",
            }
        )
    if next_audience["companyWide"] and not prior_audience.get("companyWide"):
        changes.append(
            {
                "label": "Audience",
                "from": _audience_label(prior_audience),
                "to": "Every office in the brokerage",
                "impact": "The link becomes visible brokerage-wide.",
            }
        )
    added_offices = sorted(
        set(next_audience["offices"]) - set(prior_audience.get("offices", []))
    )
    if added_offices:
        changes.append(
            {
                "label": "Offices added",
                "from": _audience_label(prior_audience),
                "to": ", ".join(added_offices),
                "impact": "People in these offices can now see the link.",
            }
        )
    removed_roles = sorted(
        set(prior_audience.get("roles", [])) - set(next_audience["roles"])
    )
    if removed_roles and not next_audience["roles"]:
        changes.append(
            {
                "label": "Role audience removed",
                "from": ", ".join(prior_audience.get("roles", [])),
                "to": "Every role",
                "impact": "The link is no longer limited to specific roles.",
            }
        )
    elif removed_roles:
        changes.append(
            {
                "label": "Role audience widened",
                "from": ", ".join(prior_audience.get("roles", [])),
                "to": ", ".join(next_audience["roles"]),
                "impact": "Roles were removed from the filter, widening who sees it.",
            }
        )
    return changes


def _audience_label(audience: dict[str, Any]) -> str:
    if audience.get("companyWide"):
        base = "Every office"
    else:
        offices = audience.get("offices") or []
        base = ", ".join(offices) if offices else "No office"
    roles = audience.get("roles") or []
    if roles:
        return f"{base} · {', '.join(roles)}"
    return f"{base} · every role"


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #


def _write_audience(
    link: QuickAccessLink, *, role_codes: list[str], office_ids: list[int]
) -> None:
    link.role_audiences.exclude(role_code__in=role_codes).delete()
    existing_roles = set(link.role_audiences.values_list("role_code", flat=True))
    QuickAccessLinkRoleAudience.objects.bulk_create(
        [
            QuickAccessLinkRoleAudience(link=link, role_code=code)
            for code in role_codes
            if code not in existing_roles
        ]
    )
    link.office_audiences.exclude(office_id__in=office_ids).delete()
    existing_offices = set(link.office_audiences.values_list("office_id", flat=True))
    QuickAccessLinkOfficeAudience.objects.bulk_create(
        [
            QuickAccessLinkOfficeAudience(link=link, office_id=office_id)
            for office_id in office_ids
            if office_id not in existing_offices
        ]
    )


def _log(
    action: str,
    *,
    actor: User,
    link: QuickAccessLink,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    log_event(
        action,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=QuickAccessLink._meta.label_lower,
            target_id=str(link.pk),
            target_label=link.stable_key,
        ),
        before=before,
        after=after,
        office_id=link.owner_office.stable_key if link.owner_office else "",
        source="app",
        channel="quick_access_administration",
        metadata=metadata,
    )


def create_link(*, actor: User, **kwargs: Any) -> QuickAccessLink:
    """Authorize outside the transaction, then write inside it.

    Same split as :func:`update_link`: a denial audited inside ``atomic`` would
    be rolled back along with the refused write.
    """
    ensure_can_create(actor)
    return _create_link(actor=actor, **kwargs)


@transaction.atomic
def _create_link(
    *,
    actor: User,
    cleaned: dict[str, Any],
    role_codes: list[str],
    office_ids: list[int],
    company_wide: bool,
    acknowledged: bool,
) -> QuickAccessLink:
    ensure_can_create(actor)
    ensure_audience_within_grant(
        actor, company_wide=company_wide, office_ids=office_ids
    )

    changes = exposure_changes(
        None,
        {
            "audience": prospective_audience(
                company_wide=company_wide,
                role_codes=role_codes,
                office_ids=office_ids,
            )
        },
    )
    if changes and not acknowledged:
        raise BroadExposureNotAcknowledged(changes)

    # A company-wide link is the company's; anything narrower stays scoped
    # even when a brokerage-wide administrator created it, so the office it
    # targets can go on maintaining it.
    owner_scope = (
        QuickAccessLink.OwnerScope.COMPANY
        if company_wide
        else QuickAccessLink.OwnerScope.SCOPED
    )
    link = QuickAccessLink(
        stable_key=cleaned["stable_key"],
        company_wide=company_wide,
        owner_scope=owner_scope,
        owner_office_id=office_ids[0] if office_ids else None,
        is_active=cleaned.get("is_active", True),
        created_by=actor,
        updated_by=actor,
        **{name: cleaned[name] for name in EDITABLE_FIELDS if name in cleaned},
    )
    link.full_clean(exclude=["owner_office"])
    link.save()
    _write_audience(link, role_codes=role_codes, office_ids=office_ids)

    _log(
        "web.quick_access.created",
        actor=actor,
        link=link,
        before=None,
        after=link_snapshot(link),
    )
    invalidate_on_commit()
    return link


def update_link(
    *, actor: User, link: QuickAccessLink, **kwargs: Any
) -> QuickAccessLink:
    """Authorize outside the transaction, then write inside it.

    The denial audit is the reason for the split: a ``PermissionDenied`` raised
    inside ``atomic`` rolls the transaction back, and the audit row with it. The
    locked row is re-checked in :func:`_update_link` so a scope change that
    lands between the two checks still loses.
    """
    ensure_manage_authority(actor, link)
    return _update_link(actor=actor, link=link, **kwargs)


@transaction.atomic
def _update_link(
    *,
    actor: User,
    link: QuickAccessLink,
    cleaned: dict[str, Any],
    role_codes: list[str],
    office_ids: list[int],
    company_wide: bool,
    expected_version: str,
    acknowledged: bool,
) -> QuickAccessLink:
    locked = (
        QuickAccessLink.objects.select_for_update()
        .select_related("owner_office")
        .get(pk=link.pk)
    )
    ensure_manage_authority(actor, locked)
    if link_version(locked) != (expected_version or ""):
        raise StaleQuickAccessVersion()
    ensure_audience_within_grant(
        actor, company_wide=company_wide, office_ids=office_ids
    )

    before = link_snapshot(locked)
    changes = exposure_changes(
        before,
        {
            **{
                name: cleaned.get(name, getattr(locked, name))
                for name in EDITABLE_FIELDS
            },
            "audience": prospective_audience(
                company_wide=company_wide,
                role_codes=role_codes,
                office_ids=office_ids,
            ),
        },
    )
    if changes and not acknowledged:
        raise BroadExposureNotAcknowledged(changes)

    for name in EDITABLE_FIELDS:
        if name in cleaned:
            setattr(locked, name, cleaned[name])
    locked.company_wide = company_wide
    locked.owner_scope = (
        QuickAccessLink.OwnerScope.COMPANY
        if company_wide
        else QuickAccessLink.OwnerScope.SCOPED
    )
    locked.owner_office_id = office_ids[0] if office_ids else None
    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office"])
    locked.save()
    _write_audience(locked, role_codes=role_codes, office_ids=office_ids)

    after = link_snapshot(locked)
    _log(
        "web.quick_access.updated",
        actor=actor,
        link=locked,
        before=before,
        after=after,
    )
    if before["audience"] != after["audience"]:
        _log(
            "web.quick_access.audience_changed",
            actor=actor,
            link=locked,
            before={"audience": before["audience"]},
            after={"audience": after["audience"]},
        )
    invalidate_on_commit()
    return locked


def set_link_state(
    *, actor: User, link: QuickAccessLink, action: str
) -> QuickAccessLink:
    """Activate, deactivate, archive, or restore one link.

    Authorized before the transaction opens, so a denial leaves an audit row
    behind rather than rolling one back. See :func:`update_link`.
    """
    ensure_manage_authority(actor, link)
    return _set_link_state(actor=actor, link=link, action=action)


@transaction.atomic
def _set_link_state(
    *, actor: User, link: QuickAccessLink, action: str
) -> QuickAccessLink:
    """Apply one lifecycle transition to the locked row.

    Lifecycle lives apart from the edit form so a routine copy change can never
    quietly publish a link, and so the audit trail names what happened instead
    of hiding it inside a field diff.
    """
    locked = QuickAccessLink.objects.select_for_update().get(pk=link.pk)
    ensure_manage_authority(actor, locked)
    before = link_snapshot(locked)

    if action == "activate":
        locked.is_active = True
        locked.is_archived = False
        locked.archived_at = None
    elif action == "deactivate":
        locked.is_active = False
    elif action == "archive":
        locked.is_archived = True
        locked.is_active = False
        locked.archived_at = timezone.now()
    elif action == "restore":
        locked.is_archived = False
        locked.archived_at = None
    else:
        raise ValidationError({"action": _("Unsupported action.")})

    locked.updated_by = actor
    locked.full_clean(exclude=["owner_office"])
    locked.save()
    after = link_snapshot(locked)
    _log(
        "web.quick_access.archived"
        if action in {"archive", "restore"}
        else "web.quick_access.activation_changed",
        actor=actor,
        link=locked,
        before=before,
        after=after,
        metadata={"action": action},
    )
    invalidate_on_commit()
    return locked


def reorder_links(*, actor: User, link_ids: list[int]) -> list[QuickAccessLink]:
    """Authorize every submitted link, then rewrite the order in one transaction."""
    for link in QuickAccessLink.objects.filter(pk__in=link_ids):
        ensure_manage_authority(actor, link)
    return _reorder_links(actor=actor, link_ids=link_ids)


@transaction.atomic
def _reorder_links(*, actor: User, link_ids: list[int]) -> list[QuickAccessLink]:
    """Rewrite the panel order without touching links the actor cannot manage.

    The submitted links keep the *positions* they already occupied — their
    ``sort_order`` values are collected, sorted, and handed back out in the new
    sequence. A company-owned link interleaved between two office links keeps
    its own position, and an office administrator reordering their three links
    cannot move it. Ties are separated as they are redistributed, so a routine
    drag never needs the whole table renumbered.
    """
    if not link_ids:
        raise ValidationError({"order": _("Send the new order.")})
    if len(set(link_ids)) != len(link_ids):
        raise ValidationError({"order": _("The order repeats a link.")})

    locked = {
        link.pk: link
        for link in QuickAccessLink.objects.select_for_update().filter(pk__in=link_ids)
    }
    if len(locked) != len(link_ids):
        raise ValidationError({"order": _("That order names a link that is gone.")})

    ordered = [locked[pk] for pk in link_ids]
    for link in ordered:
        ensure_manage_authority(actor, link)

    slots: list[int] = []
    previous: int | None = None
    for slot in sorted(link.sort_order for link in ordered):
        if previous is not None and slot <= previous:
            slot = previous + 1
        slots.append(slot)
        previous = slot

    previous_order = sorted(
        ordered, key=lambda item: (item.sort_order, item.name, item.pk)
    )
    before = {"order": [link.stable_key for link in previous_order]}
    for link, slot in zip(ordered, slots, strict=True):
        link.sort_order = slot
        link.updated_by = actor
    QuickAccessLink.objects.bulk_update(ordered, ["sort_order", "updated_by"])

    after = {"order": [link.stable_key for link in ordered]}
    log_event(
        "web.quick_access.reordered",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=QuickAccessLink._meta.label_lower,
            target_label="quick_access_order",
        ),
        before=before,
        after=after,
        source="app",
        channel="quick_access_administration",
    )
    invalidate_on_commit()
    return ordered
