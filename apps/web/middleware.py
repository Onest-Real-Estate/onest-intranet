import logging

from django.middleware.csrf import get_token
from django.urls import Resolver404, resolve
from inertia import share

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.roles import ordered_role_names, primary_role_label
from apps.user.services.role_assignments import get_effective_permissions
from apps.web.authorization import (
    get_authorization_policy,
    is_non_route_exempt_path,
)
from apps.web.navigation import hub_feature_states, primary_office_payload

logger = logging.getLogger("apps.authorization")


class AuthorizationPolicyMiddleware:
    """Default-deny middleware for local views missing explicit auth metadata."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_non_route_exempt_path(request.path):
            return self.get_response(request)
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return self.get_response(request)
        callback = match.func
        module = getattr(callback, "__module__", "")
        callback_name = getattr(callback, "__name__", callback.__class__.__name__)
        if not module.startswith(("apps.user.", "apps.web.")):
            return self.get_response(request)
        policy = get_authorization_policy(callback)
        if policy is None:
            request_id = getattr(request, "audit_request_id", "")
            log_event(
                "security.endpoint.unclassified",
                actor=actor_from_user(getattr(request, "user", None)),
                target=AuditTarget(
                    target_type="endpoint",
                    target_label=request.path,
                    target_snapshot={"module": module, "view": callback_name},
                ),
                outcome=AuditEvent.Outcome.DENIED,
                source="request",
                channel=request.method,
                reason="missing_authorization_policy",
                metadata={"request_id": request_id},
            )
            logger.warning(
                (
                    "unclassified_endpoint path=%s method=%s module=%s "
                    "view=%s request_id=%s"
                ),
                request.path,
                request.method,
                module,
                callback_name,
                request_id,
            )
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        request.authorization_policy = policy
        return self.get_response(request)


class InertiaShareMiddleware:
    """Attach props shared with every Inertia page (user, csrf token)."""

    def serialize_user(self, user):
        if not user.is_authenticated:
            return None
        return {
            "id": user.id,
            "email": user.email,
            "name": user.display_name or user.get_full_name() or user.email,
            # Django auth permission codenames, e.g. "user.view_user".
            "permissions": sorted(get_effective_permissions(user)),
            # Role (Django group) names, highest-priority first.
            "roles": ordered_role_names(user),
            "roleLabel": primary_role_label(user),
            "isStaff": user.is_staff,
            "isSuperuser": user.is_superuser,
        }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        share(
            request,
            user=lambda: self.serialize_user(request.user),
            csrfToken=lambda: get_token(request),
            requestId=lambda: getattr(request, "audit_request_id", ""),
            # Nav feature state and office context — see web.navigation.
            features=hub_feature_states,
            primaryOffice=lambda: primary_office_payload(request.user),
        )
        return self.get_response(request)
