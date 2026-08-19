from django.middleware.csrf import get_token
from inertia import share

from apps.user.roles import ordered_role_names, primary_role_label
from apps.user.services.role_assignments import get_effective_permissions


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
        )
        return self.get_response(request)
