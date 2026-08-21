"""Dedicated role-assignment administration: list, workspace, preview, mutate.

The assignment service in :mod:`apps.user.services.role_assignments` owns
delegation, dates, duplicates, and audit. This module is the product surface
on top: which people an actor with ``web.assign_user_roles`` may reach, what
the workspace renders, and the dry-run preview that must match post-save
access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Max, Q, QuerySet

from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import (
    MANAGEMENT_ROLE_KEYS,
    ROLE_BY_KEY,
    ROLE_DEFINITIONS,
    ROLE_LABELS,
    ScopeType,
    is_valid_scope_type,
    normalize_role_code,
    role_assignment_block_reason,
)
from apps.user.services.agent_administration import (
    administered_user_queryset,
    ensure_office_delegable,
    ensure_revocation_leaves_valid_access,
    invalidate_permission_cache,
    scope_target_queryset,
    would_strip_last_live_assignment,
)
from apps.user.services.role_assignments import (
    EffectiveAccess,
    actor_can_manage_assignments,
    create_role_assignment,
    get_effective_access,
    revoke_role_assignment,
    update_role_assignment,
)
from apps.web.contracts import list_response
from apps.web.operations import OPERATIONS_DESTINATIONS

ASSIGN_PERMISSION = "web.assign_user_roles"
PAGE_SIZE = 25

LIVE_STATUSES = (
    UserRoleAssignment.Status.SCHEDULED,
    UserRoleAssignment.Status.ACTIVE,
)


class StaleRoleAssignmentVersion(Exception):
    message = (
        "This person's role assignments changed since you loaded the page. "
        "Review the current values and try again."
    )


# ---------------------------------------------------------------------------
# Access snapshots (shared by preview and post-save)
# ---------------------------------------------------------------------------


def _access_snapshot(access: EffectiveAccess) -> dict[str, Any]:
    if access.company_wide:
        scope_label = "Brokerage-wide"
    elif access.region_keys:
        scope_label = ", ".join(
            Office.objects.filter(stable_key__in=sorted(access.region_keys))
            .order_by("sort_order", "name")
            .values_list("name", flat=True)
        )
    elif access.office_keys:
        scope_label = ", ".join(
            Office.objects.filter(stable_key__in=sorted(access.office_keys))
            .order_by("sort_order", "name")
            .values_list("name", flat=True)
        )
    elif access.assigned_record:
        scope_label = "Assigned records only"
    else:
        scope_label = "No administrative scope"
    return {
        "roles": [ROLE_LABELS.get(key, key) for key in access.role_keys],
        "roleKeys": list(access.role_keys),
        "permissions": sorted(access.permissions),
        "scopeLabel": scope_label,
        "companyWide": access.company_wide,
        "assignedRecord": access.assigned_record,
        "liveAssignments": len(access.assignments),
    }


def _navigation_keys(permissions: set[str] | frozenset[str]) -> list[dict[str, str]]:
    return [
        {
            "key": destination.key,
            "label": destination.label,
            "section": destination.section,
        }
        for destination in OPERATIONS_DESTINATIONS
        if destination.permission in permissions
    ]


def access_delta(
    *,
    before: EffectiveAccess,
    after: EffectiveAccess,
) -> dict[str, Any]:
    """Permission and navigation delta between two effective-access states."""
    before_perms = set(before.permissions)
    after_perms = set(after.permissions)
    added = sorted(after_perms - before_perms)
    removed = sorted(before_perms - after_perms)
    before_nav = {row["key"]: row for row in _navigation_keys(before_perms)}
    after_nav = {row["key"]: row for row in _navigation_keys(after_perms)}
    return {
        "before": _access_snapshot(before),
        "after": _access_snapshot(after),
        "permissionDelta": {"added": added, "removed": removed},
        "navigationDelta": {
            "added": [
                after_nav[key] for key in sorted(set(after_nav) - set(before_nav))
            ],
            "removed": [
                before_nav[key] for key in sorted(set(before_nav) - set(after_nav))
            ],
        },
    }


def _hypothetical_access(
    user: User,
    *,
    assignments: list[UserRoleAssignment],
) -> EffectiveAccess:
    """Resolve effective access as if ``assignments`` were the live set.

    Uses the same helpers as the live path, but skips status sync writes by
    passing the assignment list explicitly.
    """
    from apps.user.services.role_assignments import (
        get_effective_permissions,
        get_effective_role_keys,
    )
    from apps.web.permission_catalog import filter_to_catalog

    live = tuple(
        item
        for item in assignments
        if item.status in LIVE_STATUSES and item.is_effective()
    )
    # Rebuild EffectiveAccess the same way get_effective_access does, without
    # touching the database status rows.
    role_keys = tuple(get_effective_role_keys(user, assignments=live))
    permissions = filter_to_catalog(get_effective_permissions(user, assignments=live))
    region_keys: set[str] = set()
    office_keys: set[str] = set()
    company_wide = False
    assigned_record = False
    from apps.user.roles import ADMIN, BRANCH_MANAGER, REGION_MANAGER
    from apps.user.services.hierarchy import is_hierarchy_consistent

    for assignment in live:
        if assignment.scope_type == ScopeType.ASSIGNED_RECORD:
            assigned_record = True
            continue
        if assignment.scope_type == ScopeType.COMPANY:
            company_wide = True
            continue
        if assignment.scope_office is None:
            continue
        if not is_hierarchy_consistent(assignment.scope_office):
            continue
        if assignment.scope_type == ScopeType.REGION:
            region_keys.add(assignment.scope_office.stable_key)
        if assignment.scope_type == ScopeType.OFFICE:
            office_keys.add(assignment.scope_office.stable_key)
    if not live:
        office = getattr(user, "office", None)
        if ADMIN in role_keys:
            company_wide = True
        if office is not None and is_hierarchy_consistent(office):
            if BRANCH_MANAGER in role_keys:
                office_keys.add(office.stable_key)
            if REGION_MANAGER in role_keys and office.region is not None:
                region_keys.add(office.region.stable_key)
    return EffectiveAccess(
        assignments=live,
        role_keys=role_keys,
        permissions=permissions,
        region_keys=frozenset(region_keys),
        office_keys=frozenset(office_keys),
        company_wide=company_wide,
        assigned_record=assigned_record,
    )


def _all_assignments(user: User) -> list[UserRoleAssignment]:
    return list(
        UserRoleAssignment.objects.filter(user=user)
        .select_related(
            "scope_office",
            "scope_office__region",
            "assigned_by",
            "revoked_by",
        )
        .order_by("role", "-created_at")
    )


def grant_version(user: User) -> str:
    """Concurrency token for creating a new assignment on this user."""
    latest = (
        UserRoleAssignment.objects.filter(user=user)
        .aggregate(latest=Max("updated_at"))
        .get("latest")
    )
    return latest.isoformat() if latest else "0"


def assignment_version(assignment: UserRoleAssignment) -> str:
    return assignment.updated_at.isoformat() if assignment.updated_at else "0"


# ---------------------------------------------------------------------------
# Role / scope options (delegable + blocked with reasons)
# ---------------------------------------------------------------------------


def role_scope_options(actor: User) -> list[dict[str, Any]]:
    """Every catalog role with scopes and why unavailable ones are blocked."""
    access = get_effective_access(actor)
    scope_labels = dict(ScopeType.CHOICES)
    office_probe = (
        scope_target_queryset(actor)
        .filter(kind__in=[Office.Kind.BRANCH, Office.Kind.REGIONAL_OFFICE])
        .first()
    )
    region_probe = scope_target_queryset(actor).filter(kind=Office.Kind.REGION).first()
    options: list[dict[str, Any]] = []
    for definition in ROLE_DEFINITIONS:
        block = role_assignment_block_reason(
            definition.code, actor_is_superuser=bool(actor.is_superuser)
        )
        scopes: list[dict[str, Any]] = []
        for scope_type in definition.valid_scope_types:
            reason: str | None = block
            available = False
            if block is None:
                if scope_type == ScopeType.COMPANY:
                    available = actor_can_manage_assignments(
                        actor,
                        role=definition.code,
                        target_scope_type=scope_type,
                        scope_office=None,
                        access=access,
                    )
                    if not available:
                        reason = "Company-wide grants require brokerage-wide reach."
                elif scope_type == ScopeType.ASSIGNED_RECORD:
                    probe = office_probe
                    available = actor_can_manage_assignments(
                        actor,
                        role=definition.code,
                        target_scope_type=scope_type,
                        scope_office=probe,
                        access=access,
                    )
                    if not available:
                        reason = (
                            "Assigned-record grants require office reach over "
                            "the person's workplace."
                        )
                elif scope_type == ScopeType.REGION:
                    available = (
                        region_probe is not None
                        and actor_can_manage_assignments(
                            actor,
                            role=definition.code,
                            target_scope_type=scope_type,
                            scope_office=region_probe,
                            access=access,
                        )
                    )
                    if not available:
                        reason = "You cannot grant region scope inside your own reach."
                else:
                    available = (
                        office_probe is not None
                        and actor_can_manage_assignments(
                            actor,
                            role=definition.code,
                            target_scope_type=scope_type,
                            scope_office=office_probe,
                            access=access,
                        )
                    )
                    if not available:
                        reason = "You cannot grant office scope inside your own reach."
            scopes.append(
                {
                    "value": scope_type,
                    "label": scope_labels[scope_type],
                    "available": available,
                    "unavailableReason": None if available else reason,
                }
            )
        any_available = any(scope["available"] for scope in scopes)
        options.append(
            {
                "value": definition.code,
                "label": definition.label,
                "description": definition.description,
                "protected": definition.protected,
                "available": any_available,
                "unavailableReason": (
                    block
                    if block
                    else (
                        None
                        if any_available
                        else "No scope for this role falls inside your delegation."
                    )
                ),
                "scopes": scopes,
            }
        )
    return options


def _assignment_access_summary(assignment: UserRoleAssignment) -> dict[str, Any]:
    """What a single assignment contributes on its own (role permissions + scope)."""
    code = normalize_role_code(assignment.role) or assignment.role
    definition = ROLE_BY_KEY.get(code)
    permissions: list[str] = []
    if definition is not None:
        permissions = sorted(definition.default_permissions)
    return {
        "roleLabel": ROLE_LABELS.get(code, assignment.role),
        "scopeLabel": assignment.scope_label(),
        "permissions": permissions,
        "orgReach": (
            "Brokerage-wide"
            if assignment.scope_type == ScopeType.COMPANY
            else (
                "Assigned records only"
                if assignment.scope_type == ScopeType.ASSIGNED_RECORD
                else assignment.scope_label()
            )
        ),
    }


def _assignment_payload(
    assignment: UserRoleAssignment,
    *,
    actor: User,
    access: EffectiveAccess,
) -> dict[str, Any]:
    code = normalize_role_code(assignment.role) or assignment.role
    can_manage = (
        assignment.role in ROLE_BY_KEY
        and assignment.status in LIVE_STATUSES
        and actor_can_manage_assignments(
            actor,
            role=assignment.role,
            target_scope_type=assignment.scope_type,
            scope_office=(
                assignment.scope_office
                if assignment.scope_type != ScopeType.ASSIGNED_RECORD
                else assignment.user.office
            ),
            access=access,
        )
    )
    return {
        "id": assignment.pk,
        "role": code,
        "roleLabel": ROLE_LABELS.get(code, assignment.role),
        "roleDescription": (
            ROLE_BY_KEY[code].description if code in ROLE_BY_KEY else ""
        ),
        "scopeType": assignment.scope_type,
        "scopeLabel": assignment.scope_label(),
        "scopeOfficeId": (
            assignment.scope_office.pk if assignment.scope_office else None
        ),
        "status": assignment.status,
        "startsAt": assignment.starts_at.isoformat() if assignment.starts_at else None,
        "endsAt": assignment.ends_at.isoformat() if assignment.ends_at else None,
        "assignedBy": str(assignment.assigned_by) if assignment.assigned_by else None,
        "revokedBy": str(assignment.revoked_by) if assignment.revoked_by else None,
        "revokedAt": (
            assignment.revoked_at.isoformat() if assignment.revoked_at else None
        ),
        "businessReason": assignment.business_reason,
        "version": assignment_version(assignment),
        "canEdit": can_manage,
        "canRevoke": can_manage,
        "access": _assignment_access_summary(assignment),
        "isLastLive": would_strip_last_live_assignment(
            assignment.user, assignment=assignment
        ),
        "isManagement": code in MANAGEMENT_ROLE_KEYS,
    }


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssignmentListFilters:
    q: str = ""
    role: str = ""
    status: str = ""
    office: int | None = None
    region: int | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "q": self.q,
            "role": self.role,
            "status": self.status,
            "office": "" if self.office is None else str(self.office),
            "region": "" if self.region is None else str(self.region),
        }


def parse_list_filters(params) -> AssignmentListFilters:
    q = (params.get("q") or "").strip()[:200]
    role = (params.get("role") or "").strip()
    if role and normalize_role_code(role) is None:
        role = ""
    status = (params.get("status") or "").strip()
    allowed_status = {choice.value for choice in UserRoleAssignment.Status}
    if status and status not in allowed_status:
        status = ""
    office = None
    region = None
    try:
        raw_office = (params.get("office") or "").strip()
        if raw_office:
            office = int(raw_office)
    except ValueError:
        office = None
    try:
        raw_region = (params.get("region") or "").strip()
        if raw_region:
            region = int(raw_region)
    except ValueError:
        region = None
    return AssignmentListFilters(
        q=q, role=role, status=status, office=office, region=region
    )


def _apply_list_filters(
    queryset: QuerySet[User], filters: AssignmentListFilters
) -> QuerySet[User]:
    if filters.q:
        queryset = queryset.filter(
            Q(email__icontains=filters.q)
            | Q(first_name__icontains=filters.q)
            | Q(last_name__icontains=filters.q)
            | Q(preferred_name__icontains=filters.q)
        )
    if filters.office is not None:
        queryset = queryset.filter(office_id=filters.office)
    if filters.region is not None:
        queryset = queryset.filter(
            Q(office_id=filters.region) | Q(office__region_id=filters.region)
        )
    if filters.role:
        queryset = queryset.filter(
            role_assignments__role=filters.role,
            role_assignments__status__in=LIVE_STATUSES,
        )
    if filters.status:
        queryset = queryset.filter(role_assignments__status=filters.status)
    return queryset.distinct()


def build_assignment_list(
    actor: User,
    *,
    filters: AssignmentListFilters,
    page: int = 1,
) -> dict[str, Any]:
    base = administered_user_queryset(actor).select_related("office", "office__region")
    filtered = _apply_list_filters(base, filters)
    total = filtered.count()
    page = max(1, page)
    start = (page - 1) * PAGE_SIZE
    users = list(
        filtered.order_by("last_name", "first_name", "email")[start : start + PAGE_SIZE]
    )
    # Prefetch assignments for the page only.
    assignment_map: dict[int, list[UserRoleAssignment]] = {
        user.pk: [] for user in users
    }
    if users:
        for assignment in (
            UserRoleAssignment.objects.filter(user_id__in=assignment_map)
            .select_related("scope_office", "user")
            .order_by("role", "-created_at")
        ):
            assignment_map[assignment.user.pk].append(assignment)

    rows = []
    for user in users:
        assignments = assignment_map.get(user.pk, [])
        live = [item for item in assignments if item.status in LIVE_STATUSES]
        active = UserRoleAssignment.Status.ACTIVE
        counts = {
            "active": sum(1 for item in assignments if item.status == active),
            "scheduled": sum(
                1
                for item in assignments
                if item.status == UserRoleAssignment.Status.SCHEDULED
            ),
            "expired": sum(
                1
                for item in assignments
                if item.status == UserRoleAssignment.Status.EXPIRED
            ),
            "revoked": sum(
                1
                for item in assignments
                if item.status == UserRoleAssignment.Status.REVOKED
            ),
        }
        rows.append(
            {
                "id": user.pk,
                "email": user.email,
                "displayName": str(user),
                "isActive": user.is_active,
                "isSelf": actor.pk == user.pk,
                "office": (
                    {
                        "id": user.office.pk,
                        "name": user.office.name,
                        "pathLabel": user.office.path_label(),
                    }
                    if user.office
                    else None
                ),
                "liveRoles": [
                    {
                        "role": normalize_role_code(item.role) or item.role,
                        "roleLabel": ROLE_LABELS.get(
                            normalize_role_code(item.role) or item.role, item.role
                        ),
                        "scopeLabel": item.scope_label(),
                        "status": item.status,
                    }
                    for item in live
                ],
                "counts": counts,
            }
        )

    role_options = [
        {"value": definition.code, "label": definition.label}
        for definition in ROLE_DEFINITIONS
    ]
    offices = [
        {
            "id": office.pk,
            "name": office.name,
            "pathLabel": office.path_label(),
            "kind": office.kind,
        }
        for office in scope_target_queryset(actor).order_by("sort_order", "name")[:200]
    ]
    return {
        "users": list_response(
            rows,
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters.as_payload(),
        ),
        "filterOptions": {
            "roles": role_options,
            "statuses": [
                {"value": choice.value, "label": choice.label}
                for choice in UserRoleAssignment.Status
            ],
            "offices": offices,
        },
        "scope": _actor_scope_payload(actor),
    }


def _actor_scope_payload(actor: User) -> dict[str, str]:
    from apps.web.operations import operations_scope_payload

    scope = operations_scope_payload(actor)
    return {"level": scope["level"], "label": scope["label"]}


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


def workspace_payload(actor: User, target: User) -> dict[str, Any]:
    access = get_effective_access(actor)
    target_access = get_effective_access(target)
    assignments = [
        _assignment_payload(item, actor=actor, access=access)
        for item in _all_assignments(target)
    ]
    offices = [
        {
            "id": office.pk,
            "name": office.name,
            "pathLabel": office.path_label(),
            "kind": office.kind,
            "regionName": office.region_name(),
        }
        for office in scope_target_queryset(actor).order_by("sort_order", "name")
    ]
    can_mutate = actor.pk != target.pk and any(
        option["available"] for option in role_scope_options(actor)
    )
    return {
        "subject": {
            "id": target.pk,
            "email": target.email,
            "displayName": str(target),
            "isActive": target.is_active,
            "isSelf": actor.pk == target.pk,
            "office": (
                {
                    "id": target.office.pk,
                    "name": target.office.name,
                    "pathLabel": target.office.path_label(),
                }
                if target.office
                else None
            ),
            "agentStatus": target.agent_status,
        },
        "assignments": assignments,
        "effectiveAccess": _access_snapshot(target_access),
        "grantVersion": grant_version(target),
        "options": {
            "roles": role_scope_options(actor),
            "offices": offices,
        },
        "editable": can_mutate,
        "administrationHref": f"/operations/users/{target.pk}/administration",
    }


# ---------------------------------------------------------------------------
# Preview + mutations
# ---------------------------------------------------------------------------


def _high_impact_for_grant(
    *,
    role: str,
    scope_type: str,
    target: User,
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    code = normalize_role_code(role) or role
    label = ROLE_LABELS.get(code, role)
    if scope_type == ScopeType.COMPANY:
        changes.append(
            {
                "label": "Company-wide reach",
                "from": "Current scope",
                "to": "Brokerage-wide",
                "impact": (
                    f"Granting {label} company-wide lets this person reach every "
                    "office the hub knows about."
                ),
            }
        )
    if code in MANAGEMENT_ROLE_KEYS:
        changes.append(
            {
                "label": "Management role",
                "from": "No management grant",
                "to": label,
                "impact": (
                    f"{label} can administer people and roles. Confirm this is "
                    "intentional."
                ),
            }
        )
    definition = ROLE_BY_KEY.get(code)
    if definition is not None and definition.protected:
        changes.append(
            {
                "label": "Protected role",
                "from": "—",
                "to": label,
                "impact": "Protected roles are heavily audited and rarely delegated.",
            }
        )
    return changes


def _high_impact_for_revoke(
    *,
    target: User,
    assignment: UserRoleAssignment,
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    if would_strip_last_live_assignment(target, assignment=assignment):
        changes.append(
            {
                "label": "Last live role",
                "from": assignment.scope_label(),
                "to": "No live assignments",
                "impact": (
                    "Revoking this removes their only live role. Engaged agents "
                    "cannot be left without a replacement."
                ),
            }
        )
    code = normalize_role_code(assignment.role) or assignment.role
    if code in MANAGEMENT_ROLE_KEYS:
        changes.append(
            {
                "label": "Management access",
                "from": ROLE_LABELS.get(code, assignment.role),
                "to": "Revoked",
                "impact": "They lose management capabilities from this assignment.",
            }
        )
    return changes


def preview_grant(
    *,
    actor: User,
    target: User,
    role: str,
    scope_type: str,
    scope_office: Office | None,
    starts_at=None,
    ends_at=None,
) -> dict[str, Any]:
    _ensure_assign_authority(actor, target)
    code = normalize_role_code(role)
    if code is None:
        raise ValidationError({"role": "Unsupported role."})
    if not is_valid_scope_type(code, scope_type):
        raise ValidationError({"scope_type": "This role cannot use that scope."})
    if scope_type in ScopeType.ORG_LESS:
        scope_office = None
    before = get_effective_access(target)
    # Build a transient assignment for the hypothetical set.
    draft = UserRoleAssignment(
        user=target,
        role=code,
        scope_type=scope_type,
        scope_office=scope_office,
        starts_at=starts_at,
        ends_at=ends_at,
        status=UserRoleAssignment.Status.ACTIVE,
    )
    draft.refresh_status()
    existing = _all_assignments(target)
    after = _hypothetical_access(target, assignments=[*existing, draft])
    delta = access_delta(before=before, after=after)
    high_impact = _high_impact_for_grant(
        role=code, scope_type=scope_type, target=target
    )
    return {
        **delta,
        "highImpact": high_impact,
        "requiresConfirmation": bool(high_impact),
        "warnings": [],
    }


def preview_revoke(
    *,
    actor: User,
    target: User,
    assignment: UserRoleAssignment,
) -> dict[str, Any]:
    _ensure_assign_authority(actor, target)
    if assignment.user.pk != target.pk:
        raise PermissionDenied("That assignment does not belong to this user.")
    before = get_effective_access(target)
    remaining = [item for item in _all_assignments(target) if item.pk != assignment.pk]
    after = _hypothetical_access(target, assignments=remaining)
    delta = access_delta(before=before, after=after)
    high_impact = _high_impact_for_revoke(target=target, assignment=assignment)
    warnings: list[str] = []
    try:
        ensure_revocation_leaves_valid_access(target, assignment=assignment)
    except ValidationError as exc:
        warnings.extend(exc.messages)
    return {
        **delta,
        "highImpact": high_impact,
        "requiresConfirmation": bool(high_impact) or bool(warnings),
        "warnings": warnings,
    }


def preview_edit(
    *,
    actor: User,
    target: User,
    assignment: UserRoleAssignment,
    starts_at=None,
    ends_at=None,
) -> dict[str, Any]:
    _ensure_assign_authority(actor, target)
    if assignment.user.pk != target.pk:
        raise PermissionDenied("That assignment does not belong to this user.")
    before = get_effective_access(target)
    others = [item for item in _all_assignments(target) if item.pk != assignment.pk]
    draft = UserRoleAssignment(
        pk=assignment.pk,
        user=target,
        role=assignment.role,
        scope_type=assignment.scope_type,
        scope_office=assignment.scope_office,
        starts_at=starts_at,
        ends_at=ends_at,
        status=assignment.status,
        revoked_at=assignment.revoked_at,
    )
    draft.refresh_status()
    after = _hypothetical_access(target, assignments=[*others, draft])
    delta = access_delta(before=before, after=after)
    return {
        **delta,
        "highImpact": [],
        "requiresConfirmation": False,
        "warnings": [],
    }


def _ensure_assign_authority(actor: User, target: User) -> None:
    """Reach + capability for the dedicated assignment surface.

    Reuses administrative scope (same people the actor can see) and requires
    ``web.assign_user_roles``. Self-assignment is refused here too.
    """
    if actor.pk == target.pk:
        raise PermissionDenied("Users cannot modify their own role assignments.")
    from apps.user.services.role_assignments import has_effective_permission

    if not has_effective_permission(actor, ASSIGN_PERMISSION) and not (
        actor.is_superuser
    ):
        raise PermissionDenied("You cannot assign user roles.")
    # Same scope boundary as administration — out-of-scope is the caller's job
    # to 404 before reaching here.
    if not administered_user_queryset(actor).filter(pk=target.pk).exists():
        raise PermissionDenied("That user is outside your administrative scope.")


def admin_grant_assignment(
    *,
    actor: User,
    target: User,
    role: str,
    scope_type: str,
    scope_office: Office | None,
    starts_at=None,
    ends_at=None,
    business_reason: str,
    expected_version: str,
    confirmed: bool = False,
) -> UserRoleAssignment:
    _ensure_assign_authority(actor, target)
    if grant_version(target) != (expected_version or ""):
        raise StaleRoleAssignmentVersion()
    high_impact = _high_impact_for_grant(
        role=role, scope_type=scope_type, target=target
    )
    if high_impact and not confirmed:
        raise ValidationError(
            {
                "__all__": (
                    "This grant is high-impact. Confirm the preview before saving."
                )
            }
        )
    if scope_office is not None and scope_type not in ScopeType.ORG_LESS:
        ensure_office_delegable(actor, scope_office)
    assignment = create_role_assignment(
        actor=actor,
        target_user=target,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
        starts_at=starts_at,
        ends_at=ends_at,
        business_reason=business_reason,
    )
    invalidate_permission_cache(target)
    return assignment


def admin_edit_assignment(
    *,
    actor: User,
    target: User,
    assignment: UserRoleAssignment,
    starts_at=None,
    ends_at=None,
    business_reason: str,
    expected_version: str,
) -> UserRoleAssignment:
    _ensure_assign_authority(actor, target)
    if assignment.user.pk != target.pk:
        raise PermissionDenied("That assignment does not belong to this user.")
    if assignment_version(assignment) != (expected_version or ""):
        raise StaleRoleAssignmentVersion()
    updated = update_role_assignment(
        actor=actor,
        assignment=assignment,
        starts_at=starts_at,
        ends_at=ends_at,
        business_reason=business_reason,
    )
    invalidate_permission_cache(target)
    return updated


def admin_revoke_assignment(
    *,
    actor: User,
    target: User,
    assignment: UserRoleAssignment,
    business_reason: str,
    expected_version: str,
    confirmed: bool = False,
) -> UserRoleAssignment:
    _ensure_assign_authority(actor, target)
    if assignment.user.pk != target.pk:
        raise PermissionDenied("That assignment does not belong to this user.")
    if assignment_version(assignment) != (expected_version or ""):
        raise StaleRoleAssignmentVersion()
    high_impact = _high_impact_for_revoke(target=target, assignment=assignment)
    if high_impact and not confirmed:
        raise ValidationError(
            {
                "__all__": (
                    "This revocation is high-impact. Confirm the preview before saving."
                )
            }
        )
    ensure_revocation_leaves_valid_access(target, assignment=assignment)
    revoked = revoke_role_assignment(
        actor=actor,
        assignment=assignment,
        business_reason=business_reason,
    )
    invalidate_permission_cache(target)
    return revoked
