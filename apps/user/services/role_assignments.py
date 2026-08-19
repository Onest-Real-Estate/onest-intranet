from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import (
    ADMIN,
    BRANCH_MANAGER,
    REGION_MANAGER,
    ROLE_BY_KEY,
    ROLE_PRIORITY,
    ScopeType,
    get_role_definition,
)

MANAGEMENT_ROLES = frozenset({ADMIN})


@dataclass(frozen=True)
class EffectiveAccess:
    assignments: tuple[UserRoleAssignment, ...]
    role_keys: tuple[str, ...]
    permissions: frozenset[str]
    region_keys: frozenset[str]
    office_keys: frozenset[str]
    company_wide: bool


def _coerce_now(at=None):
    return at or timezone.now()


def _region_scope_key(scope_type: str, scope_office: Office | None) -> str:
    if scope_type == ScopeType.REGION and scope_office is not None:
        return scope_office.stable_key
    if scope_office and scope_office.region:
        return scope_office.region.stable_key
    return ""


def sync_assignment_statuses(user: User, *, at=None) -> None:
    at = _coerce_now(at)
    assignments = list(UserRoleAssignment.objects.filter(user=user))
    updates: list[UserRoleAssignment] = []
    for assignment in assignments:
        previous = assignment.status
        current = assignment.refresh_status(at=at)
        if current != previous:
            updates.append(assignment)
    if updates:
        UserRoleAssignment.objects.bulk_update(updates, ["status", "updated_at"])


def active_assignment_queryset(user: User, *, at=None):
    at = _coerce_now(at)
    return (
        UserRoleAssignment.objects.filter(user=user)
        .select_related("scope_office", "scope_office__region")
        .filter(status=UserRoleAssignment.Status.ACTIVE)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=at))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=at))
        .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=at))
    )


def get_effective_assignments(user: User, *, at=None) -> list[UserRoleAssignment]:
    if getattr(user, "is_anonymous", False):
        return []
    sync_assignment_statuses(user, at=at)
    return list(active_assignment_queryset(user, at=at))


def get_effective_role_keys(
    user: User,
    *,
    at=None,
    assignments: Sequence[UserRoleAssignment] | None = None,
) -> list[str]:
    seen: set[str] = set()
    role_keys: list[str] = []
    effective_assignments = (
        get_effective_assignments(user, at=at) if assignments is None else assignments
    )
    for assignment in effective_assignments:
        if assignment.role not in seen:
            seen.add(assignment.role)
            role_keys.append(assignment.role)
    if not role_keys:
        extras: list[str] = []
        for group_name in user.groups.values_list("name", flat=True):
            if group_name in ROLE_BY_KEY and group_name not in seen:
                seen.add(group_name)
                role_keys.append(group_name)
            elif group_name not in seen:
                seen.add(group_name)
                extras.append(group_name)
        extras.sort()
        role_keys.extend(extras)
    rank = {name: index for index, name in enumerate(ROLE_PRIORITY)}
    role_keys.sort(key=lambda name: rank.get(name, 999))
    return role_keys


def get_primary_role_key(user: User, *, at=None) -> str | None:
    role_keys = get_effective_role_keys(user, at=at)
    return role_keys[0] if role_keys else None


def get_effective_permissions(
    user: User,
    *,
    at=None,
    assignments: Sequence[UserRoleAssignment] | None = None,
) -> set[str]:
    if getattr(user, "is_anonymous", False):
        return set()
    if getattr(user, "is_superuser", False):
        return set(user.get_all_permissions())

    effective_assignments = (
        get_effective_assignments(user, at=at) if assignments is None else assignments
    )
    if not effective_assignments:
        return set(user.get_all_permissions())

    permissions = set(
        user.user_permissions.values_list("content_type__app_label", "codename")
    )
    normalized = {f"{app_label}.{codename}" for app_label, codename in permissions}
    role_keys = []
    seen: set[str] = set()
    for assignment in effective_assignments:
        if assignment.role not in seen:
            seen.add(assignment.role)
            role_keys.append(assignment.role)
    group_names = [
        get_role_definition(role_key).group_name
        for role_key in role_keys
        if role_key in ROLE_BY_KEY
    ]
    if group_names:
        rows = Group.objects.filter(name__in=group_names).values_list(
            "permissions__content_type__app_label",
            "permissions__codename",
        )
        normalized.update(
            f"{app_label}.{codename}"
            for app_label, codename in rows
            if app_label and codename
        )
    return normalized


def has_effective_permission(user: User, permission: str, *, at=None) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return permission in get_effective_permissions(user, at=at)


def has_effective_permissions(
    user: User, permissions: tuple[str, ...], *, at=None
) -> bool:
    if not permissions:
        return True
    effective_permissions = get_effective_permissions(user, at=at)
    return all(permission in effective_permissions for permission in permissions)


