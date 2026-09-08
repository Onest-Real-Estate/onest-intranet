from django.urls import path

from apps.audit import views

urlpatterns = [
    path(
        "activity/<slug:record_type>/<str:record_id>",
        views.activity_timeline,
        name="activity_timeline",
    ),
]
