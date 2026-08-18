from django.contrib.auth.decorators import login_required
from django.http import Http404
from inertia import defer, inertia, render

from .dashboard import (
    HUB_SECTIONS,
    dashboard_action_items,
    dashboard_announcements,
    dashboard_documents,
    dashboard_market,
    dashboard_quick_apps,
    dashboard_schedule,
    dashboard_stats,
    dashboard_training,
    dashboard_transactions,
)


@login_required
@inertia("Dashboard")
def dashboard(request):
    return {
        "stats": defer(lambda: dashboard_stats(), group="stats"),
        "quickApps": defer(lambda: dashboard_quick_apps(), group="pipeline"),
        "announcements": defer(lambda: dashboard_announcements(), group="pipeline"),
        "transactions": defer(lambda: dashboard_transactions(), group="pipeline"),
        "training": defer(lambda: dashboard_training(), group="pipeline"),
        "schedule": defer(lambda: dashboard_schedule(), group="widgets"),
        "actionItems": defer(lambda: dashboard_action_items(), group="widgets"),
        "market": defer(lambda: dashboard_market(), group="widgets"),
        "documents": defer(lambda: dashboard_documents(), group="widgets"),
    }


@login_required
@inertia("ComingSoon")
def coming_soon(request, section: str):
    title = HUB_SECTIONS.get(section)
    if title is None:
        raise Http404()
    return {"title": title, "section": section}


def permission_denied(request, exception=None):
    """Custom 403 handler — renders the PermissionDenied Inertia page.

    Wired via ``handler403`` in config/urls.py. Used for PermissionDenied
    exceptions (e.g. ``apps.web.permissions.permission_required``) and CSRF
    failures. Returns a 403 whether the request is a full page load (HTML
    with data-page) or an Inertia visit (JSON).
    """
    response = render(request, "PermissionDenied")
    response.status_code = 403
    return response
