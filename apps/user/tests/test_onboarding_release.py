"""Release pass: the first-login journey proven as one system.

Each domain has its own focused suite. These tests drive the real seams in
sequence — Microsoft sign-in, the dashboard dialog, office handoff delivery,
the scoped administrator workspace, conditional guides, contract initiation,
reset, and hostile requests — so a contract drift between two domains fails
here even when both halves pass on their own.
"""

from __future__ import annotations

import json
import logging

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.audit.models import AuditEvent, DomainEvent
from apps.contract.models import AgentContract
from apps.notifications.actions import resolve_action_href
from apps.notifications.consumers import deliver_for_event
from apps.notifications.models import Notification
from apps.onboarding_tools.models import AgentToolStatus, ToolState
from apps.user.models import User, UserOnboardingCase
from apps.user.services import onboarding_state
from apps.user.services.onboarding_metrics import journey_health
from apps.user.services.onboarding_office import OFFICE_HANDOFF_EVENT
from apps.user.services.onboarding_operations import reset_required_setup
from apps.user.services.onboarding_state import new_agent_filter
from apps.user.tests.test_microsoft_sso import (
    GRAPH_PROFILE,
    providers,
    sign_in_with_microsoft,
)
from apps.user.tests.test_onboarding import assignable_office
from apps.user.tests.test_onboarding_administration import (
    action_version,
    branch_manager,
    company_admin,
    event_envelope,
)
from apps.user.tests.test_onboarding_next_steps import guide
from apps.user.tests.test_onboarding_office_handoff import (
    administrator,
    clear_branch_admins,
    contact,
)
from apps.user.tests.test_onboarding_profile import (
    complete_profile,
    fill_sections,
    finalize,
    flow,
    save,
    upload_headshot,
)

INERTIA = {"X-Inertia": "true"}
PRIVATE_VALUES = ("1 Main St", "202.555.0100", "123-456-789", "VA-9911")


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def microsoft_agent(**claims) -> User:
    """A brand-new account created by the real allauth Microsoft callback."""
    profile = {**GRAPH_PROFILE, **claims}
    with override_settings(SOCIALACCOUNT_PROVIDERS=providers(verified_email=True)):
        request, response = sign_in_with_microsoft(profile)
    assert response.status_code == 302
    assert response["Location"] == reverse("dashboard")
    return User.objects.get(pk=request.user.pk)


def dashboard(client: Client, **partial: str) -> dict:
    response = client.get(reverse("dashboard"), headers={**INERTIA, **partial})
    assert response.status_code == 200, response.content[:300]
    return json.loads(response.content)["props"]


def journey(client: Client) -> dict:
    return dashboard(client)["onboardingJourney"]


def deliver_pending(name: str) -> None:
    for event in DomainEvent.objects.filter(name=name):
        deliver_for_event(event_envelope(event))


def tool_row(payload: dict, key: str) -> dict:
    return next(item for item in payload["tools"] if item["key"] == key)


def workspace_post(client: Client, route: str, agent: User, data: dict):
    return client.post(
        reverse(route, args=[agent.pk]),
        json.dumps({**data, "expected_version": action_version(agent)}),
        content_type="application/json",
        headers=INERTIA,
    )


