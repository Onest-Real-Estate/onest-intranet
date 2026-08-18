from django.shortcuts import redirect

# Paths that must stay reachable before the profile is complete: the
# onboarding flow itself, sign-out, and the Django admin. /profile is
# gated — incomplete users should finish onboarding first.
EXEMPT_PREFIXES = ("/admin", "/onboarding", "/logout")


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
        if (
            user.is_authenticated
            and not user.is_staff
            and not user.profile_completed
            and not request.path.startswith(EXEMPT_PREFIXES)
        ):
            return redirect("onboarding")
        return self.get_response(request)
