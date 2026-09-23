"""Two surfaces over one catalog.

* ``my_tools`` — an agent's own checklist. No permission: a person is always
  entitled to know what they are expected to have and how to get it.
* ``team_readiness`` — how far the people this reader covers have got. Scoped
  by the ordinary office tree, with no extra grant: if you may already see the
  agent in the directory, you may see whether their email works.

Writes go through :mod:`apps.onboarding_tools.services`, which authorizes
against the *stored* agent and refuses self-management.
"""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from inertia import inertia, render

from apps.onboarding_tools import services
from apps.onboarding_tools.models import (
    COMPLETE_STATES,
    AgentToolStatus,
    OnboardingTool,
)
from apps.onboarding_tools.payloads import (
    grouped_payload,
    readiness_payload,
    state_options,
)
from apps.training.tool_guides import activation_guides_for
from apps.user.models import User
from apps.web.authorization import enforce_policy, scope_queryset_for_user_office
from apps.web.capability import access_for
from apps.web.contracts import empty_validation_errors

MY_TOOLS_PAGE = "MyTools"
TEAM_PAGE = "TeamToolReadiness"


def _agent_props(request: HttpRequest, agent: User, *, managed: bool) -> dict[str, Any]:
    checklist = services.checklist_for(agent)
    actor = cast(User, request.user)
    # Guides are resolved for the *reader*: the button opens the item under the
    # reader's own training visibility, so offering one they cannot open would
    # be a dead link. Two bounded queries, whatever the catalog size.
    guides = activation_guides_for(actor, [item.tool.slug for item in checklist])
    return {
        "agent": {
            "id": agent.pk,
            "name": agent.get_full_name() or agent.get_short_name(),
            "office": agent.office.name if agent.office else None,
            "isSelf": agent.pk == actor.pk,
        },
        "groups": grouped_payload(checklist, guides),
        "readiness": readiness_payload(services.readiness_for(agent)),
        # Whether *this* reader may move *this* agent's rows. Self-management is
        # refused, so an administrator opening their own page gets a read-only
        # checklist like anybody else.
        "canManage": managed and services.can_manage(actor, agent),
        "stateOptions": state_options(),
        "supportPath": reverse("it_support"),
        "errors": empty_validation_errors(),
    }


@enforce_policy("my_tools")
@inertia(MY_TOOLS_PAGE)
def my_tools(request: HttpRequest):
    """The signed-in agent's own checklist."""
    return _agent_props(request, cast(User, request.user), managed=False)


@enforce_policy("my_tools")
@require_POST
def confirm_my_tool(request: HttpRequest, slug: str):
    """The agent ticks, or unticks, "I have this" on their own checklist.

    Self only, by construction: the row written is always the signed-in
    user's, and nothing posted can name anybody else.
    """
    # ``"1"`` is what the JSON middleware makes of ``true``; ``"true"`` is a
    # plain form post. Anything else, including a missing value, unticks.
    confirmed = (request.POST.get("have") or "").strip().lower() in {"1", "true"}
    try:
        services.set_agent_confirmation(
            agent=cast(User, request.user), slug=slug, confirmed=confirmed
        )
    except ValidationError:
        # The slug is not on this agent's checklist. A 404 rather than a form
        # error: nothing on the page could have produced it.
        raise Http404("No tool matches that slug.") from None
    return redirect(reverse("my_tools"))


def _readable_agents(request: HttpRequest):
    """People whose progress this reader may see.

    Scoped in SQL before counting: a total is a disclosure too, and a manager
    whose reach is one branch must not learn how many agents exist elsewhere.
    """
    reader = cast(User, request.user)
    return scope_queryset_for_user_office(
        reader,
        User.objects.filter(is_active=True).exclude(pk=reader.pk),
        field_name="office",
        access=access_for(reader),
    ).select_related("office")