# --------------------------------------------------------------------------- #
# Scenarios 1, 3–8: the whole journey, one agent, every domain
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_new_agent_completes_the_whole_journey_across_every_domain(media_root, caplog):
    clear_branch_admins()
    selected = assignable_office()
    branch_admin = administrator("branch.admin@example.com", office_scope=selected)
    contact(branch_admin, contact_office=selected, primary=True)
    guide(slug="lofty-activation", tool_code="lofty")
    guide(slug="skyslope-activation", tool_code="skyslope")

    # 1. Complete Microsoft claims: the account exists and the legal name is
    #    Microsoft's, so onboarding cannot overwrite it.
    agent = microsoft_agent(
        id="entra-new-agent",
        mail="new.agent@onest.realestate",
        givenName="Bob",
        surname="Lee",
        displayName="Bob Lee",
    )
    browser = Client()
    browser.force_login(agent)
    first = dashboard(browser)
    assert first["onboardingJourney"]["strictGateActive"] is True
    assert first["onboardingJourney"]["currentStep"]["code"] == "profile"
    assert first["onboardingProfile"]["identity"]["legalNameLocked"] is True
    assert "dashboardWidgets" not in first
    blocked = browser.get(reverse("profile"))
    assert blocked.status_code == 302
    assert blocked["Location"].startswith(reverse("dashboard"))

    # 3. Upload, replace, save every section, confirm the office, finalize.
    upload_headshot(browser, name="first.jpg")
    upload_headshot(browser, name="replacement.jpg")
    fill_sections(browser)
    assert finalize(browser, json_body=True).status_code == 302
    agent.refresh_from_db()
    assert agent.profile_completed is True
    assert (agent.first_name, agent.last_name) == ("Bob", "Lee")
    assert agent.headshot.name.endswith(".jpg")

    waiting = journey(browser)
    assert waiting["strictGateActive"] is False
    assert waiting["requiredSetupComplete"] is True
    assert waiting["currentStep"]["code"] == "activation"
    assert waiting["nextAction"]["code"] == "wait_for_office"
    assert waiting["activationGuides"]["lofty"]["state"] == "locked"
    assert waiting["activationGuides"]["skyslope"]["state"] == "locked"

    # 4. The correct office administrator receives one scoped, redacted case.
    deliver_pending(OFFICE_HANDOFF_EVENT)
    deliver_pending(OFFICE_HANDOFF_EVENT)
    [notice] = Notification.objects.filter(event_key=OFFICE_HANDOFF_EVENT)
    assert notice.recipient == branch_admin
    for private in PRIVATE_VALUES:
        assert private not in json.dumps(notice.action_args)
    case = UserOnboardingCase.objects.get(user=agent)
    assert case.owner == branch_admin
    assert case.office_handoff_state == UserOnboardingCase.OfficeHandoffState.NOTIFIED

    notified_desk = Client()
    notified_desk.force_login(branch_admin)
    href = resolve_action_href(notice.action_key, notice.action_args)
    assert href is not None
    opened = notified_desk.get(href, headers=INERTIA)
    assert opened.status_code == 200
    assert json.loads(opened.content)["component"] == "OnboardingWorkspace"

    # Recording sends needs web.manage_new_agent_onboarding, which the office's
    # Branch Manager holds today (see docs/onboarding-support.md, open
    # decisions: whether the notified Branch Admin should hold it too).
    office_desk = Client()
    office_desk.force_login(branch_manager(selected.slug, "branch.manager@example.com"))

    # 5. Lofty's send unlocks Lofty's guide and nothing else.
    response = workspace_post(
        office_desk,
        "new_agent_onboarding_tools",
        agent,
        {"tool": "lofty", "action": "mark_invitation_sent"},
    )
    assert response.status_code == 302, response.content[:300]
    after_lofty = journey(browser)
    assert after_lofty["activationGuides"]["lofty"]["state"] == "available"
    assert after_lofty["activationGuides"]["skyslope"]["state"] == "locked"
    assert tool_row(after_lofty, "lofty")["state"] == ToolState.INVITATION_SENT

    # 6. SkySlope's send unlocks SkySlope's guide.
    response = workspace_post(
        office_desk,
        "new_agent_onboarding_tools",
        agent,
        {"tool": "skyslope", "action": "mark_invitation_sent"},
    )
    assert response.status_code == 302, response.content[:300]
    assert journey(browser)["activationGuides"]["skyslope"]["state"] == "available"

    # 7. Contract initiation shows as source-derived status for the agent.
    contracts_admin = Client()
    contracts_admin.force_login(company_admin())
    response = workspace_post(
        contracts_admin, "new_agent_onboarding_contract", agent, {}
    )
    assert response.status_code == 302, response.content[:300]
    assert AgentContract.objects.filter(recipient=agent).count() == 1
    with_contract = journey(browser)
    assert with_contract["contract"]["state"] == "generated"
    assert "contract_unavailable" not in {
        blocker["key"] for blocker in with_contract["blockers"]
    }

    # 8. Refresh, a second device, and a reconnect's journey-only reload all
    #    read the same database truth; nothing lives in the first browser.
    other_device = Client()
    other_device.force_login(agent)
    reconnect = dashboard(
        other_device,
        **{
            "X-Inertia-Partial-Component": "Dashboard",
            "X-Inertia-Partial-Data": "onboardingJourney",
        },
    )
    assert set(reconnect) == {"onboardingJourney"}
    for view in (
        journey(browser),
        journey(other_device),
        reconnect["onboardingJourney"],
    ):
        assert view["activationGuides"] == with_contract["activationGuides"]
        assert view["contract"] == with_contract["contract"]
        assert view["stateVersion"] == with_contract["stateVersion"]

    # Observability sees the same journey without identifying anyone.
    health = journey_health(User.objects.filter(pk=agent.pk), now=agent.date_joined)
    assert health.required_setup_completed == 1
    assert health.handoff_states["notified"] == 1
    lofty = next(tool for tool in health.tools if tool.tool == "lofty")
    assert lofty.invitations_sent == 1
    assert lofty.median_hours_to_invitation is not None
    for record in caplog.records:
        for private in (*PRIVATE_VALUES, "new.agent@onest.realestate"):
            assert private not in record.getMessage()


