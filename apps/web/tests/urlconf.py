"""Test URLconf used by test_permissions.py (end-to-end 403 handler test)."""

from django.http import HttpResponse
from django.urls import path

from apps.web.permissions import permission_required

handler403 = "apps.web.views.permission_denied"


def _protected_view(request):
    return HttpResponse("protected")


urlpatterns = [
    path(
        "protected",
        permission_required(all_permissions=["user.view_user"])(_protected_view),
    ),
]
