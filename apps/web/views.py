from django.contrib.auth.decorators import login_required
from inertia import inertia, render


@inertia("Home")
def home(request):
    return {}


@login_required
@inertia("Dashboard")
def dashboard(request):
    return {}


def permission_denied(request, exception=None):
    """Custom 403 handler — renders the PermissionDenied Inertia page.

    Wired via ``handler403`` in config/urls.py. Used for PermissionDenied
    exceptions (e.g. ``apps/web/permissions.permission_required``) and CSRF
    failures. Returns a 403 whether the request is a full page load (HTML
    with data-page) or an Inertia visit (JSON).
    """
    response = render(request, "PermissionDenied")
    response.status_code = 403
    return response
