from django.urls import path
from django.views.generic import RedirectView

from .views.administration_views import (
    user_administration,
    user_administration_index,
    user_administration_roles,
    user_administration_submit,
)
from .views.auth_views import (
    headshot_display,
    headshot_upload,
    login_page,
    logout,
    onboarding,
    onboarding_submit,
    profile,
    profile_submit,
)
from .views.onboarding_administration_views import (
    onboarding_notice,
    onboarding_owner,
    onboarding_tasks,
    onboarding_tools,
    onboarding_workspace,
)

urlpatterns = [
    path("", login_page, name="login"),
    path("login", RedirectView.as_view(pattern_name="login", query_string=True)),
    path("logout", logout, name="logout"),
    path("onboarding", onboarding, name="onboarding"),
    path("onboarding/submit", onboarding_submit, name="onboarding_submit"),
    path("account/headshot", headshot_upload, name="headshot_upload"),
    path("account/headshot/file", headshot_display, name="headshot_display"),
    path("profile", profile, name="profile"),
    path("profile/submit", profile_submit, name="profile_submit"),
    path(
        "operations/users/administration",
        user_administration_index,
        name="user_administration_index",
    ),
    path(
        "operations/users/<int:user_id>/administration",
        user_administration,
        name="user_administration",
    ),
    path(
        "operations/users/<int:user_id>/administration/submit",
        user_administration_submit,
        name="user_administration_submit",
    ),
    path(
        "operations/users/<int:user_id>/administration/roles",
        user_administration_roles,
        name="user_administration_roles",
    ),
    path(
        "operations/new-agents/<int:user_id>",
        onboarding_workspace,
        name="new_agent_onboarding",
    ),
    path(
        "operations/new-agents/<int:user_id>/owner",
        onboarding_owner,
        name="new_agent_onboarding_owner",
    ),
    path(
        "operations/new-agents/<int:user_id>/tasks",
        onboarding_tasks,
        name="new_agent_onboarding_tasks",
    ),
    path(
        "operations/new-agents/<int:user_id>/tools",
        onboarding_tools,
        name="new_agent_onboarding_tools",
    ),
    path(
        "operations/new-agents/<int:user_id>/notices",
        onboarding_notice,
        name="new_agent_onboarding_notice",
    ),
]