# --------------------------------------------------------------------------- #
# Scenario 2: partial Microsoft claims
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.parametrize(
    "claims",
    [
        {"givenName": "", "surname": "", "displayName": ""},
        {"givenName": "Pat", "surname": None, "displayName": "Pat"},
    ],
)
def test_partial_microsoft_claims_keep_the_name_editable_and_required(claims):
    agent = microsoft_agent(
        id="entra-partial", mail="partial@onest.realestate", **claims
    )
    browser = Client()
    browser.force_login(agent)

    props = flow(browser)
    assert props["onboardingJourney"]["strictGateActive"] is True
    assert props["identity"]["legalNameLocked"] is False
    assert props["profileFlow"]["fields"]["first_name"]["readOnly"] is False
    rejected = save(browser, "identity", {"first_name": "", "last_name": ""})
    assert rejected.status_code == 422
    accepted = save(browser, "identity", {"first_name": "Pat", "last_name": "Kim"})
    assert accepted.status_code == 302


# --------------------------------------------------------------------------- #
# Scenario 9: failures stay honest and never re-lock the agent
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_missing_admin_and_source_outages_are_honest_and_countable(
    media_root, monkeypatch
):
    clear_branch_admins()
    agent = microsoft_agent(id="entra-outage", mail="outage@onest.realestate")
    browser = Client()
    browser.force_login(agent)
    complete_profile(browser)

    # A contract source failure and the training source failing together.
    real_contract_states = onboarding_state.contract_states
    real_training_states = onboarding_state.training_states
    monkeypatch.setattr(
        onboarding_state,
        "contract_states",
        lambda users: {
            user.pk: onboarding_state._unavailable_contract_state() for user in users
        },
    )
    monkeypatch.setattr(
        onboarding_state,
        "training_states",
        lambda users: {
            user.pk: onboarding_state._unavailable_training_state() for user in users
        },
    )
    payload = journey(browser)
    blockers = {blocker["key"] for blocker in payload["blockers"]}
    assert {"office_handoff_failed", "contract_unavailable"} <= blockers
    assert payload["strictGateActive"] is False
    assert payload["requiredSetupComplete"] is True
    assert payload["activationComplete"] is False
    assert payload["officeHandoff"]["state"] == "notification_failed"
    assert payload["contract"]["state"] == "unavailable"

    health = journey_health(User.objects.filter(pk=agent.pk), now=agent.date_joined)
    assert health.agents_blocked_by_source == 1
    assert health.blockers["office_handoff_failed"] == 1
    assert health.failures["user.onboarding.office_handoff_unavailable"] == 1

    monkeypatch.setattr(onboarding_state, "contract_states", real_contract_states)
    monkeypatch.setattr(onboarding_state, "training_states", real_training_states)
    assert journey(browser)["contract"]["state"] == "not_started"


@pytest.mark.django_db
def test_inactive_office_and_unavailable_guide_do_not_strand_the_agent(
    media_root, caplog
):
    clear_branch_admins()
    agent = microsoft_agent(id="entra-retired", mail="retired@onest.realestate")
    browser = Client()
    browser.force_login(agent)
    upload_headshot(browser)
    fill_sections(browser)

    # The office is retired while the dialog is open: finalization refuses it
    # and sends the agent back to choose again, without losing saved values.
    retired = assignable_office()
    retired.is_active = False
    retired.save(update_fields=["is_active"])
    with caplog.at_level(logging.WARNING):
        refused = finalize(browser)
    assert refused.status_code in {409, 422}
    agent.refresh_from_db()
    assert agent.profile_completed is False
    assert agent.phone_number
    assert "onboarding_error code=" in caplog.text

    retired.is_active = True
    retired.save(update_fields=["is_active"])
    assert finalize(browser).status_code == 302

    # An invitation sent for a tool with no published guide falls back to the
    # vendor's help or request path instead of an empty button.
    admin = Client()
    admin.force_login(company_admin())
    response = workspace_post(
        admin,
        "new_agent_onboarding_tools",
        agent,
        {"tool": "lofty", "action": "mark_invitation_sent"},
    )
    assert response.status_code == 302
    assert journey(browser)["activationGuides"]["lofty"]["state"] == "unavailable"


