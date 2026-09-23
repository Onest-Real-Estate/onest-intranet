"""The agent's own "I have this", and the two ways a card gets them unstuck.

The tick is a separate fact from ``state``: it is the agent's to set, only on
their own checklist, and it never moves the staff-confirmed readiness figure.
"""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.onboarding_tools import services, views
from apps.onboarding_tools.models import AgentToolStatus, ToolState
from apps.onboarding_tools.tests.test_catalog import person, seeded, tool
from apps.training.tool_guides import ActivationGuide
from apps.web.tests.test_permissions import inertia_page_script

__all__ = ["seeded"]


def tick(client, slug: str, have: bool):
    # JSON, because that is what Inertia's router actually sends.
    return client.post(
        reverse("my_tool_have", args=[slug]),
        data=json.dumps({"have": have}),
        content_type="application/json",
    )


def page_tools(response) -> dict[str, dict]:
    props = inertia_page_script(response)["props"]
    return {item["slug"]: item for group in props["groups"] for item in group["tools"]}


@pytest.mark.django_db
def test_an_agent_ticks_their_own_tool_without_moving_readiness(
    seeded, client, django_capture_on_commit_callbacks
):
    agent = person("agent@example.com")
    client.force_login(agent)
    before = services.readiness_for(agent)

    with django_capture_on_commit_callbacks(execute=True):
        response = tick(client, "rpr", True)

    assert response.status_code == 302
    assert response["Location"] == reverse("my_tools")
    row = AgentToolStatus.objects.get(agent=agent, tool=tool("rpr"))
    assert row.agent_confirmed_at is not None
    # The claim is not a confirmation: state and the figure are untouched.
    assert row.state == ToolState.NOT_STARTED
    assert services.readiness_for(agent) == before
    assert AuditEvent.objects.filter(action="onboarding_tool.agent_confirmed").exists()


@pytest.mark.django_db
def test_unticking_clears_the_mark(seeded, client, django_capture_on_commit_callbacks):
    agent = person("agent@example.com")
    client.force_login(agent)
    tick(client, "rpr", True)

    with django_capture_on_commit_callbacks(execute=True):
        tick(client, "rpr", False)

    row = AgentToolStatus.objects.get(agent=agent, tool=tool("rpr"))
    assert row.agent_confirmed_at is None
    assert AuditEvent.objects.filter(
        action="onboarding_tool.agent_unconfirmed"
    ).exists()


@pytest.mark.django_db
def test_a_double_tick_is_one_event(seeded, client, django_capture_on_commit_callbacks):
    client.force_login(person("agent@example.com"))

    with django_capture_on_commit_callbacks(execute=True):
        tick(client, "rpr", True)
        tick(client, "rpr", True)

    assert (
        AuditEvent.objects.filter(action="onboarding_tool.agent_confirmed").count() == 1
    )


@pytest.mark.django_db
def test_a_tick_keeps_staff_confirmation_intact(seeded, client):
    """Unticking must never undo what oNEST confirmed."""
    from apps.onboarding_tools.tests.test_catalog import manager

    agent = person("agent@example.com")
    services.set_state(
        actor=manager(), agent=agent, tool=tool("rpr"), state=ToolState.READY
    )
    client.force_login(agent)

    tick(client, "rpr", True)
    tick(client, "rpr", False)

    row = AgentToolStatus.objects.get(agent=agent, tool=tool("rpr"))
    assert row.state == ToolState.READY
    assert row.ready_at is not None


@pytest.mark.django_db
def test_a_tool_off_the_agents_checklist_is_refused(seeded, client):
    """A Virginia agent cannot record Connecticut's MLS."""
    agent = person("agent@example.com", "fairfax-va")
    client.force_login(agent)

    response = tick(client, "smartmls", True)

    assert response.status_code == 404
    assert not AgentToolStatus.objects.filter(agent=agent).exists()


@pytest.mark.django_db
def test_ticking_needs_a_session(seeded, client):
    response = tick(client, "rpr", True)
    assert response.status_code == 302
    assert "next=" in response["Location"]
    assert not AgentToolStatus.objects.exists()


@pytest.mark.django_db
def test_ticking_refuses_get(seeded, client):
    client.force_login(person("agent@example.com"))
    response = client.get(reverse("my_tool_have", args=["rpr"]))
    assert response.status_code == 405


@pytest.mark.django_db
def test_the_page_carries_the_tick_and_a_tool_specific_support_link(seeded, client):
    agent = person("agent@example.com")
    client.force_login(agent)
    tick(client, "rpr", True)

    tools = page_tools(client.get(reverse("my_tools")))

    assert tools["rpr"]["haveIt"] is True
    assert tools["rpr"]["haveItAt"]
    assert tools["onedrive"]["haveIt"] is False
    assert tools["onedrive"]["supportHref"] == "/support/it?tool=onedrive"
    assert tools["onedrive"]["training"] is None


@pytest.mark.django_db
def test_a_catalog_request_path_wins_over_the_default_support_link(seeded, client):
    row = tool("rpr")
    row.request_path = "/support/it?category=software"
    row.save(update_fields=["request_path"])
    client.force_login(person("agent@example.com"))

    tools = page_tools(client.get(reverse("my_tools")))

    assert tools["rpr"]["supportHref"] == "/support/it?category=software"


@pytest.mark.django_db
def test_the_page_links_the_tools_training(seeded, client, monkeypatch):
    """The join itself is covered by the training app; this pins the shape."""
    guide = ActivationGuide(
        tool_code="rpr",
        content_id=12,
        title="Getting started with RPR",
        summary="",
        estimated_minutes=6,
        href="/training/12",
        completed=False,
        in_progress=True,
        has_transcript=False,
        version_number=1,
    )
    asked: list[list[str]] = []

    def fake_guides(user, codes, **_kwargs):
        asked.append(list(codes))
        return {"rpr": guide}

    monkeypatch.setattr(views, "activation_guides_for", fake_guides)
    client.force_login(person("agent@example.com"))

    tools = page_tools(client.get(reverse("my_tools")))

    assert tools["rpr"]["training"] == {
        "href": "/training/12",
        "title": "Getting started with RPR",
        "minutes": 6,
        "completed": False,
        "inProgress": True,
    }
    assert tools["onedrive"]["training"] is None
    # One lookup for the whole checklist, not one per tool.
    assert len(asked) == 1
    assert "onedrive" in asked[0]


@pytest.mark.django_db
def test_support_opens_already_about_the_tool(seeded, client):
    client.force_login(person("agent@example.com"))

    response = client.get(reverse("it_support"), {"tool": "rpr", "subject": "x"})

    draft = inertia_page_script(response)["props"]["draft"]
    assert draft == {"subject": f"Help with {tool('rpr').name}", "category": "software"}


@pytest.mark.django_db
def test_support_ignores_an_unknown_tool(seeded, client):
    client.force_login(person("agent@example.com"))

    response = client.get(reverse("it_support"), {"tool": "not-a-tool"})

    assert inertia_page_script(response)["props"]["draft"] == {}
