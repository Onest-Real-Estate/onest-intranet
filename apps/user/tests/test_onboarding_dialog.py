"""Dashboard-hosted onboarding dialog: gated props, activation center, deep links.

The dialog is presentation. These tests prove the server is the boundary: what
the dashboard serializes under the strict gate, that routes stay blocked, and
when the released activation center is asked to open.
"""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from apps.user.models import User
from apps.user.tests.test_onboarding import make_agent
from apps.user.tests.test_onboarding_profile import (
    CONTACT,
    INERTIA,
    agent,
    complete_profile,
    save,
)

WIDGET_PROPS = ("metrics", "announcements", "actionItems", "training", "schedule")


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def dashboard_page(client, query: str = "", **headers) -> dict:
    response = client.get(f"{reverse('dashboard')}{query}", **INERTIA, **headers)
    assert response.status_code == 200, response.content[:300]
    body = json.loads(response.content)
    assert body["component"] == "Dashboard"
    return body


def partial_headers(*keys: str) -> dict:
    return {
        "HTTP_X_INERTIA_PARTIAL_COMPONENT": "Dashboard",
        "HTTP_X_INERTIA_PARTIAL_DATA": ",".join(keys),
    }


# ---------------------------------------------------------------------------
# Strict gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_strict_gate_dashboard_carries_the_setup_dialog_and_no_widget_providers(
    client,
):
    client.force_login(agent())
    body = dashboard_page(client, "?section=contact&onboarding=open")
    props = body["props"]

    assert "deferredProps" not in body
    assert props["onboardingJourney"]["strictGateActive"] is True
    assert props["onboardingProfile"]["profileFlow"]["currentSection"] == "contact"
    assert "onboardingActivation" not in props
    assert props["features"] == {}
    assert set(WIDGET_PROPS).isdisjoint(props)


@pytest.mark.django_db
def test_strict_gate_partial_reload_cannot_request_widget_data(client):
    client.force_login(agent())
    body = dashboard_page(client, **partial_headers(*WIDGET_PROPS))
    assert set(WIDGET_PROPS).isdisjoint(body["props"])
    assert "deferredProps" not in body


@pytest.mark.django_db
def test_strict_gate_validation_error_rerenders_the_dashboard_dialog(client):
    client.force_login(agent())
    response = save(client, "contact", {**CONTACT, "zip_code": "2203"})
    assert response.status_code == 422
    body = json.loads(response.content)

    assert body["component"] == "Dashboard"
    assert "deferredProps" not in body
    assert body["props"]["features"] == {}
    assert body["props"]["onboardingJourney"]["strictGateActive"] is True
    setup = body["props"]["onboardingProfile"]
    assert setup["profileFlow"]["currentSection"] == "contact"
    assert "zip_code" in setup["validation"]["fields"]
    assert setup["initial"]["zipCode"] == "2203"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "route_name", ["profile", "my_tools", "it_support", "action_items_queue"]
)
@pytest.mark.parametrize("inertia_visit", [False, True])
def test_deep_links_stay_server_blocked_behind_the_dialog(
    client, route_name, inertia_visit
):
    client.force_login(agent())
    headers = INERTIA if inertia_visit else {}
    response = client.get(reverse(route_name), **headers)
    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_section_from_a_bookmark_is_validated_by_the_server(client):
    client.force_login(agent())
    props = dashboard_page(client, "?section=../admin")["props"]
    assert props["onboardingProfile"]["profileFlow"]["currentSection"] == "identity"


@pytest.mark.django_db
def test_non_agent_dashboard_never_carries_onboarding_dialog_props(client):
    client.force_login(User.objects.create_user(email="operations@example.com"))
    props = dashboard_page(client, "?onboarding=open&section=contact")["props"]
    assert "onboardingJourney" not in props
    assert "onboardingProfile" not in props
    assert "onboardingActivation" not in props


# ---------------------------------------------------------------------------
# Released activation center
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_activation_center_opens_once_per_login_then_on_request(client, media_root):
    user = agent()
    client.force_login(user)
    complete_profile(client)

    first = dashboard_page(client)
    props = first["props"]
    assert props["onboardingJourney"]["strictGateActive"] is False
    assert props["onboardingJourney"]["activationComplete"] is False
    assert "onboardingProfile" not in props
    assert "deferredProps" in first
    assert props["onboardingActivation"]["autoOpen"] is True
    assert props["onboardingActivation"]["office"]["office"]["name"]

    # Ordinary navigation does not nag, and a stale section link is inert.
    again = dashboard_page(client, "?section=contact")["props"]
    assert again["onboardingActivation"]["autoOpen"] is False
    assert "onboardingProfile" not in again

    # The persistent entry and old links can always ask for it.
    requested = dashboard_page(client, "?onboarding=open")["props"]
    assert requested["onboardingActivation"]["autoOpen"] is True

    # A new login prompts once more.
    client.logout()
    client.force_login(user)
    assert dashboard_page(client)["props"]["onboardingActivation"]["autoOpen"] is True


@pytest.mark.django_db
def test_partial_reload_does_not_spend_the_login_prompt(client, media_root):
    client.force_login(agent())
    complete_profile(client)

    partial = dashboard_page(client, **partial_headers("greeting"))
    assert "onboardingActivation" not in partial["props"]
    assert dashboard_page(client)["props"]["onboardingActivation"]["autoOpen"] is True


@pytest.mark.django_db
def test_completed_legacy_agent_is_not_prompted(client):
    user = make_agent(
        User.objects.create_user(email="legacy@example.com", profile_completed=True)
    )
    client.force_login(user)
    props = dashboard_page(client)["props"]
    assert "onboardingProfile" not in props
    if props["onboardingJourney"]["activationComplete"]:
        assert props["onboardingActivation"] == {"autoOpen": False, "office": None}
