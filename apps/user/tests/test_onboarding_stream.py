"""Centrifugo hints are private, committed, and never source-of-truth data."""

from __future__ import annotations

import json
import re
from unittest.mock import Mock

import httpx
import jwt
import pytest
from django.db import transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.events import publish
from apps.audit.models import DomainEvent
from apps.audit.tasks import dispatch_event
from apps.onboarding_tools.models import ToolState
from apps.user.models import OnboardingStreamState, User
from apps.user.services.onboarding_operations import reset_required_setup
from apps.user.services.onboarding_stream import (
    consume,
    private_channel,
    state_version,
)
from apps.user.tests.test_onboarding_administration import (
    account,
    action_version,
    company_admin,
    confirm_required_setup,
    event_envelope,
)
from apps.user.tests.test_onboarding_next_steps import guide


@pytest.fixture
def live_settings(settings):
    settings.CENTRIFUGO_API_URL = "http://centrifugo.internal"
    settings.CENTRIFUGO_API_KEY = "test-api-key"
    settings.CENTRIFUGO_HMAC_SECRET = "test-signing-secret-at-least-32-bytes-long"
    settings.CENTRIFUGO_WS_URL = "ws://centrifugo.test/connection/websocket"


def _response():
    response = Mock()
    response.json.return_value = {"result": {}}
    return response


@pytest.mark.django_db(transaction=True)
def test_commit_dispatches_safe_private_event_and_rollback_does_not(
    live_settings, monkeypatch
):
    user = User.objects.create_user(email="stream@example.com")
    queued: list[str] = []
    monkeypatch.setattr(
        "apps.audit.tasks.dispatch_event.delay",
        lambda event_id: queued.append(event_id),
    )
    posts: list[dict] = []

    def post(*_args, **kwargs):
        posts.append(kwargs)
        return _response()

    monkeypatch.setattr("apps.user.services.onboarding_stream.httpx.post", post)
    with pytest.raises(ValueError, match="rollback"), transaction.atomic():
        publish(
            "user.onboarding.profile_changed",
            subject=f"user:{user.pk}",
            payload={"user_id": user.pk},
        )
        raise ValueError("rollback")
    assert queued == []
    assert posts == []
    assert state_version(user.pk) == 0
    assert not DomainEvent.objects.filter(
        name="user.onboarding.profile_changed"
    ).exists()

    with transaction.atomic():
        event = publish(
            "user.onboarding.profile_changed",
            subject=f"user:{user.pk}",
            payload={"user_id": user.pk},
        )
        assert queued == []
        assert posts == []
    assert queued == [str(event.id)]
    dispatch_event(str(event.id))
    assert state_version(user.pk) == 1
    assert len(posts) == 1
    assert posts[0]["json"] == {
        "channel": private_channel(user.pk),
        "data": {
            "id": str(event.id),
            "eventType": "onboarding.state_changed",
            "sourceKey": "profile",
            "stateVersion": 1,
        },
    }
    assert "stream@example.com" not in repr(posts)
    dispatch_event(str(event.id))
    assert state_version(user.pk) == 1
    assert len(posts) == 1


