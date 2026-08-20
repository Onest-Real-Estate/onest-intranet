import logging

from django.middleware.csrf import get_token
from django.urls import Resolver404, resolve
from inertia import share

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.headshot import headshot_public_url
from apps.user.roles import AGENT, ROLE_LABELS, SUPERADMIN_LABEL
from apps.user.services.role_assignments import get_effective_access
from apps.web.authorization import (
    get_authorization_policy,
    is_non_route_exempt_path,
)
from apps.web.navigation import hub_feature_states, primary_office_payload
from apps.web.permission_catalog import CATALOG_VERSION
from apps.web.shell import authorization_version, help_configuration

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
    """Attach the minimal, request-cached contract shared with Inertia pages."""

    def access_context(self, request):
        cached = getattr(request, "_inertia_access_context", None)
        if cached is not None:
            return cached
        if not request.user.is_authenticated:
            context = None
        else:
            context = get_effective_access(request.user)
        request._inertia_access_context = context
        return context

    def serialize_user(self, request):
        user = request.user
        if not user.is_authenticated:
            return None
        access = self.access_context(request)
        role_label = (
            SUPERADMIN_LABEL
            if user.is_superuser
            else ROLE_LABELS.get(
                access.role_keys[0] if access.role_keys else AGENT,
                ROLE_LABELS[AGENT],
            )
        )
        return {
            "id": user.id,
            "email": user.email,
            "name": user.display_name or user.get_full_name() or user.email,
            "headshotUrl": headshot_public_url(request, user),
            # Catalogued Django auth permission codenames only.
            "permissions": sorted(access.permissions),
            # Role codes (stable), highest-priority first.
            "roles": list(access.role_keys),
            "roleLabel": role_label,
            "isStaff": user.is_staff,
            "isSuperuser": user.is_superuser,
        }

    def shell_context(self, request):
        access = self.access_context(request)
        return {
            "authorizationVersion": (
                authorization_version(access) if access is not None else ""
            ),
            "capabilitySchemaVersion": CATALOG_VERSION,
            "help": help_configuration(),
            "session": {"authenticated": request.user.is_authenticated},
        }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        share(
            request,
            user=lambda: self.serialize_user(request),
            csrfToken=lambda: get_token(request),
            requestId=lambda: getattr(request, "audit_request_id", ""),
            # Nav feature state and office context — see web.navigation.
            features=lambda: hub_feature_states(
                request.user,
                permissions=(
                    self.access_context(request).permissions
                    if self.access_context(request) is not None
                    else None
                ),
            ),
            primaryOffice=lambda: primary_office_payload(request.user),
            shell=lambda: self.shell_context(request),
        )
        return self.get_response(request)