# --------------------------------------------------------------------------- #
# Scenario 10: authorized reset of a completed agent
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_reset_reopens_required_setup_and_keeps_every_historical_fact(media_root):
    clear_branch_admins()
    selected = assignable_office()
    branch_admin = administrator("reset.admin@example.com", office_scope=selected)
    contact(branch_admin, contact_office=selected, primary=True)
    agent = microsoft_agent(id="entra-reset", mail="reset@onest.realestate")
    browser = Client()
    browser.force_login(agent)
    complete_profile(browser)
    deliver_pending(OFFICE_HANDOFF_EVENT)
    admin = Client()
    admin.force_login(company_admin())
    workspace_post(
        admin,
        "new_agent_onboarding_tools",
        agent,
        {"tool": "lofty", "action": "mark_invitation_sent"},
    )
    workspace_post(admin, "new_agent_onboarding_contract", agent, {})
    audit_before = AuditEvent.objects.count()

    staff = User.objects.create_user(email="staff@example.com", is_staff=True)
    reset_required_setup(actor=staff, user=agent)

    reopened = flow(browser)
    assert reopened["onboardingJourney"]["strictGateActive"] is True
    # The earliest incomplete required step, with every saved value kept.
    assert reopened["onboardingJourney"]["currentStep"]["code"] == "profile"
    assert reopened["initial"]["phoneNumber"]
    assert reopened["initial"]["headshotUrl"]
    # Historical facts survive; only the required-setup checkpoint is cleared.
    assert AgentContract.objects.filter(recipient=agent).count() == 1
    assert AgentToolStatus.objects.get(agent=agent, tool__slug="lofty").state == (
        ToolState.INVITATION_SENT
    )
    assert AuditEvent.objects.count() > audit_before
    case = UserOnboardingCase.objects.get(user=agent)
    assert case.required_setup_completed_at is None
    assert case.owner == branch_admin

    # Re-confirming creates a new handoff for the new cycle, not a duplicate
    # of the old one.
    assert save(browser, "credentials", _credentials_for(selected)).status_code == 302
    assert finalize(browser).status_code == 302
    handoffs = DomainEvent.objects.filter(name=OFFICE_HANDOFF_EVENT)
    assert sorted(event.payload["onboarding_version"] for event in handoffs) == [
        0,
        1,
    ]


def _credentials_for(selected):
    from apps.user.tests.test_onboarding_profile import credentials

    return credentials(office=str(selected.pk), confirmed_office_id=str(selected.pk))


# --------------------------------------------------------------------------- #
# Scenario 11: out-of-scope administrators and cross-user attacks
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_out_of_scope_admin_and_cross_user_requests_are_denied(media_root, settings):
    settings.CENTRIFUGO_API_URL = "http://centrifugo.internal"
    settings.CENTRIFUGO_API_KEY = "test-api-key"
    settings.CENTRIFUGO_HMAC_SECRET = "test-signing-secret-at-least-32-bytes-long"
    settings.CENTRIFUGO_WS_URL = "ws://centrifugo.test/connection/websocket"
    clear_branch_admins()
    agent = microsoft_agent(id="entra-target", mail="target@onest.realestate")
    browser = Client()
    browser.force_login(agent)
    complete_profile(browser)
    # A manager with the mutation grant, but for a sibling office.
    sibling_admin = branch_manager("fairfax-va", "sibling.manager@example.com")
    outsider = Client()
    outsider.force_login(sibling_admin)

    for route in ("new_agent_onboarding", "new_agent_onboarding_headshot"):
        assert outsider.get(reverse(route, args=[agent.pk])).status_code == 404
    denied = workspace_post(
        outsider,
        "new_agent_onboarding_tools",
        agent,
        {"tool": "lofty", "action": "mark_invitation_sent"},
    )
    assert denied.status_code == 404
    assert not AgentToolStatus.objects.filter(
        agent=agent, state=ToolState.INVITATION_SENT
    ).exists()

    # Another agent cannot open the workspace, act on it, or subscribe to the
    # first agent's live channel by naming it.
    peer = microsoft_agent(id="entra-peer", mail="peer@onest.realestate")
    peer_browser = Client()
    peer_browser.force_login(peer)
    assert peer_browser.get(
        reverse("new_agent_onboarding", args=[agent.pk])
    ).status_code in {302, 403, 404}
    assert workspace_post(
        peer_browser, "new_agent_onboarding_contract", agent, {}
    ).status_code in {302, 403, 404}
    assert not AgentContract.objects.filter(recipient=agent).exists()

    token = browser.get(reverse("onboarding_stream_token"), {"user_id": peer.pk}).json()
    peer_client = Client()
    peer_client.force_login(peer)
    peer_token = peer_client.get(
        reverse("onboarding_stream_token"), {"user_id": agent.pk}
    ).json()
    assert token["channel"] != peer_token["channel"]

    population = User.objects.filter(new_agent_filter(agent.date_joined)).distinct()
    rendered = repr(journey_health(population, now=agent.date_joined))
    for private in ("target@onest.realestate", "peer@onest.realestate", "Support"):
        assert private not in rendered


