"""Server-side permission guards matching the frontend ``PermissionRequired``.

The frontend component only *shows* content conditionally — these guards are
the real enforcement. Permissions are Django auth codenames (e.g.
``"user.view_user"``), the same strings exposed to the client as
``user.permissions`` by ``web.middleware.InertiaShareMiddleware``.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from ninja.security import SessionAuth


def _has_permissions(user, any_permissions, all_permissions):
    """True when the user holds every permission in ``all_permissions`` and
    at least one in ``any_permissions`` (empty tuples are not required)."""
    has_all = not all_permissions or user.has_perms(all_permissions)
    has_any = not any_permissions or any(
        user.has_perm(permission) for permission in any_permissions
    )
    return has_all and has_any


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
        @login_required(login_url=login_url)
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not _has_permissions(request.user, any_permissions, all_permissions):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

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