@pytest.mark.django_db
def test_token_is_self_only_short_lived_and_rejects_inactive_user(
    live_settings, client, settings
):
    agent = account("agent@example.com", "fairfax-va")
    other = account("other@example.com", "fairfax-va")
    client.force_login(agent)
    response = client.get(
        reverse("onboarding_stream_token"),
        {"user_id": other.pk, "channel": private_channel(other.pk)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["channel"] == private_channel(agent.pk)
    assert re.fullmatch(r"\$onboarding:[0-9a-f]{40}", body["channel"])
    assert body["channel"] != private_channel(other.pk)
    assert response["Cache-Control"] == "no-store"
    connection = jwt.decode(
        body["connectionToken"], settings.CENTRIFUGO_HMAC_SECRET, algorithms=["HS256"]
    )
    subscription = jwt.decode(
        body["subscriptionToken"], settings.CENTRIFUGO_HMAC_SECRET, algorithms=["HS256"]
    )
    assert connection["sub"] == subscription["sub"]
    assert subscription["channel"] == private_channel(agent.pk)
    assert 0 < connection["exp"] - int(timezone.now().timestamp()) <= 60
    assert client.get(reverse("onboarding_stream_token")).status_code == 200

    agent.is_active = False
    agent.save(update_fields=["is_active"])
    assert client.get(reverse("onboarding_stream_token")).status_code in {401, 403}


@pytest.mark.django_db
def test_token_denies_anonymous_and_non_agent(live_settings, client):
    assert client.get(reverse("onboarding_stream_token")).status_code in {401, 403}
    user = User.objects.create_user(email="nonagent@example.com")
    client.force_login(user)
    assert client.get(reverse("onboarding_stream_token")).status_code == 403


@pytest.mark.django_db
def test_token_rate_limit_and_unconfigured_fallback(live_settings, client, settings):
    agent = account("agent@example.com", "fairfax-va")
    client.force_login(agent)
    route = reverse("onboarding_stream_token")
    for _ in range(24):
        assert client.get(route).status_code == 200
    limited = client.get(route)
    assert limited.status_code == 429
    assert limited["Retry-After"] == "60"
    settings.CENTRIFUGO_API_URL = ""
    assert client.get(route).status_code == 503


@pytest.mark.django_db
def test_reset_emits_the_same_profile_invalidation():
    target = account("target@example.com", "fairfax-va")
    actor = User.objects.create_user(email="staff@example.com", is_staff=True)
    reset_required_setup(actor=actor, user=target)
    assert DomainEvent.objects.filter(
        name="user.onboarding.profile_changed", subject=f"user:{target.pk}"
    ).exists()


@pytest.mark.django_db
def test_provider_outage_does_not_change_database_truth(live_settings, monkeypatch):
    user = User.objects.create_user(email="outage@example.com")
    event = DomainEvent.objects.create(
        name="user.onboarding.profile_changed",
        payload={"user_id": user.pk},
    )
    monkeypatch.setattr(
        "apps.user.services.onboarding_stream.httpx.post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("down")),
    )
    with pytest.raises(RuntimeError, match="onboarding live publish failed"):
        consume(event_envelope(event))
    assert OnboardingStreamState.objects.get(user=user).version == 1


@pytest.mark.django_db
def test_two_sessions_admin_invitation_unlocks_agent_partial_journey(
    live_settings, monkeypatch
):
    agent = account("agent@example.com", "fairfax-va")
    confirm_required_setup(agent)
    admin = company_admin()
    guide(slug="skyslope-live-activation", tool_code="skyslope")
    agent_client = Client()
    admin_client = Client()
    agent_client.force_login(agent)
    admin_client.force_login(admin)
    headers = {"X-Inertia": "true"}
    before = json.loads(
        agent_client.get(reverse("dashboard"), headers=headers).content
    )["props"]["onboardingJourney"]
    assert before["activationGuides"]["skyslope"]["state"] == "locked"

    response = admin_client.post(
        reverse("new_agent_onboarding_tools", args=[agent.pk]),
        {
            "tool": "skyslope",
            "action": "mark_invitation_sent",
            "expected_version": action_version(agent),
        },
    )
    assert response.status_code == 302
    event = DomainEvent.objects.filter(name="onboarding_tool.state_changed").latest(
        "occurred_at"
    )
    sent: list[dict] = []

    def post(*_args, **kwargs):
        sent.append(kwargs["json"])
        return _response()

    monkeypatch.setattr("apps.user.services.onboarding_stream.httpx.post", post)
    consume(event_envelope(event))
    assert sent[0]["data"]["sourceKey"] == "tool"
    assert sent[0]["data"]["stateVersion"] > before["stateVersion"]
    assert "skyslope" not in repr(sent)

    partial = {
        **headers,
        "X-Inertia-Partial-Component": "Dashboard",
        "X-Inertia-Partial-Data": "onboardingJourney",
    }
    after = json.loads(agent_client.get(reverse("dashboard"), headers=partial).content)[
        "props"
    ]
    assert set(after) == {"onboardingJourney"}
    journey = after["onboardingJourney"]
    assert journey["activationGuides"]["skyslope"]["state"] == "available"
    assert journey["stateVersion"] == sent[0]["data"]["stateVersion"]
    assert (
        next(tool for tool in journey["tools"] if tool["key"] == "skyslope")["state"]
        == ToolState.INVITATION_SENT
    )