def get_effective_access(user: User, *, at=None) -> EffectiveAccess:
    assignments = tuple(get_effective_assignments(user, at=at))
    role_keys = tuple(get_effective_role_keys(user, at=at, assignments=assignments))
    permissions = frozenset(
        get_effective_permissions(user, at=at, assignments=assignments)
    )
    region_keys: set[str] = set()
    office_keys: set[str] = set()
    company_wide = False
    for assignment in assignments:
        if assignment.scope_type == ScopeType.COMPANY:
            company_wide = True
            continue
        if assignment.scope_office is None:
            continue
        if assignment.scope_type == ScopeType.REGION:
            region_keys.add(assignment.scope_office.stable_key)
        if assignment.scope_type == ScopeType.OFFICE:
            office_keys.add(assignment.scope_office.stable_key)
    if not assignments:
        office = getattr(user, "office", None)
        if ADMIN in role_keys:
            company_wide = True
        if office is not None:
            if BRANCH_MANAGER in role_keys:
                office_keys.add(office.stable_key)
            if REGION_MANAGER in role_keys and office.region is not None:
                region_keys.add(office.region.stable_key)
    return EffectiveAccess(
        assignments=assignments,
        role_keys=role_keys,
        permissions=permissions,
        region_keys=frozenset(region_keys),
        office_keys=frozenset(office_keys),
        company_wide=company_wide,
    )


def actor_can_manage_assignments(
    actor: User,
    *,
    role: str,
    target_scope_type: str,
    scope_office: Office | None,
) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    if actor.pk is None:
        return False

    definition = get_role_definition(role)
    if definition.protected:
        return False

    access = get_effective_access(actor)
    if ADMIN not in access.role_keys:
        return False
    if target_scope_type == ScopeType.COMPANY:
        return access.company_wide
    if scope_office is None:
        return False
    if target_scope_type == ScopeType.REGION:
        return scope_office.stable_key in access.region_keys or access.company_wide
    return scope_office.stable_key in access.office_keys or access.company_wide


def ensure_assignment_authority(
    actor: User,
    target_user: User,
    *,
    role: str,
    scope_type: str,
    scope_office: Office | None,
) -> None:
    if actor.pk == target_user.pk:
        raise PermissionDenied("Users cannot modify their own role assignments.")
    if not actor_can_manage_assignments(
        actor, role=role, target_scope_type=scope_type, scope_office=scope_office
    ):
        raise PermissionDenied("You do not have authority to manage this assignment.")


def _assignment_target(
    assignment: UserRoleAssignment | None = None,
    *,
    target_user: User | None = None,
) -> AuditTarget:
    if assignment is not None:
        label = f"{assignment.user.email}:{assignment.role}:{assignment.scope_type}"
        return AuditTarget(
            target_type="user.role_assignment",
            target_id=str(assignment.pk or ""),
            target_label=label,
            target_snapshot={
                "user_id": assignment.user.pk,
                "role": assignment.role,
                "scope_type": assignment.scope_type,
                "scope_office_id": (
                    assignment.scope_office.pk if assignment.scope_office else None
                ),
            },
        )
    if target_user is not None:
        return AuditTarget(
            target_type="user.user",
            target_id=str(target_user.pk or ""),
            target_label=target_user.email,
        )
    return AuditTarget(target_type="user.role_assignment")


def create_role_assignment(
    *,
    actor: User,
    target_user: User,
    role: str,
    scope_type: str,
    scope_office: Office | None = None,
    starts_at=None,
    ends_at=None,
    business_reason: str = "",
) -> UserRoleAssignment:
    ensure_assignment_authority(
        actor,
        target_user,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
    )
    if role not in ROLE_BY_KEY:
        raise ValidationError({"role": "Unsupported role."})

    with transaction.atomic():
        User.objects.select_for_update().filter(pk=target_user.pk).get()
        duplicate = (
            UserRoleAssignment.objects.select_for_update()
            .filter(
                user=target_user,
                role=role,
                scope_type=scope_type,
                scope_office=scope_office,
                status__in=[
                    UserRoleAssignment.Status.SCHEDULED,
                    UserRoleAssignment.Status.ACTIVE,
                ],
            )
            .first()
        )
        if duplicate is not None:
            log_event(
                "user.role_assignment.denied",
                actor=actor_from_user(actor),
                target=_assignment_target(duplicate),
                outcome=AuditEvent.Outcome.DENIED,
                reason="duplicate_assignment",
                metadata={"target_user_id": target_user.pk},
            )
            raise ValidationError(
                {
                    "__all__": (
                        "An active or scheduled assignment already exists "
                        "for this role and scope."
                    )
                }
            )

        assignment = UserRoleAssignment(
            user=target_user,
            role=role,
            scope_type=scope_type,
            scope_office=scope_office,
            starts_at=starts_at,
            ends_at=ends_at,
            assigned_by=actor,
            business_reason=business_reason,
        )
        assignment.refresh_status()
        assignment.full_clean()
        assignment.save()
        log_event(
            "user.role_assignment.created",
            actor=actor_from_user(actor),
            target=_assignment_target(assignment),
            after={
                "user_id": target_user.pk,
                "role": role,
                "scope_type": scope_type,
                "scope_office_id": scope_office.pk if scope_office else None,
                "status": assignment.status,
            },
            office_id=(scope_office.stable_key if scope_office else ""),
            region_id=_region_scope_key(scope_type, scope_office),
            metadata={"business_reason": business_reason},
        )
        return assignment


