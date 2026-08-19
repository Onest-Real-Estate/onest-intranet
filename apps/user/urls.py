from django.urls import path
from django.views.generic import RedirectView

from .views.auth_views import (
    headshot_upload,
    login_page,
    logout,
    onboarding,
    onboarding_submit,
    profile,
    profile_submit,
)

urlpatterns = [
    path("", login_page, name="login"),
    path("login", RedirectView.as_view(pattern_name="login", query_string=True)),
    path("logout", logout, name="logout"),
    path("onboarding", onboarding, name="onboarding"),
    path("onboarding/submit", onboarding_submit, name="onboarding_submit"),
    path("account/headshot", headshot_upload, name="headshot_upload"),
    path("profile", profile, name="profile"),
    path("profile/submit", profile_submit, name="profile_submit"),
]
