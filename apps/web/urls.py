from django.urls import path

from . import views

urlpatterns = [
    path("dashboard", views.dashboard, name="dashboard"),
    path("design-system", views.design_system, name="design_system"),
    path("hub/<slug:section>", views.coming_soon, name="coming_soon"),
    *[
        path(
            destination.path,
            views.OPERATIONS_VIEWS[destination.route_name],
            name=destination.route_name,
        )
        for destination in views.OPERATIONS_DESTINATIONS
    ],
]