def revoke_role_assignment(
    *,
    actor: User,
    assignment: UserRoleAssignment,
    business_reason: str = "",
) -> UserRoleAssignment:
    if actor.pk != assignment.user.pk:
        ensure_assignment_authority(
            actor,
            assignment.user,
            role=assignment.role,
            scope_type=assignment.scope_type,
            scope_office=assignment.scope_office,
        )
    if actor.pk == assignment.user.pk and would_remove_last_management_role(
        actor, assignment=assignment
    ):
        raise ValidationError(
            {
                "__all__": (
                    "Revoking this assignment would remove your last management role."
                )
            }
        )

    with transaction.atomic():
        locked = (
            UserRoleAssignment.objects.select_for_update()
            .select_related("scope_office", "scope_office__region", "user")
            .get(pk=assignment.pk)
        )
        before = {
            "status": locked.status,
            "revoked_at": locked.revoked_at.isoformat() if locked.revoked_at else None,
        }
        if locked.status == UserRoleAssignment.Status.REVOKED:
            return locked
        locked.status = UserRoleAssignment.Status.REVOKED
        locked.revoked_at = timezone.now()
        locked.revoked_by = actor
        if business_reason:
            locked.business_reason = business_reason
        locked.full_clean()
        locked.save(
            update_fields=[
                "status",
                "revoked_at",
                "revoked_by",
                "business_reason",
                "updated_at",
            ]
        )
        log_event(
            "user.role_assignment.revoked",
            actor=actor_from_user(actor),
            target=_assignment_target(locked),
            before=before,
            after={
                "status": locked.status,
                "revoked_at": (
                    locked.revoked_at.isoformat() if locked.revoked_at else None
                ),
                "revoked_by_id": actor.pk,
            },
            office_id=(locked.scope_office.stable_key if locked.scope_office else ""),
            region_id=_region_scope_key(locked.scope_type, locked.scope_office),
            metadata={"business_reason": business_reason},
        )
        return locked


def update_role_assignment(
    *,
    actor: User,
    assignment: UserRoleAssignment,
    starts_at=None,
    ends_at=None,
    business_reason: str = "",
) -> UserRoleAssignment:
    ensure_assignment_authority(
        actor,
        assignment.user,
        role=assignment.role,
        scope_type=assignment.scope_type,
        scope_office=assignment.scope_office,
    )

    with transaction.atomic():
        locked = UserRoleAssignment.objects.select_for_update().get(pk=assignment.pk)
        before = {
            "starts_at": locked.starts_at.isoformat() if locked.starts_at else None,
            "ends_at": locked.ends_at.isoformat() if locked.ends_at else None,
            "status": locked.status,
            "business_reason": locked.business_reason,
        }
        locked.starts_at = starts_at
        locked.ends_at = ends_at
        locked.business_reason = business_reason
        locked.refresh_status()
        locked.full_clean()
        locked.save(
            update_fields=[
                "starts_at",
                "ends_at",
                "business_reason",
                "status",
                "updated_at",
            ]
        )
        log_event(
            "user.role_assignment.updated",
            actor=actor_from_user(actor),
            target=_assignment_target(locked),
            before=before,
            after={
                "starts_at": locked.starts_at.isoformat() if locked.starts_at else None,
                "ends_at": locked.ends_at.isoformat() if locked.ends_at else None,
                "status": locked.status,
                "business_reason": locked.business_reason,
            },
            office_id=(locked.scope_office.stable_key if locked.scope_office else ""),
            region_id=_region_scope_key(locked.scope_type, locked.scope_office),
        )
        return locked


def would_remove_last_management_role(
    actor: User, *, assignment: UserRoleAssignment
) -> bool:
    if assignment.user.pk != actor.pk or assignment.role not in MANAGEMENT_ROLES:
        return False
    assignments = [
        item
        for item in get_effective_assignments(actor)
        if item.role in MANAGEMENT_ROLES and item.pk != assignment.pk
    ]
    return len(assignments) == 0