@enforce_policy("team_tool_readiness")
@inertia(TEAM_PAGE)
def team_readiness(request: HttpRequest):
    """How far the people this reader covers have got.

    The per-agent figure is computed with one aggregate over the whole set
    rather than by resolving each agent's catalog in turn — the latter is a
    query per person, which is exactly how a team page becomes unusable at
    forty agents.
    """
    query = (request.GET.get("q") or "").strip()[:120]
    readable = _readable_agents(request)
    if query:
        # Narrows the already-scoped set. A name matching somebody outside the
        # reader's reach simply finds nothing.
        readable = readable.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    agents = list(readable.order_by("first_name", "last_name", "pk")[:200])
    if not agents:
        return {
            "agents": [],
            "filters": {"q": query},
            "errors": empty_validation_errors(),
        }

    # One read for everybody's completed rows. The denominator comes from the
    # catalog resolved per office, which is a handful of distinct offices
    # rather than one lookup per agent.
    done = dict(
        AgentToolStatus.objects.filter(agent__in=agents, state__in=COMPLETE_STATES)
        .values("agent_id")
        .annotate(total=Count("pk"))
        .values_list("agent_id", "total")
    )
    required_by_office: dict[int | None, int] = {}
    for agent in agents:
        key = agent.office_id
        if key not in required_by_office:
            required_by_office[key] = (
                OnboardingTool.objects.for_office(agent.office)
                .filter(is_required=True)
                .count()
            )

    rows = []
    for agent in agents:
        total = required_by_office.get(agent.office_id, 0)
        ready = min(done.get(agent.pk, 0), total)
        rows.append(
            {
                "id": agent.pk,
                "name": agent.get_full_name() or agent.get_short_name(),
                "office": agent.office.name if agent.office else None,
                "ready": ready,
                "total": total,
                "percent": 100 if total == 0 else round(ready * 100 / total),
                "complete": ready >= total,
            }
        )
    # Least ready first: this page exists to find who is still blocked, and an
    # alphabetical list makes somebody read forty rows to find the three that
    # matter.
    rows.sort(key=lambda row: (row["complete"], row["percent"], row["name"]))
    return {
        "agents": rows,
        "filters": {"q": query},
        "errors": empty_validation_errors(),
    }


@enforce_policy("team_tool_readiness")
@inertia(MY_TOOLS_PAGE)
def agent_tools(request: HttpRequest, agent_id: int):
    """One agent's checklist, for somebody who covers them.

    Loaded through the scoped queryset, so an agent outside the reader's reach
    is a 404 rather than a 403 — confirming an id exists is itself a disclosure
    across a scope boundary.
    """
    agent = _readable_agents(request).filter(pk=agent_id).first()
    if agent is None:
        raise Http404("No agent matches that id.")
    return _agent_props(request, agent, managed=True)


def _rerender(request: HttpRequest, agent: User, errors: dict) -> HttpResponse:
    response = render(
        request,
        MY_TOOLS_PAGE,
        {**_agent_props(request, agent, managed=True), "errors": errors},
    )
    response.status_code = 422
    return response


@enforce_policy("team_tool_readiness")
@require_POST
def set_tool_state(request: HttpRequest, agent_id: int):
    agent = _readable_agents(request).filter(pk=agent_id).first()
    if agent is None:
        raise Http404("No agent matches that id.")

    tool = OnboardingTool.objects.filter(
        slug=(request.POST.get("tool") or "").strip()
    ).first()
    if tool is None:
        return _rerender(
            request, agent, {"fields": {"tool": ["Unknown tool."]}, "form": []}
        )

    try:
        services.set_state(
            actor=request.user,
            agent=agent,
            tool=tool,
            state=(request.POST.get("state") or "").strip(),
            note=request.POST.get("note") or "",
        )
    except PermissionDenied:
        raise
    except ValidationError as exc:
        errors = (
            {"fields": dict(exc.message_dict), "form": []}
            if hasattr(exc, "message_dict")
            else {"fields": {}, "form": list(exc.messages)}
        )
        return _rerender(request, agent, errors)
    return redirect(reverse("agent_tools", args=[agent.pk]))


# --------------------------------------------------------------------------- #
# Catalog administration
# --------------------------------------------------------------------------- #

CATALOG_PAGE = "OnboardingToolCatalog"


def _catalog_offices(request: HttpRequest):
    """Office nodes this administrator may attach a tool to."""
    from apps.user.models import Office
    from apps.web.authorization import scope_queryset_for_offices

    return scope_queryset_for_offices(
        cast(User, request.user), Office.objects.filter(is_active=True)
    ).order_by("name", "pk")


