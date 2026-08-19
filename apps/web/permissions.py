"""Server-side permission guards matching the frontend ``PermissionRequired``.

The frontend component only *shows* content conditionally — these guards are
the real enforcement. Permissions are Django auth codenames (e.g.
``"user.view_user"``), the same strings exposed to the client as
``user.permissions`` by ``web.middleware.InertiaShareMiddleware``.
"""

from django.core.exceptions import PermissionDenied
from ninja.security import SessionAuth

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.web.authorization import _has_permissions


def permission_required(any_permissions=(), all_permissions=(), login_url=None):
    """Require Django auth permissions on a view (Inertia pages included).

    Mirrors the frontend ``PermissionRequired`` component: the user must hold
    every permission in ``all_permissions`` and at least one in
    ``any_permissions``. Unauthenticated users are redirected to the login
    page; authenticated users without the permissions get a 403.

    Usage::

        @permission_required(all_permissions=["user.view_user"])
        @inertia("Reports")
        def reports(request):
            return {}
    """

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path(), login_url=login_url)
            if not _has_permissions(request.user, any_permissions, all_permissions):
                log_event(
                    "security.permission.denied",
                    actor=actor_from_user(request.user),
                    target=AuditTarget(
                        target_type="view",
                        target_label=request.path,
                        target_snapshot={
                            "any_permissions": list(any_permissions),
                            "all_permissions": list(all_permissions),
                        },
                    ),
                    outcome=AuditEvent.Outcome.DENIED,
                    source="request",
                    channel="permission_required",
                    reason="missing_permissions",
                )
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        _wrapped_view.__name__ = getattr(view_func, "__name__", "_wrapped_view")
        _wrapped_view.__doc__ = getattr(view_func, "__doc__", None)
        return _wrapped_view

    return decorator


class PermissionRequiredAuth(SessionAuth):
    """django-ninja auth that additionally requires Django auth permissions.

    Usage::

        from ninja import NinjaAPI
        from apps.web.permissions import PermissionRequiredAuth

        api = NinjaAPI(
            auth=PermissionRequiredAuth(all_permissions=["user.view_user"])
        )

    Returns the user only when authenticated *and* holding the required
    permissions; otherwise the request is rejected (401).
    """

    def __init__(self, any_permissions=(), all_permissions=()):
        super().__init__()
        self.any_permissions = tuple(any_permissions)
        self.all_permissions = tuple(all_permissions)

    def authenticate(self, request, key=None):
        user = super().authenticate(request, key)
        if user is None:
            return None
        if _has_permissions(user, self.any_permissions, self.all_permissions):
            return user
        return None