@pytest.mark.django_db
def test_failed_handoff_recovers_once_a_contact_exists_without_a_false_claim(
    media_root,
):
    clear_branch_admins()
    selected = assignable_office()
    agent = microsoft_agent(id="entra-recover", mail="recover@onest.realestate")
    browser = Client()
    browser.force_login(agent)
    complete_profile(browser)
    assert journey(browser)["officeHandoff"]["state"] == "notification_failed"

    desk = Client()
    desk.force_login(company_admin())

    def workspace() -> dict:
        response = desk.get(
            reverse("new_agent_onboarding", args=[agent.pk]), headers=INERTIA
        )
        return json.loads(response.content)["props"]["onboarding"]

    # Nobody to send to yet: the action explains what support must fix first.
    blocked = workspace()["recommendedAction"]
    assert blocked["code"] == "retry_office_handoff"
    assert blocked["enabled"] is False
    assert "Branch Admin contact" in blocked["unavailableReason"]
    refused = workspace_post(desk, "new_agent_onboarding_handoff", agent, {})
    assert refused.status_code == 422

    branch_admin = administrator("late.admin@example.com", office_scope=selected)
    contact(branch_admin, contact_office=selected, primary=True)
    assert workspace()["recommendedAction"]["enabled"] is True
    retried = workspace_post(desk, "new_agent_onboarding_handoff", agent, {})
    assert retried.status_code == 302, retried.content[:300]

    # Publishing is not delivery: the agent still sees the failure until the
    # notification actually exists.
    assert journey(browser)["officeHandoff"]["state"] == "notification_failed"
    deliver_pending(OFFICE_HANDOFF_EVENT)
    assert Notification.objects.get(event_key=OFFICE_HANDOFF_EVENT).recipient == (
        branch_admin
    )
    recovered = journey(browser)
    assert recovered["officeHandoff"]["state"] == "notified"
    assert "office_handoff_failed" not in {
        item["key"] for item in recovered["blockers"]
    }
    assert UserOnboardingCase.objects.get(user=agent).owner == branch_admin

    # A delivered handoff is history; it cannot be retried again.
    again = workspace_post(desk, "new_agent_onboarding_handoff", agent, {})
    assert again.status_code == 422
    assert (
        AuditEvent.objects.filter(
            action="user.onboarding.office_handoff_retried", target_id=str(agent.pk)
        ).count()
        == 1
    )

    outsider = Client()
    outsider.force_login(branch_manager("fairfax-va", "other.manager@example.com"))
    assert (
        workspace_post(outsider, "new_agent_onboarding_handoff", agent, {}).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# Query budgets: the agent's dashboard shell and the onboarding composer
# --------------------------------------------------------------------------- #


def _dashboard_queries(client: Client) -> int:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as captured:
        dashboard(client)
    return sum(
        1
        for query in captured.captured_queries
        if not query["sql"].lstrip().upper().startswith("EXPLAIN")
        and '"django_session"' not in query["sql"]
    )


@pytest.mark.django_db
def test_agent_dashboard_with_the_journey_has_a_fixed_query_budget():
    from apps.user.models import OnboardingTask
    from apps.user.tests.test_onboarding_administration import (
        account,
        confirm_required_setup,
    )
    from apps.user.tests.test_onboarding_journey import add_tool

    agent = account("budget.agent@example.com", "fairfax-va")
    case = confirm_required_setup(agent)
    staff = User.objects.create_superuser(email="budget.staff@example.com")
    browser = Client()
    browser.force_login(agent)

    def add_row(index: int) -> None:
        tool = add_tool(f"budget-{index}")
        AgentToolStatus.objects.create(
            agent=agent,
            tool=tool,
            state=ToolState.INVITATION_SENT,
            invitation_sent_at=case.required_setup_completed_at,
        )
        guide(slug=f"budget-guide-{index}", tool_code=tool.slug)
        OnboardingTask.objects.create(
            case=case, title=f"Budget task {index}", created_by=staff
        )

    # Measure from one of everything, so a query that only runs once a guide
    # or task exists is in the baseline and only per-row growth fails.
    add_row(0)
    dashboard(browser)  # warm per-process and session caches
    baseline = _dashboard_queries(browser)
    for index in range(1, 5):
        add_row(index)

    assert _dashboard_queries(browser) == baseline, baseline
