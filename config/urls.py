from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("apps.user.urls")),
    path("", include("apps.web.urls")),
]

# Silk (SQL profiling) is dev-only — see config/settings.py. Web UI: /silk/.
if settings.DEBUG:
    urlpatterns += [path("silk/", include("silk.urls", namespace="silk"))]

# Custom 403 page (PermissionDenied Inertia page) — see
# apps/web/views.permission_denied.
handler403 = "apps.web.views.permission_denied"
