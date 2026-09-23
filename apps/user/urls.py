from django.urls import path
from django.views.generic import RedirectView

from .views.administration_views import (
    user_account_state,
    user_administration,
    user_administration_roles,
    user_administration_submit,
)
from .views.agent_directory_views import (
    agent_directory,
    agent_directory_detail,
    agent_directory_headshot,
)
from .views.auth_views import (
    headshot_display,
    headshot_upload,
    login_page,
    logout,
    profile,
    profile_submit,
)
from .views.directory_views import people_hub
from .views.office_administration_views import (
    office_administration_contact,
    office_administration_contact_end,
    office_administration_detail,
    office_administration_impact,
    office_administration_structure,
    office_administration_update,
    office_info,
)
from .views.office_resource_administration_views import (
    office_resource_create,
    office_resource_detail,
    office_resource_file,
    office_resource_new,
    office_resource_transition,
    office_resource_update,
    office_resources_admin_index,
)
from .views.office_resource_views import (
    office_resource_download,
    office_resources,
)
from .views.onboarding_administration_views import (
    onboarding_contract,
    onboarding_handoff,
    onboarding_headshot,
    onboarding_notice,
    onboarding_owner,
    onboarding_tasks,
    onboarding_tools,
    onboarding_workspace,
)
from .views.onboarding_profile_views import (
    onboarding,
    onboarding_office_preview,
    onboarding_profile_finalize,
    onboarding_profile_save,
)
from .views.onboarding_stream_views import onboarding_stream_token
from .views.role_assignment_views import (
    role_assignment_mutate,
    role_assignment_preview,
    role_assignment_workspace,
)

urlpatterns = [
    # One navigation entry for Users, Roles & permissions, and New agents.
    path("operations/people", people_hub, name="admin_people"),
    path("", login_page, name="login"),
    path("login", RedirectView.as_view(pattern_name="login", query_string=True)),
    path("logout", logout, name="logout"),
    path("onboarding", onboarding, name="onboarding"),
    path(
        "onboarding/live/token",
        onboarding_stream_token,
        name="onboarding_stream_token",
    ),
    path(
        "onboarding/offices/<int:office_id>/preview",
        onboarding_office_preview,
        name="onboarding_office_preview",
    ),
    path(
        "onboarding/profile/sections/<slug:section>",
        onboarding_profile_save,
        name="onboarding_profile_save",
    ),
    path(
        "onboarding/profile/finalize",
        onboarding_profile_finalize,
        name="onboarding_profile_finalize",
    ),
    path("account/headshot", headshot_upload, name="headshot_upload"),
    path("account/headshot/file", headshot_display, name="headshot_display"),
    path("profile", profile, name="profile"),
    path("profile/submit", profile_submit, name="profile_submit"),
    path("hub/agent-directory", agent_directory, name="agent_directory"),
    path(
        "hub/agent-directory/<int:user_id>",
        agent_directory_detail,
        name="agent_directory_detail",
    ),
    path(
        "hub/agent-directory/<int:user_id>/headshot",
        agent_directory_headshot,
        name="agent_directory_headshot",
    ),
    path("office-info", office_info, name="office_info"),
    path("office-resources", office_resources, name="office_resources"),
    path(
        "office-resources/<slug:slug>/download",
        office_resource_download,
        name="office_resources_download",
    ),
    path(
        "operations/office-resources",
        office_resources_admin_index,
        name="admin_office_resources",
    ),
    path(
        "operations/office-resources/new",
        office_resource_new,
        name="admin_office_resource_new",
    ),
    path(
        "operations/office-resources/create",
        office_resource_create,
        name="admin_office_resource_create",
    ),
    path(
        "operations/office-resources/<int:resource_id>",
        office_resource_detail,
        name="admin_office_resource",
    ),
    path(
        "operations/office-resources/<int:resource_id>/submit",
        office_resource_update,
        name="admin_office_resource_update",
    ),
    path(
        "operations/office-resources/<int:resource_id>/file",
        office_resource_file,
        name="admin_office_resource_file",
    ),
    path(
        "operations/office-resources/<int:resource_id>/transition",
        office_resource_transition,
        name="admin_office_resource_transition",
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
        "operations/users/<int:user_id>/account-state",
        user_account_state,
        name="user_account_state",
    ),
    path(
        "operations/role-assignments/<int:user_id>",
        role_assignment_workspace,
        name="admin_assign_roles_user",
    ),
    path(
        "operations/role-assignments/<int:user_id>/preview",
        role_assignment_preview,
        name="admin_assign_roles_preview",
    ),
    path(
        "operations/role-assignments/<int:user_id>/assignments",
        role_assignment_mutate,
        name="admin_assign_roles_mutate",
    ),
    path(
        "operations/offices/<int:office_id>",
        office_administration_detail,
        name="admin_office",
    ),
    path(
        "operations/offices/<int:office_id>/update",
        office_administration_update,
        name="admin_office_update",
    ),
    path(
        "operations/offices/<int:office_id>/structure",
        office_administration_structure,
        name="admin_office_structure",
    ),
    path(
        "operations/offices/<int:office_id>/impact",
        office_administration_impact,
        name="admin_office_impact",
    ),
    path(
        "operations/offices/<int:office_id>/contacts",
        office_administration_contact,
        name="admin_office_contact",
    ),
    path(
        "operations/offices/<int:office_id>/contacts/end",
        office_administration_contact_end,
        name="admin_office_contact_end",
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
        "operations/new-agents/<int:user_id>/headshot",
        onboarding_headshot,
        name="new_agent_onboarding_headshot",
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
        "operations/new-agents/<int:user_id>/contract",
        onboarding_contract,
        name="new_agent_onboarding_contract",
    ),
    path(
        "operations/new-agents/<int:user_id>/handoff",
        onboarding_handoff,
        name="new_agent_onboarding_handoff",
    ),
    path(
        "operations/new-agents/<int:user_id>/notices",
        onboarding_notice,
        name="new_agent_onboarding_notice",
    ),
]
