from django.urls import path

from . import views
from .quick_access import views as quick_access_views

urlpatterns = [
    path("dashboard", views.dashboard, name="dashboard"),
    path("design-system", views.design_system, name="design_system"),
    path("hub/<slug:section>", views.coming_soon, name="coming_soon"),
    # The dashboard panel's fire-and-forget click beacon. Not administrative:
    # it answers 204 to any signed-in reader and never says what it recorded.
    path(
        "dashboard/quick-access/click",
        quick_access_views.quick_access_click,
        name="quick_access_click",
    ),
    # Quick Access administration. The list itself is an operations
    # destination (below); these are the endpoints it drives.
    path(
        "operations/quick-access/new",
        quick_access_views.quick_access_new,
        name="quick_access_new",
    ),
    path(
        "operations/quick-access/reorder",
        quick_access_views.quick_access_reorder,
        name="quick_access_reorder",
    ),
    path(
        "operations/quick-access/submit",
        quick_access_views.quick_access_create,
        name="quick_access_create",
    ),
    path(
        "operations/quick-access/<int:link_id>",
        quick_access_views.quick_access_edit,
        name="quick_access_edit",
    ),
    path(
        "operations/quick-access/<int:link_id>/submit",
        quick_access_views.quick_access_update,
        name="quick_access_update",
    ),
    path(
        "operations/quick-access/<int:link_id>/state",
        quick_access_views.quick_access_state,
        name="quick_access_state",
    ),
    *[
        path(
            destination.path,
            views.OPERATIONS_VIEWS[destination.route_name],
            name=destination.route_name,
        )
        for destination in views.OPERATIONS_DESTINATIONS
    ],
]
