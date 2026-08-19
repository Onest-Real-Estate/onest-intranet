from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from functools import wraps
from typing import Any, Literal, cast

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
    has_effective_permissions,
)

logger = logging.getLogger("apps.authorization")

AccessLevel = Literal[
    "public",
    "authenticated",
    "onboarding_only",
    "permission_protected",
]
AuthBehavior = Literal["redirect", "json"]


@dataclass(frozen=True)
class AuthorizationPolicy:
    key: str
    access: AccessLevel
    description: str
    methods: tuple[str, ...]
    route_names: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    any_permissions: tuple[str, ...] = ()
    all_permissions: tuple[str, ...] = ()
    scope_rule: str = "none"
    allow_incomplete_profile: bool = False
    auth_behavior: AuthBehavior = "redirect"
    denial_status: int = 403
    surface_type: str = "route"


ROUTE_POLICIES: dict[str, AuthorizationPolicy] = {
    "login_page": AuthorizationPolicy(
        key="login_page",
        access="public",
        description="Microsoft SSO landing page.",
        methods=("GET",),
        route_names=("login",),
    ),
    "login_redirect_alias": AuthorizationPolicy(
        key="login_redirect_alias",
        access="public",
        description="Legacy /login alias that redirects to /.",
        methods=("GET",),
        path_prefixes=("/login",),
    ),
    "logout": AuthorizationPolicy(
        key="logout",
        access="authenticated",
        description="End the current session safely.",
        methods=("POST",),
        route_names=("logout",),
        allow_incomplete_profile=True,
    ),
    "onboarding": AuthorizationPolicy(
        key="onboarding",
        access="onboarding_only",
        description="Collect required post-SSO profile details.",
        methods=("GET",),
        route_names=("onboarding",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
    ),
    "onboarding_submit": AuthorizationPolicy(
        key="onboarding_submit",
        access="onboarding_only",
        description="Persist onboarding profile details.",
        methods=("POST",),
        route_names=("onboarding_submit",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
    ),
    "headshot_upload": AuthorizationPolicy(
        key="headshot_upload",
        access="onboarding_only",
        description="Upload the current user's headshot preview.",
        methods=("POST",),
        route_names=("headshot_upload",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
        auth_behavior="json",
    ),
    "profile": AuthorizationPolicy(
        key="profile",
        access="authenticated",
        description="Render the signed-in user's profile editor.",
        methods=("GET",),
        route_names=("profile",),
        scope_rule="self_only",
    ),
    "profile_submit": AuthorizationPolicy(
        key="profile_submit",
        access="authenticated",
        description="Persist the signed-in user's profile updates.",
        methods=("POST",),
        route_names=("profile_submit",),
        scope_rule="self_only",
    ),
    "dashboard": AuthorizationPolicy(
        key="dashboard",
        access="authenticated",
        description="Render the hub dashboard and deferred widgets.",
        methods=("GET",),
        route_names=("dashboard",),
        scope_rule="self_only",
    ),
    "design_system": AuthorizationPolicy(
        key="design_system",
        access="authenticated",
        description="Render the internal ONEST component catalog.",
        methods=("GET",),
        route_names=("design_system",),
        scope_rule="self_only",
    ),
    "coming_soon": AuthorizationPolicy(
        key="coming_soon",
        access="authenticated",
        description="Render a placeholder hub section page.",
        methods=("GET",),
        route_names=("coming_soon",),
        scope_rule="self_only",
    ),
}

NON_ROUTE_SURFACES: tuple[AuthorizationPolicy, ...] = (
    AuthorizationPolicy(
        key="admin_prefix",
        access="permission_protected",
        description="Django admin site and model endpoints.",
        methods=("GET", "POST"),
        path_prefixes=("/admin/",),
        all_permissions=("admin.access_admin",),
        scope_rule="admin_queryset_scope",
        surface_type="path_prefix",
    ),
    AuthorizationPolicy(
        key="allauth_accounts_prefix",
        access="public",
        description="Third-party allauth auth endpoints under /accounts/.",
        methods=("GET", "POST"),
        path_prefixes=("/accounts/",),
        surface_type="path_prefix",
    ),
    AuthorizationPolicy(
        key="user_admin_reset_onboarding",
        access="permission_protected",
        description="Admin bulk reset of onboarding state.",
        methods=("POST",),
        all_permissions=("user.change_user",),
        scope_rule="user_office_scope_all_objects",
        surface_type="admin_action",
    ),
    AuthorizationPolicy(
        key="audit_admin_replay_selected",
        access="permission_protected",
        description="Admin bulk replay of domain events.",
        methods=("POST",),
        all_permissions=("audit.can_replay_events",),
        scope_rule="audit_event_scope",
        surface_type="admin_action",
    ),
    AuthorizationPolicy(
        key="audit_admin_replay_selected_deliveries",
        access="permission_protected",
        description="Admin bulk replay of event deliveries.",
        methods=("POST",),
        all_permissions=("audit.can_replay_events",),
        scope_rule="audit_event_scope",
        surface_type="admin_action",
    ),
    AuthorizationPolicy(
        key="audit_task_replay_event",
        access="permission_protected",
        description="Background replay task with initiator revalidation.",
        methods=("TASK",),
        all_permissions=("audit.can_replay_events",),
        scope_rule="initiator_revalidation",
        surface_type="task",
    ),
)


def inventory_rows() -> list[dict[str, Any]]:
    policies = list(ROUTE_POLICIES.values()) + list(NON_ROUTE_SURFACES)
    return [asdict(policy) for policy in policies]


def get_authorization_policy(view_func) -> AuthorizationPolicy | None:
    return getattr(view_func, "_authorization_policy", None)


def _has_permissions(user, any_permissions, all_permissions):
    has_all = not all_permissions or has_effective_permissions(
        user, tuple(all_permissions)
    )
    has_any = not any_permissions or any(
        has_effective_permission(user, permission) for permission in any_permissions
    )
    return has_all and has_any


def _log_denial(
    request: HttpRequest,
    *,
    policy: AuthorizationPolicy,
    reason: str,
    status_code: int,
) -> None:
    request_id = getattr(request, "audit_request_id", "")
    log_event(
        "security.authorization.denied",
        actor=actor_from_user(getattr(request, "user", None)),
        target=AuditTarget(
            target_type="endpoint",
            target_label=request.path,
            target_snapshot={
                "policy": policy.key,
                "access": policy.access,
                "methods": list(policy.methods),
            },
        ),
        outcome=AuditEvent.Outcome.DENIED,
        source="request",
        channel=request.method or "",
        reason=reason,
        metadata={"request_id": request_id, "status_code": status_code},
    )
    logger.info(
        (
            "authorization_denied policy=%s path=%s method=%s "
            "status=%s request_id=%s reason=%s"
        ),
        policy.key,
        request.path,
        request.method,
        status_code,
        request_id,
        reason,
    )


def _json_denial(status_code: int, code: str, request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "error": code,
            "requestId": getattr(request, "audit_request_id", ""),
        },
        status=status_code,
    )


def _unauthenticated_response(
    request: HttpRequest, policy: AuthorizationPolicy
) -> HttpResponse:
    if policy.auth_behavior == "json":
        return _json_denial(401, "authentication_required", request)
    return redirect_to_login(request.get_full_path())


def enforce_policy(policy_key: str):
    policy = ROUTE_POLICIES[policy_key]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs):
            user = request.user
            if policy.access == "public":
                return view_func(request, *args, **kwargs)
            if not user.is_authenticated:
                _log_denial(
                    request,
                    policy=policy,
                    reason="authentication_required",
                    status_code=401,
                )
                return _unauthenticated_response(request, policy)
            if policy.access == "permission_protected" and not _has_permissions(
                user,
                policy.any_permissions,
                policy.all_permissions,
            ):
                _log_denial(
                    request,
                    policy=policy,
                    reason="missing_permissions",
                    status_code=policy.denial_status,
                )
                if policy.auth_behavior == "json":
                    return _json_denial(
                        policy.denial_status, "permission_denied", request
                    )
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        wrapped_view = cast(Any, _wrapped)
        wrapped_view._authorization_policy = policy
        return wrapped_view

    return decorator


def scope_q_for_user_offices(user, *, field_name: str) -> Q:
    access = get_effective_access(user)
    if access.company_wide:
        return Q()
    filters = Q()
    if access.region_keys:
        filters |= Q(
            **{f"{field_name}__region__stable_key__in": sorted(access.region_keys)}
        )
    if access.office_keys:
        filters |= Q(**{f"{field_name}__stable_key__in": sorted(access.office_keys)})
    return filters


def scope_queryset_for_user_office(
    user,
    queryset: QuerySet,
    *,
    field_name: str,
) -> QuerySet:
    if getattr(user, "is_superuser", False):
        return queryset
    filters = scope_q_for_user_offices(user, field_name=field_name)
    if not filters:
        return queryset.none()
    return queryset.filter(filters)


def scope_queryset_for_offices(user, queryset: QuerySet) -> QuerySet:
    if getattr(user, "is_superuser", False):
        return queryset
    access = get_effective_access(user)
    if access.company_wide:
        return queryset
    filters = Q()
    if access.region_keys:
        filters |= Q(region__stable_key__in=sorted(access.region_keys)) | Q(
            stable_key__in=sorted(access.region_keys)
        )
    if access.office_keys:
        filters |= Q(stable_key__in=sorted(access.office_keys))
    if not filters:
        return queryset.none()
    return queryset.filter(filters)


def assert_admin_bulk_scope(
    user,
    queryset: QuerySet,
    *,
    scoped_queryset: QuerySet,
    policy_key: str,
) -> None:
    total_ids = set(queryset.values_list("pk", flat=True))
    scoped_ids = set(scoped_queryset.values_list("pk", flat=True))
    if total_ids != scoped_ids:
        policy = next(item for item in NON_ROUTE_SURFACES if item.key == policy_key)
        dummy_request = HttpRequest()
        dummy_request.user = user
        dummy_request.path = "admin-bulk-action"
        dummy_request.method = "POST"
        _log_denial(
            dummy_request,
            policy=policy,
            reason="out_of_scope_objects",
            status_code=403,
        )
        raise PermissionDenied("The selected collection contains out-of-scope objects.")


def has_admin_permission(user, *permissions: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_staff", False):
        return False
    return has_effective_permissions(user, tuple(permissions))


def is_explicitly_public_path(path: str) -> bool:
    return any(
        path.startswith(prefix)
        for policy in NON_ROUTE_SURFACES
        if policy.access == "public"
        for prefix in policy.path_prefixes
    )


def is_non_route_exempt_path(path: str) -> bool:
    if path.startswith("/admin/"):
        return True
    if is_explicitly_public_path(path):
        return True
    return path.startswith("/silk/")
