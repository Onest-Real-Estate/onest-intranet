from django.middleware.csrf import get_token
from inertia import share


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
            "permissions": sorted(user.get_all_permissions()),
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
