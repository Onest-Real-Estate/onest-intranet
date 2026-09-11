"""Quick-documents dashboard widget, backed by the office resource library.

The panel is a short window on `office_resources`. It reuses
`effective_resources`, which is that page's own single visibility gate — the
office scope chain, active window, and slug precedence all resolved there — so
the dashboard can never surface a resource the library would have withheld.
"""

from __future__ import annotations

from collections import Counter

from django.urls import reverse

from apps.user.models import OfficeResource
from apps.user.services.office_resources import effective_resources
from apps.web.capability import has_capability
from apps.web.dashboard.envelope import ProviderResult, empty, ready
from apps.web.dashboard.providers import DashboardContext

_MAX_ROWS = 5

#: Outer bound on the onboarding population a single funnel will aggregate.
_ONBOARDING_CAP = 500

#: The resources worth a dashboard shortcut. A `content` resource is a page of
#: prose that has to be read in place; a file and a link are things somebody
#: reaches for mid-task, which is what this panel is for.
_SHORTCUT_TYPES = (OfficeResource.ResourceType.FILE, OfficeResource.ResourceType.LINK)


def _href(resource: OfficeResource) -> str:
    if resource.resource_type == OfficeResource.ResourceType.FILE:
        # Protected storage: the download view re-checks scope on every hit,
        # so the panel links to it rather than to a storage URL.
        return reverse("office_resources_download", args=[resource.slug])
    if resource.resource_type == OfficeResource.ResourceType.LINK and resource.url:
        return resource.url
    return reverse("office_resources")


def quick_documents(context: DashboardContext) -> ProviderResult:
    """Files and links from the reader's effective office resource library."""
    resources = [
        resource
        for resource in effective_resources(context.user)
        if resource.resource_type in _SHORTCUT_TYPES
        and resource.processing_state == OfficeResource.ProcessingState.READY
    ]

    if not resources:
        return empty(
            "No documents yet",
            "Forms and files published for your office appear here.",
            action_label="Open office resources",
            action_href=reverse("office_resources"),
        )

    return ready(
        {
            "total": len(resources),
            "items": [
                {
                    "id": resource.slug,
                    "name": resource.title,
                    "kind": resource.resource_type,
                    "href": _href(resource),
                    "office": resource.owner_office.name,
                }
                for resource in resources[:_MAX_ROWS]
            ],
            "viewAllHref": reverse("office_resources"),
        }
    )


def agent_onboarding(context: DashboardContext) -> ProviderResult:
    """New-agent onboarding as a funnel over the reader's administered people.

    Population and scope both come from ``new_agent_queryset`` — the same
    service the New Agent List uses — so the funnel can never count somebody
    the reader is not allowed to administer.
    """
    from apps.user.services.onboarding_state import (
        OverallStatus,
        build_onboarding_states,
        new_agent_queryset,
    )

    user = context.user
    if not has_capability(user, "web.view_new_agents", access=context.access):
        return empty(
            "No onboarding in scope",
            "New agents appear here once you can administer them.",
        )

    # Bounded: the funnel is a count, and a brokerage-wide reader should not
    # pull every record to produce four numbers.
    people = list(
        new_agent_queryset(user, at=context.now, access=context.access)[
            :_ONBOARDING_CAP
        ]
    )
    if not people:
        return empty(
            "Nobody onboarding",
            "Agents in their first weeks appear here with what is still open.",
            action_label="Open the new agent list",
            action_href=reverse("admin_new_agents"),
        )

    counts = Counter(state.overall_status for state in build_onboarding_states(people))
    stages = [
        ("not_started", "Not started", OverallStatus.NOT_STARTED, "neutral"),
        ("in_progress", "In progress", OverallStatus.IN_PROGRESS, "info"),
        ("blocked", "Blocked", OverallStatus.BLOCKED, "destructive"),
        ("ready", "Ready", OverallStatus.READY, "success"),
    ]
    total = sum(counts.values())
    return ready(
        {
            "stages": [
                {
                    "key": key,
                    "label": label,
                    # Formatted server-side: the page never rounds a figure.
                    "value": str(counts.get(status, 0)),
                    "tone": tone,
                }
                for key, label, status, tone in stages
            ],
            "caption": (
                f"{total} agent onboarding"
                if total == 1
                else f"{total} agents onboarding"
            ),
            "viewAllHref": reverse("admin_new_agents"),
        }
    )
