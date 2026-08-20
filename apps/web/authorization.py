from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from functools import wraps
from typing import Any, Literal, cast

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.services.role_assignments import get_effective_access
from apps.web.capability import matches_permission_check
from apps.web.operations import OPERATIONS_DESTINATIONS, operations_policy_key

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
        access="authenticated",
        description=(
            "Replace or remove the current user's headshot, from onboarding "
            "or the profile page."
        ),
        methods=("POST",),
        route_names=("headshot_upload",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
        auth_behavior="json",
    ),
    "headshot_display": AuthorizationPolicy(
        key="headshot_display",
        access="authenticated",
        description="Stream the signed-in user's headshot for avatar display.",
        methods=("GET",),
        route_names=("headshot_display",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
    ),
    "profile": AuthorizationPolicy(
        key="profile",
        access="authenticated",
        description="Render the signed-in user's own agent profile editor.",
        methods=("GET",),
        route_names=("profile",),
        scope_rule="self_only",
    ),
    "profile_submit": AuthorizationPolicy(
        key="profile_submit",
        access="authenticated",
        description=(
            "Persist the signed-in user's self-editable profile fields. "
            "Never addresses a user identifier supplied by the client."
        ),
        methods=("POST",),
        route_names=("profile_submit",),
        scope_rule="self_only",
    ),
    "user_administration_index": AuthorizationPolicy(
        key="user_administration_index",
        access="permission_protected",
        description=(
            "Find a user to administer. The listing is filtered to the "
            "signed-in administrator's own office and region scope."
        ),
        methods=("GET",),
        route_names=("user_administration_index",),
        all_permissions=("user.view_user_administration",),
        scope_rule="administered_user_scope",
    ),
    "user_administration": AuthorizationPolicy(
        key="user_administration",
        access="permission_protected",
        description=(
            "Render one user's broker-controlled profile record. The subject "
            "is resolved through the actor's scoped queryset, so an "
            "out-of-scope id is a 404."
        ),
        methods=("GET",),
        route_names=("user_administration",),
        all_permissions=("user.view_user_administration",),
        scope_rule="administered_user_scope",
    ),
    "user_administration_submit": AuthorizationPolicy(
        key="user_administration_submit",
        access="permission_protected",
        description=(
            "Persist broker-controlled profile fields for one user. Never "
            "accepts a role, permission, or account-status change."
        ),
        methods=("POST",),
        route_names=("user_administration_submit",),
        all_permissions=("user.change_user_administration",),
        scope_rule="administered_user_delegation_scope",
    ),
    "user_administration_roles": AuthorizationPolicy(
        key="user_administration_roles",
        access="permission_protected",
        description=(
            "Grant or revoke one role assignment for a user, through the "
            "role-assignment service and its own delegation rules."
        ),
        methods=("POST",),
        route_names=("user_administration_roles",),
        all_permissions=("user.change_user_administration",),
        scope_rule="role_delegation_scope",
    ),
    "new_agent_onboarding": AuthorizationPolicy(
        key="new_agent_onboarding",
        access="permission_protected",
        description="Render one source-derived onboarding record inside scope.",
        methods=("GET",),
        route_names=("new_agent_onboarding",),
        all_permissions=("web.view_new_agents",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_owner": AuthorizationPolicy(
        key="new_agent_onboarding_owner",
        access="permission_protected",
        description="Assign the operational owner of one scoped onboarding case.",
        methods=("POST",),
        route_names=("new_agent_onboarding_owner",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_tasks": AuthorizationPolicy(
        key="new_agent_onboarding_tasks",
        access="permission_protected",
        description="Create or resolve an operational onboarding task.",
        methods=("POST",),
        route_names=("new_agent_onboarding_tasks",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_tools": AuthorizationPolicy(
        key="new_agent_onboarding_tools",
        access="permission_protected",
        description="Update one approved operational tool-setup state.",
        methods=("POST",),
        route_names=("new_agent_onboarding_tools",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_notice": AuthorizationPolicy(
        key="new_agent_onboarding_notice",
        access="permission_protected",
        description="Delegate an eligible notice resend to its source domain.",
        methods=("POST",),
        route_names=("new_agent_onboarding_notice",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="source_service_reauthorization",
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

ROUTE_POLICIES.update(
    {
        operations_policy_key(destination): AuthorizationPolicy(
            key=operations_policy_key(destination),
            access="permission_protected",
            description=f"Render the {destination.label} administrative destination.",
            methods=("GET",),
            route_names=(destination.route_name,),
            all_permissions=(destination.permission,),
            scope_rule=destination.scope_rule,
        )
        for destination in OPERATIONS_DESTINATIONS
    }
)

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
    """Fail-closed capability check via the reviewed permission catalog."""
    return matches_permission_check(
        user,
        any_permissions=tuple(any_permissions),
        all_permissions=tuple(all_permissions),
    )


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
    return unauthenticated_redirect(request)


def unauthenticated_redirect(
    request: HttpRequest, *, login_url: str | None = None
) -> HttpResponse:
    """Redirect safely, marking only interrupted Inertia sessions as expired."""

    destination = login_url
    if destination is None and request.headers.get("X-Inertia") == "true":
        destination = f"{reverse('login')}?reason=session-expired"
    return redirect_to_login(request.get_full_path(), login_url=destination)


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


def _office_scope_q(access, *, field_name: str) -> Q:
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


def scope_q_for_user_offices(user, *, field_name: str) -> Q:
    return _office_scope_q(get_effective_access(user), field_name=field_name)


def scope_queryset_for_user_office(
    user,
    queryset: QuerySet,
    *,
    field_name: str,
    access=None,
) -> QuerySet:
    if getattr(user, "is_superuser", False):
        return queryset
    effective = get_effective_access(user) if access is None else access
    # Company-wide access yields an empty ``Q``, which is falsy — reading it as
    # "no scope" would hand a brokerage-wide admin an empty queryset.
    if effective.company_wide:
        return queryset
    filters = _office_scope_q(effective, field_name=field_name)
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
    return matches_permission_check(user, all_permissions=tuple(permissions))


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
