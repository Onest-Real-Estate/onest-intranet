from django.urls import path

from apps.onboarding_tools.views import (
    agent_tools,
    my_tools,
    reorder_tools_view,
    save_tool_view,
    set_tool_state,
    team_readiness,
    tool_catalog,
)

urlpatterns = [
    # Every agent's own checklist. No grant: a person is always entitled to
    # know what they are expected to have and how to get it.
    path("my-tools", my_tools, name="my_tools"),
    path("operations/tool-readiness", team_readiness, name="team_tool_readiness"),
    path(
        "operations/tool-readiness/<int:agent_id>",
        agent_tools,
        name="agent_tools",
    ),
    path(
        "operations/tool-readiness/<int:agent_id>/state",
        set_tool_state,
        name="agent_tool_state",
    ),
    # Catalog administration. Brokerage-wide configuration, so it sits under
    # operations rather than beside the agent's own checklist.
    path(
        "operations/tool-catalog",
        tool_catalog,
        name="onboarding_tool_catalog",
    ),
    path(
        "operations/tool-catalog/new",
        save_tool_view,
        name="onboarding_tool_create",
    ),
    path(
        "operations/tool-catalog/reorder",
        reorder_tools_view,
        name="onboarding_tool_reorder",
    ),
    path(
        "operations/tool-catalog/<slug:slug>",
        save_tool_view,
        name="onboarding_tool_save",
    ),
]
