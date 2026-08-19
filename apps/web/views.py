from django.http import Http404
from inertia import defer, inertia, render

from .authorization import enforce_policy
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


@enforce_policy("dashboard")
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


@enforce_policy("coming_soon")
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
    response = render(
        request,
        "PermissionDenied",
        {"requestId": getattr(request, "audit_request_id", "")},
    )
    response.status_code = 403
    return response


def not_found(request, exception=None):
    response = render(
        request, "NotFound", {"requestId": getattr(request, "audit_request_id", "")}
    )
    response.status_code = 404
    return response
