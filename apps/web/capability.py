"""Capability evaluation: catalogued permissions, fail-closed, scoped checks.

Authentication (session / SSO), capability (this module), and organizational
scope (``role_assignments.get_effective_access`` + queryset helpers) are
deliberately separate. Callers that need both must ask for both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.services.role_assignments import (
    EffectiveAccess,
    get_effective_access,
    has_effective_permission,
)
from apps.web.permission_catalog import (
    filter_to_catalog,
    get_permission_definition,
    is_cataloged_permission,
)

if TYPE_CHECKING:
    from apps.user.models import Office, User

_REQUEST_CACHE_ATTR = "_capability_access_cache"


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    reason: str
    permission: str

    @property
    def denied(self) -> bool:
        return not self.allowed


def access_for(
    user: User, *, at=None, access: EffectiveAccess | None = None
) -> EffectiveAccess:
    if access is not None:
        return access
    return get_effective_access(user, at=at)


def request_access(request) -> EffectiveAccess | None:
    """Request-scoped effective access (invalidates naturally per request)."""
    if hasattr(request, _REQUEST_CACHE_ATTR):
        return getattr(request, _REQUEST_CACHE_ATTR)
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        setattr(request, _REQUEST_CACHE_ATTR, None)
        return None
    resolved = get_effective_access(user)
    setattr(request, _REQUEST_CACHE_ATTR, resolved)
    return resolved


def clear_request_access_cache(request) -> None:
    if hasattr(request, _REQUEST_CACHE_ATTR):
        delattr(request, _REQUEST_CACHE_ATTR)


def has_capability(
    user: User,
    permission: str,
    *,
    at=None,
    access: EffectiveAccess | None = None,
) -> bool:
    """Whether ``user`` holds ``permission`` (capability only, no scope).

    Unknown catalog codenames fail closed. Django ``is_superuser`` remains a
    break-glass bypass and must not be used to define System Admin behaviour.
    """
    if not permission or not is_cataloged_permission(permission):
        return False
    if getattr(user, "is_anonymous", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if access is not None:
        return permission in access.permissions
    return has_effective_permission(user, permission, at=at)


def has_capabilities(
    user: User,
    permissions: tuple[str, ...],
    *,
    at=None,
    access: EffectiveAccess | None = None,
    require_all: bool = True,
) -> bool:
    if not permissions:
        return True
    if any(not is_cataloged_permission(item) for item in permissions):
        return False
    resolved = access_for(user, at=at, access=access)
    if require_all:
        return all(
            has_capability(user, item, at=at, access=resolved) for item in permissions
        )
    return any(
        has_capability(user, item, at=at, access=resolved) for item in permissions
    )


def _office_in_scope(access: EffectiveAccess, office: Office | None) -> bool:
    if office is None:
        return False
    if access.company_wide:
        return True
    if office.stable_key in access.office_keys:
        return True
    region = getattr(office, "region", None)
    if region is not None and region.stable_key in access.region_keys:
        return True
    return office.stable_key in access.region_keys


def evaluate_permission(
    user: User,
    permission: str,
    *,
    office: Office | None = None,
    require_scope: bool | None = None,
    at=None,
    access: EffectiveAccess | None = None,
) -> CapabilityDecision:
    """Evaluate capability and optional organizational scope together.

    When ``require_scope`` is omitted, the catalog ``scoped`` flag decides
    whether a missing office context is a denial.
    """
    if not permission or not is_cataloged_permission(permission):
        return CapabilityDecision(
            allowed=False,
            reason="unknown_permission",
            permission=permission or "",
        )
    if getattr(user, "is_anonymous", False):
        return CapabilityDecision(
            allowed=False, reason="unauthenticated", permission=permission
        )

    item = get_permission_definition(permission)
    needs_scope = item.scoped if require_scope is None else require_scope

    if not has_capability(user, permission, at=at, access=access):
        return CapabilityDecision(
            allowed=False, reason="missing_capability", permission=permission
        )

    if getattr(user, "is_superuser", False):
        return CapabilityDecision(
            allowed=True, reason="superuser", permission=permission
        )

    if not needs_scope:
        return CapabilityDecision(allowed=True, reason="ok", permission=permission)

    resolved = access_for(user, at=at, access=access)
    if office is None:
        return CapabilityDecision(
            allowed=False,
            reason="missing_scope_context",
            permission=permission,
        )
    if not _office_in_scope(resolved, office):
        return CapabilityDecision(
            allowed=False, reason="out_of_scope", permission=permission
        )
    return CapabilityDecision(allowed=True, reason="ok", permission=permission)


def require_permission(
    user: User,
    permission: str,
    *,
    office: Office | None = None,
    require_scope: bool | None = None,
    at=None,
    access: EffectiveAccess | None = None,
    audit: bool = True,
    audit_label: str = "",
) -> None:
    """Raise ``PermissionDenied`` unless capability (+ optional scope) pass."""
    decision = evaluate_permission(
        user,
        permission,
        office=office,
        require_scope=require_scope,
        at=at,
        access=access,
    )
    if decision.allowed:
        return
    if audit and decision.reason in {
        "missing_capability",
        "out_of_scope",
        "missing_scope_context",
        "unknown_permission",
    }:
        log_event(
            "security.permission.denied",
            actor=actor_from_user(user),
            target=AuditTarget(
                target_type="permission",
                target_label=audit_label or permission,
                target_snapshot={
                    "permission": permission,
                    "reason": decision.reason,
                },
            ),
            outcome=AuditEvent.Outcome.DENIED,
            source="service",
            channel="require_permission",
            reason=decision.reason,
        )
    raise PermissionDenied(decision.reason)


def filter_effective_permissions(
    permissions: set[str] | frozenset[str],
) -> frozenset[str]:
    """Drop anything not in the reviewed catalog before shipping to clients."""
    return filter_to_catalog(permissions)


def matches_permission_check(
    user: User,
    *,
    any_permissions: tuple[str, ...] = (),
    all_permissions: tuple[str, ...] = (),
    at=None,
    access: EffectiveAccess | None = None,
) -> bool:
    """Shared any/all evaluator used by views, APIs, and the frontend mirror."""
    if any(not is_cataloged_permission(item) for item in any_permissions):
        return False
    if any(not is_cataloged_permission(item) for item in all_permissions):
        return False
    resolved = (
        access_for(user, at=at, access=access)
        if (any_permissions or all_permissions)
        else access
    )
    has_all = (not all_permissions) or has_capabilities(
        user, tuple(all_permissions), at=at, access=resolved, require_all=True
    )
    has_any = (not any_permissions) or has_capabilities(
        user, tuple(any_permissions), at=at, access=resolved, require_all=False
    )
    return has_all and has_any
