from django.shortcuts import redirect
from django.urls import Resolver404, resolve

from apps.user.services.onboarding_state import journey_applies_to, journey_for_user
from apps.user.services.role_assignments import get_effective_access
from apps.web.authorization import get_authorization_policy, is_non_route_exempt_path


class ProfileCompletionMiddleware:
    """Apply the server-owned required-setup gate to ordinary Agent users."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if not user.is_authenticated or user.profile_completed:
            return self.get_response(request)

        access = get_effective_access(user)
        request._inertia_access_context = access
        if not journey_applies_to(user, access=access):
            return self.get_response(request)

        journey = journey_for_user(user)
        request._onboarding_journey = journey
        request._onboarding_strict_gate = not journey.required_setup_complete
        if not request._onboarding_strict_gate:
            return self.get_response(request)
        if is_non_route_exempt_path(request.path):
            return self.get_response(request)
        try:
            policy = get_authorization_policy(resolve(request.path_info).func)
        except Resolver404:
            policy = None
        if policy is not None and policy.allow_incomplete_profile:
            return self.get_response(request)
        return redirect("dashboard")
