from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("apps.user.urls")),
    path("", include("apps.web.urls")),
]

# Silk (SQL profiling) is dev-only — see config/settings.py. Web UI: /silk/.
# Tests strip Silk from INSTALLED_APPS; keep the URL in step so DEBUG still
# serves media without importing a profiler that is not loaded.
if settings.DEBUG:
    from django.conf.urls.static import static

    if "silk" in settings.INSTALLED_APPS:
        urlpatterns += [path("silk/", include("silk.urls", namespace="silk"))]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom 403 page (PermissionDenied Inertia page) — see
# apps/web/views.permission_denied.
handler403 = "apps.web.views.permission_denied"
handler404 = "apps.web.views.not_found"
