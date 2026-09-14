from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from django.views.generic import RedirectView

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
]

# SOCIALACCOUNT_ONLY still serves GET /accounts/login/ as allauth's password
# form. Intercept it first so the hub Login page is the only sign-in chrome.
if settings.SOCIALACCOUNT_ONLY:
    urlpatterns.append(
        path(
            "accounts/login/",
            RedirectView.as_view(pattern_name="login", query_string=True),
        )
    )

urlpatterns += [
    path("accounts/", include("allauth.urls")),
    path("", include("apps.user.urls")),
    # Inventory hub routes must beat ``hub/<slug>`` in web.urls (coming_soon).
    path("", include("apps.inventory.urls")),
    path("", include("apps.web.urls")),
    path("", include("apps.contract.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.announcements.urls")),
    path("", include("apps.operational_tasks.urls")),
    path("", include("apps.feedback.urls")),
    path("", include("apps.it_support.urls")),
    path("", include("apps.onboarding_tools.urls")),
    path("", include("apps.training.urls")),
    path("", include("apps.marketing.urls")),
    path("", include("apps.compliance.urls")),
    path("", include("apps.documents.urls")),
    path("", include("apps.audit.urls")),
    path("", include("apps.reservations.urls")),
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
