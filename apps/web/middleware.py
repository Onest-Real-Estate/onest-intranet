import json
import logging

from django.core.exceptions import RequestDataTooBig
from django.http import QueryDict, UnreadablePostError
from django.middleware.csrf import get_token
from django.urls import Resolver404, resolve
from django.utils.datastructures import MultiValueDict
from inertia import share

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.notifications.shell import notification_shell_payload
from apps.user.headshot import headshot_public_url
from apps.user.roles import AGENT, ROLE_LABELS, SUPERADMIN_LABEL
from apps.user.services.role_assignments import get_effective_access
from apps.web.authorization import (
    get_authorization_policy,
    is_non_route_exempt_path,
)
from apps.web.navigation import hub_feature_states, primary_office_payload
from apps.web.permission_catalog import CATALOG_VERSION
from apps.web.quick_actions import quick_create_payload
from apps.web.shell import authorization_version, help_configuration

logger = logging.getLogger("apps.authorization")
#: Its own channel: a body that will not parse is a request-shape problem,
#: not an authorization decision, and the two are read by different people.
json_logger = logging.getLogger("apps.web.inertia_json")


class InertiaJsonPostMiddleware:
    """Make Inertia's JSON request bodies readable as ``request.POST``.

    Inertia serializes a visit's data as ``application/json`` unless it carries
    a file. Django populates ``request.POST`` only for
    ``application/x-www-form-urlencoded`` and ``multipart/form-data``, so every
    field of such a request arrives as an empty ``QueryDict`` and each view
    silently reads ``""`` — no error, no log, just a write that does nothing.
    Django's test client posts form-encoded by default, so a test suite does
    not see it.

    This translates the body once, at the edge, so the fifteen view modules
    that read ``request.POST`` keep one input contract regardless of how the
    caller encoded it. The alternative — forcing the client to send
    ``FormData`` — cannot express a list: Inertia writes ``order[0]``,
    ``order[1]``, and ``QueryDict.getlist("order")`` then returns nothing.

    Values are coerced to what an equivalent HTML form would have submitted, so
    a view written against a form post reads the same thing either way:

    * ``True`` / ``False`` become ``"1"`` / ``"0"`` — the convention Inertia's
      own ``FormData`` serializer uses, and what ``== "1"`` checks expect;
    * ``None`` becomes ``""``, the empty field a browser sends;
    * a list becomes repeated values, readable with ``getlist``;
    * a nested object is re-encoded as JSON, because a ``QueryDict`` holds
      strings and dropping it silently would be worse than handing the view
      something it can parse.

    Only unsafe methods with a JSON content type are touched. A GET carries no
    body, a form post is already correct, and a multipart upload must keep
    Django's own parser — none of them reach the translation.
    """

    #: Methods that carry a body worth reading. GET and DELETE are excluded
    #: because Inertia sends their data in the query string, not the body.
    UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH"})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in self.UNSAFE_METHODS and self._is_json(request):
            self._translate(request)
        return self.get_response(request)

    @staticmethod
    def _is_json(request) -> bool:
        return request.content_type == "application/json"

    def _translate(self, request) -> None:
        try:
            raw = request.body
        except (RequestDataTooBig, UnreadablePostError, OSError):
            # Django raises rather than truncating. Leaving ``POST`` empty lets
            # the view answer with its own validation error instead of a 500.
            json_logger.warning("unreadable body on %s", request.path)
            return
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            json_logger.warning("malformed body on %s", request.path)
            return
        if not isinstance(payload, dict):
            # A bare list or scalar has no field names, so there is nothing a
            # form-shaped view could read from it.
            return

        data = QueryDict(mutable=True)
        for key, value in payload.items():
            if isinstance(value, list):
                data.setlist(str(key), [self._scalar(item) for item in value])
            else:
                data[str(key)] = self._scalar(value)
        data._mutable = False

        # Both, together: Django populates ``_post`` and ``_files`` in one step,
        # and a view reaching for ``request.FILES`` must not find the attribute
        # missing on a request that never had one.
        request._post = data
        request._files = MultiValueDict()

    @staticmethod
    def _scalar(value) -> str:
        if isinstance(value, bool):
            return "1" if value else "0"
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, int | float):
            return str(value)
        return json.dumps(value)


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
        if not module.startswith(("apps.notifications.", "apps.user.", "apps.web.")):
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
            # Quick Create. Filtered to what the actor may actually start —
            # unavailable actions are absent from the payload, not hidden in
            # the client. See apps/web/quick_actions.py.
            quickCreate=lambda: quick_create_payload(
                request.user, access=self.access_context(request)
            ),
            # Header badge counts — the reader's own unread total, never
            # an office aggregate. See apps/notifications/shell.py.
            notifications=lambda: notification_shell_payload(request.user),
            shell=lambda: self.shell_context(request),
        )
        return self.get_response(request)
