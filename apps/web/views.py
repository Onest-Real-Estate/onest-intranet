from django.http import Http404
from django.utils import timezone
from inertia import inertia, render

from apps.announcements.administration_views import (
    announcement_administration_index,
)
from apps.user.services.role_assignments import get_effective_access
from apps.user.views.directory_views import user_directory
from apps.user.views.office_administration_views import office_administration_index
from apps.user.views.office_resource_administration_views import (
    office_resources_admin_index,
)
from apps.user.views.onboarding_administration_views import new_agent_list
from apps.user.views.role_assignment_views import role_assignment_index
from apps.web.action_items import queue_for_user
from apps.web.dashboard.envelope import WidgetStatus
from apps.web.quick_access.views import quick_access_index

from .authorization import enforce_policy
from .contracts import list_response
from .dashboard import HUB_SECTIONS, deferred_widget_props, greeting_payload
from .operations import (
    OPERATIONS_DESTINATIONS,
    OperationsDestination,
    operations_policy_key,
    operations_scope_payload,
)


@enforce_policy("dashboard")
@inertia("Dashboard")
def dashboard(request):
    """Compose the page; every query lives behind a widget provider.

    The greeting is the one prop that is not deferred — it is shell, and it is
    computed server-side so the salutation and the date agree with the day
    boundaries every provider uses.
    """
    return {
        "greeting": greeting_payload(request.user),
        **deferred_widget_props(request.user),
    }


@enforce_policy("action_items_queue")
@inertia("ActionItemsQueue")
def action_items_queue(request):
    """Full filtered queue for the signed-in user.

    Re-runs source collectors rather than replaying dashboard rows, so a stale
    CTA cannot widen access: each destination (e.g. ``profile``) still enforces
    its own policy when followed.
    """
    access = get_effective_access(request.user)
    result = queue_for_user(
        request.user,
        access,
        now=timezone.now(),
        feed_limit=0,
    )
    if result.status == WidgetStatus.READY:
        queue = result.data
    elif result.status == WidgetStatus.EMPTY:
        queue = {
            "total": 0,
            "items": [],
            "viewAllHref": request.path,
        }
    else:
        queue = None
    return {
        "queue": queue,
        "emptyState": result.empty_state.payload() if result.empty_state else None,
        "unavailable": result.unavailable.payload() if result.unavailable else None,
        "partialFailure": bool(result.meta.get("partialFailure")),
    }


@enforce_policy("coming_soon")
@inertia("ComingSoon")
def coming_soon(request, section: str):
    title = HUB_SECTIONS.get(section)
    if title is None:
        raise Http404()
    return {"title": title, "section": section}


def _operations_view(destination: OperationsDestination):
    def operations_destination(request):
        return {
            "title": destination.label,
            "section": destination.key,
            "administrative": True,
            "scope": operations_scope_payload(request.user),
        }

    operations_destination.__name__ = destination.route_name
    page_view = inertia("ComingSoon")(operations_destination)
    return enforce_policy(operations_policy_key(destination))(page_view)


OPERATIONS_VIEWS = {
    destination.route_name: _operations_view(destination)
    for destination in OPERATIONS_DESTINATIONS
}
OPERATIONS_VIEWS["admin_announcements"] = announcement_administration_index
OPERATIONS_VIEWS["admin_users"] = user_directory
OPERATIONS_VIEWS["admin_new_agents"] = new_agent_list
OPERATIONS_VIEWS["admin_quick_access"] = quick_access_index
OPERATIONS_VIEWS["admin_assign_roles"] = role_assignment_index
OPERATIONS_VIEWS["admin_offices"] = office_administration_index
OPERATIONS_VIEWS["admin_office_resources"] = office_resources_admin_index


_CATALOG_CONTRACTS = (
    {
        "id": "ON-1048",
        "client": "Avery Johnson",
        "property": "1428 Grove Avenue",
        "status": "pending_signature",
        "updated": "Aug 19, 2026",
    },
    {
        "id": "ON-1047",
        "client": "Morgan Lee",
        "property": "88 Franklin Street",
        "status": "approved",
        "updated": "Aug 18, 2026",
    },
    {
        "id": "ON-1046",
        "client": "Taylor Bennett",
        "property": "9045 Cedar Ridge Drive",
        "status": "incomplete",
        "updated": "Aug 17, 2026",
    },
    {
        "id": "ON-1045",
        "client": "Jordan Williams",
        "property": "16 Market Square",
        "status": "pending_documents",
        "updated": "Aug 16, 2026",
    },
    {
        "id": "ON-1044",
        "client": "Casey Thompson",
        "property": "707 Lakeview Court",
        "status": "settled",
        "updated": "Aug 15, 2026",
    },
    {
        "id": "ON-1043",
        "client": "Riley Davis",
        "property": "310 Goldfinch Lane",
        "status": "archived",
        "updated": "Aug 14, 2026",
    },
)


@enforce_policy("design_system")
@inertia("DesignSystem")
def design_system(request):
    """Living catalog plus a real URL-driven list contract example."""
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    rows = [
        row
        for row in _CATALOG_CONTRACTS
        if (not query or query.casefold() in " ".join(row.values()).casefold())
        and (not status or row["status"] == status)
    ]
    page_size = 3
    total_pages = max(1, (len(rows) + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    return {
        "contracts": list_response(
            rows[start : start + page_size],
            page=page,
            page_size=page_size,
            total_items=len(rows),
            filters={"q": query, "status": status},
            sort_key="updated",
            sort_direction="desc",
        )
    }


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