def _catalog_props(
    request: HttpRequest, *, errors=None, editing: str = "", draft=None
) -> dict[str, Any]:
    from apps.onboarding_tools.catalog_admin import (
        CatalogFilters,
        CatalogShow,
        catalog_rows,
        office_paths,
    )
    from apps.onboarding_tools.forms import MAX_STEPS
    from apps.onboarding_tools.models import Provisioning, ToolGroup

    actor = cast(User, request.user)
    filters = CatalogFilters.from_params(request.GET)
    catalog = catalog_rows(actor, filters)
    offices = list(_catalog_offices(request)[:500])
    paths = office_paths(offices)

    return {
        "groups": catalog["groups"],
        "summary": catalog["summary"],
        "filters": filters.payload(),
        # Reordering a filtered list would move a row relative to neighbours
        # the administrator cannot see, so the page offers it only unfiltered.
        "canReorder": not filters.narrowed,
        "offices": [
            {
                "value": str(office.pk),
                "label": office.name,
                "path": paths.get(office.pk, office.name),
                "kind": office.kind,
            }
            for office in offices
        ],
        "options": {
            "groups": [
                {"value": code, "label": str(label)}
                for code, label in ToolGroup.choices
            ],
            "provisioning": [
                {"value": code, "label": str(label)}
                for code, label in Provisioning.choices
            ],
            "show": [
                {"value": CatalogShow.ALL.value, "label": "All tools"},
                {"value": CatalogShow.ATTENTION.value, "label": "Needs attention"},
                {"value": CatalogShow.ACTIVE.value, "label": "Active"},
                {"value": CatalogShow.INACTIVE.value, "label": "Inactive"},
            ],
        },
        "links": {
            "teamReadiness": reverse("team_tool_readiness"),
            "trainingAdmin": reverse("admin_training"),
        },
        "maxSteps": MAX_STEPS,
        # Which row's editor is open, and what it should be filled with. Both
        # come back on a refused save so nothing typed is lost.
        "editing": editing,
        "draft": draft or {},
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("onboarding_tool_catalog")
@inertia(CATALOG_PAGE)
def tool_catalog(request: HttpRequest):
    """Every tool in the catalog, and the editor for one of them."""
    return _catalog_props(request, editing=(request.GET.get("edit") or "").strip())


def _checked(request: HttpRequest, name: str) -> bool:
    """A box as a browser form (``on``) or the JSON middleware (``1``) sends it."""
    return (request.POST.get(name) or "").lower() in {"on", "1", "true"}


def _draft_from(request: HttpRequest) -> dict[str, Any]:
    return {
        "slug": request.POST.get("slug") or "",
        "name": request.POST.get("name") or "",
        "description": request.POST.get("description") or "",
        "group": request.POST.get("group") or "",
        "provisioning": request.POST.get("provisioning") or "",
        "openUrl": request.POST.get("open_url") or "",
        "helpUrl": request.POST.get("help_url") or "",
        "contact": request.POST.get("contact_label") or "",
        "requestPath": request.POST.get("request_path") or "",
        "companyWide": _checked(request, "company_wide"),
        "required": _checked(request, "is_required"),
        "active": _checked(request, "is_active"),
        "sortOrder": request.POST.get("sort_order") or "0",
        "steps": [step for step in request.POST.getlist("step") if step.strip()],
        "officeIds": [
            int(value) for value in request.POST.getlist("offices") if value.isdigit()
        ],
    }


@enforce_policy("onboarding_tool_catalog")
@require_POST
def save_tool_view(request: HttpRequest, slug: str = ""):
    from apps.onboarding_tools.forms import OnboardingToolForm

    instance = OnboardingTool.objects.filter(slug=slug).first() if slug else None
    if slug and instance is None:
        raise Http404("No tool matches that identifier.")

    form = OnboardingToolForm(
        request.POST,
        instance=instance,
        scoped_offices=_catalog_offices(request),
        steps=request.POST.getlist("step"),
    )
    if not form.is_valid():
        return _catalog_422(request, form, editing=slug or "new")

    try:
        tool = services.save_tool(actor=request.user, form=form, instance=instance)
    except PermissionDenied:
        raise
    return redirect(f"{reverse('onboarding_tool_catalog')}?saved={tool.slug}")


def _catalog_422(request: HttpRequest, form, *, editing: str) -> HttpResponse:
    response = render(
        request,
        CATALOG_PAGE,
        _catalog_props(
            request,
            errors={"fields": dict(form.errors), "form": list(form.non_field_errors())},
            editing=editing,
            draft=_draft_from(request),
        ),
    )
    response.status_code = 422
    return response


@enforce_policy("onboarding_tool_catalog")
@require_POST
def reorder_tools_view(request: HttpRequest):
    group = (request.POST.get("group") or "").strip()
    slugs = [slug for slug in request.POST.getlist("order") if slug]
    services.reorder_tools(actor=request.user, group=group, slugs=slugs)
    return redirect(reverse("onboarding_tool_catalog"))
