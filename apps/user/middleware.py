from django.shortcuts import redirect
from django.urls import Resolver404, resolve

from apps.web.authorization import get_authorization_policy, is_non_route_exempt_path


class ProfileCompletionMiddleware:
    """Redirect users to the onboarding flow until their profile is complete.

    New users (first Microsoft SSO signup) must fill in their details before
    using the app — see apps/user/views.onboarding. Staff and the admin,
    onboarding, and logout URLs are exempt so admins are never locked out.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not user.is_staff and not user.profile_completed:
            if is_non_route_exempt_path(request.path):
                return self.get_response(request)
            try:
                policy = get_authorization_policy(resolve(request.path_info).func)
            except Resolver404:
                policy = None
            if policy is not None and policy.allow_incomplete_profile:
                return self.get_response(request)
            return redirect("onboarding")
        return self.get_response(request)
