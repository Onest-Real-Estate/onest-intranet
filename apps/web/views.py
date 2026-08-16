from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from inertia import inertia, render
from inertia.http import clear_history


@inertia("Home")
def home(request):
    return {}


@inertia("Login")
def login_page(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return {}


@login_required
@inertia("Dashboard")
def dashboard(request):
    return {}


@require_POST
def logout(request):
    auth_logout(request)
    clear_history(request)
    return redirect("home")


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
