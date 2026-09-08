"""Disabling and reactivating an account.

The claims this file has to keep honest: the act is confirmed, audited,
idempotent, and *enforced* — a disabled user's live session stops working on
their next request rather than whenever their cookie expires. Everything else
here is the authority matrix around it.
"""

from __future__ import annotations

import json
from importlib import import_module

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, override_settings
from django.urls import reverse

from apps.audit.models import AuditEvent, DomainEvent
from apps.user.models import User
from apps.user.services.account_state import (
    DISABLED_ACTION,
    DOMAIN_EVENT,
    REACTIVATED_ACTION,
    can_manage_account_state,
    revoke_user_sessions,
    set_account_state,
)
from apps.user.services.agent_administration import (
    StaleAdministrationVersion,
    administration_version,
)
from apps.user.tests.test_agent_administration import (
    CONNECTICUT,
    FAIRFAX,
    agent_in,
    branch_manager,
    company_admin,
    office,
)
from apps.user.tests.test_profile import completed_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def post_state(client, target: User, action: str, **overrides):
    data = {
        "action": action,
        "business_reason": "Left the brokerage on Friday.",
        "expected_version": administration_version(target),
    }
    data.update(overrides)
    return client.post(reverse("user_account_state", args=[target.pk]), data)


def signed_in_session_count(user: User) -> int:
    return sum(
        1
        for session in Session.objects.all()
        if session.get_decoded().get("_auth_user_id") == str(user.pk)
    )


def account_manager(email: str = "boss@example.com") -> User:
    """A brokerage admin: holds the account-state grant through their role."""
    return company_admin(email)


def record_admin_without_account_grant(email: str = "records@example.com") -> User:
    """Somebody who may edit the record but was never given the lockout grant."""
    user = completed_user(email=email, office=office(FAIRFAX))
    for codename in ("view_user_administration", "change_user_administration"):
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="user", codename=codename)
        )
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="web", codename="view_users")
    )
    return user


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_change_permission_alone_does_not_disable_anybody(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    actor = record_admin_without_account_grant()
    assert can_manage_account_state(actor, target) is False
    client.force_login(actor)
    assert post_state(client, target, "disable").status_code == 403
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_a_brokerage_admin_may_disable_somebody_in_scope(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(account_manager())
    assert post_state(client, target, "disable").status_code == 302
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_nobody_disables_their_own_account(client):
    actor = account_manager()
    assert can_manage_account_state(actor, actor) is False
    client.force_login(actor)
    assert post_state(client, actor, "disable").status_code == 403
    actor.refresh_from_db()
    assert actor.is_active is True


@pytest.mark.django_db
def test_an_out_of_scope_user_is_a_404_not_a_403(client):
    """A 403 would confirm the id exists. A 404 says nothing either way."""
    target = agent_in(CONNECTICUT, email="elsewhere@example.com")
    manager = branch_manager(FAIRFAX)
    manager.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="user", codename="manage_account_state"
        )
    )
    client.force_login(manager)
    assert post_state(client, target, "disable").status_code == 404
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_the_service_refuses_a_crafted_call_the_view_never_made():
    target = agent_in(CONNECTICUT, email="elsewhere@example.com")
    actor = branch_manager(FAIRFAX)
    with pytest.raises(PermissionDenied):
        set_account_state(
            actor=actor,
            target=target,
            enabled=False,
            business_reason="crafted",
            expected_version=administration_version(target),
        )


# ---------------------------------------------------------------------------
# The act itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_disabling_is_idempotent():
    target = agent_in(FAIRFAX, email="target@example.com")
    actor = account_manager()
    first = set_account_state(
        actor=actor,
        target=target,
        enabled=False,
        business_reason="Departed.",
        expected_version=administration_version(target),
    )
    assert first.changed is True

    second = set_account_state(
        actor=actor,
        target=first.user,
        enabled=False,
        business_reason="Departed.",
        expected_version=administration_version(first.user),
    )
    assert second.changed is False
    assert second.is_active is False
    # One decision, one lifecycle event.
    assert AuditEvent.objects.filter(action=DISABLED_ACTION).count() == 1


@pytest.mark.django_db
def test_reactivating_restores_access_and_is_audited_separately():
    target = agent_in(FAIRFAX, email="target@example.com")
    actor = account_manager()
    disabled = set_account_state(
        actor=actor,
        target=target,
        enabled=False,
        business_reason="Suspended pending review.",
        expected_version=administration_version(target),
    )
    restored = set_account_state(
        actor=actor,
        target=disabled.user,
        enabled=True,
        business_reason="Review cleared.",
        expected_version=administration_version(disabled.user),
    )
    assert restored.changed is True
    assert restored.user.is_active is True
    assert AuditEvent.objects.filter(action=REACTIVATED_ACTION).count() == 1


@pytest.mark.django_db
def test_a_reason_is_required():
    target = agent_in(FAIRFAX, email="target@example.com")
    with pytest.raises(ValidationError):
        set_account_state(
            actor=account_manager(),
            target=target,
            enabled=False,
            business_reason="   ",
            expected_version=administration_version(target),
        )
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_the_form_rejects_a_blank_reason(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(account_manager())
    response = post_state(client, target, "disable", business_reason="")
    assert response.status_code == 422
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_an_unsupported_action_is_refused(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(account_manager())
    response = post_state(client, target, "delete")
    assert response.status_code == 422
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_a_concurrent_edit_is_refused_rather_than_overwritten(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(account_manager())
    response = post_state(client, target, "disable", expected_version="stale")
    assert response.status_code == 409
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_the_service_raises_on_a_stale_version():
    target = agent_in(FAIRFAX, email="target@example.com")
    with pytest.raises(StaleAdministrationVersion):
        set_account_state(
            actor=account_manager(),
            target=target,
            enabled=False,
            business_reason="Departed.",
            expected_version="1999-01-01T00:00:00",
        )


# ---------------------------------------------------------------------------
# Enforcement: sessions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_disabling_ends_every_live_session_for_that_user():
    target = agent_in(FAIRFAX, email="target@example.com")
    bystander = agent_in(CONNECTICUT, email="bystander@example.com")
    for client in (Client(), Client()):
        client.force_login(target)
    Client().force_login(bystander)
    assert signed_in_session_count(target) == 2

    result = set_account_state(
        actor=account_manager(),
        target=target,
        enabled=False,
        business_reason="Departed.",
        expected_version=administration_version(target),
    )
    assert result.sessions_revoked == 2
    assert signed_in_session_count(target) == 0
    # Somebody else's session is not collateral damage.
    assert signed_in_session_count(bystander) == 1


@pytest.mark.django_db
def test_a_disabled_user_is_signed_out_on_their_next_request():
    target = agent_in(FAIRFAX, email="target@example.com")
    session = Client()
    session.force_login(target)
    assert session.get(reverse("dashboard")).status_code == 200

    set_account_state(
        actor=account_manager(),
        target=target,
        enabled=False,
        business_reason="Departed.",
        expected_version=administration_version(target),
    )
    response = session.get(reverse("dashboard"))
    assert response.status_code == 302
    assert reverse("login") in response["Location"]


@pytest.mark.django_db
def test_reactivating_does_not_resurrect_the_old_sessions():
    target = agent_in(FAIRFAX, email="target@example.com")
    Client().force_login(target)
    actor = account_manager()
    disabled = set_account_state(
        actor=actor,
        target=target,
        enabled=False,
        business_reason="Suspended.",
        expected_version=administration_version(target),
    )
    set_account_state(
        actor=actor,
        target=disabled.user,
        enabled=True,
        business_reason="Cleared.",
        expected_version=administration_version(disabled.user),
    )
    assert signed_in_session_count(target) == 0


@pytest.mark.django_db
@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.cached_db")
def test_sessions_are_cut_from_the_cache_as_well_as_the_database():
    """``cached_db`` serves reads from Redis, so the row alone is not enough."""
    target = agent_in(FAIRFAX, email="target@example.com")
    session = Client()
    session.force_login(target)
    key = session.cookies["sessionid"].value
    store = import_module(settings.SESSION_ENGINE).SessionStore
    assert store(key).get("_auth_user_id") == str(target.pk)

    set_account_state(
        actor=account_manager(),
        target=target,
        enabled=False,
        business_reason="Departed.",
        expected_version=administration_version(target),
    )
    assert store(key).get("_auth_user_id") is None
    assert signed_in_session_count(target) == 0


@pytest.mark.django_db
def test_revoking_sessions_for_somebody_with_none_is_a_no_op():
    target = agent_in(FAIRFAX, email="target@example.com")
    assert revoke_user_sessions(target) == 0


# ---------------------------------------------------------------------------
# Trail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_disable_event_records_who_why_and_how_many_sessions():
    target = agent_in(FAIRFAX, email="target@example.com")
    Client().force_login(target)
    actor = account_manager()
    set_account_state(
        actor=actor,
        target=target,
        enabled=False,
        business_reason="Left the brokerage.",
        expected_version=administration_version(target),
    )
    event = AuditEvent.objects.get(action=DISABLED_ACTION)
    assert event.actor_id == str(actor.pk)
    assert event.target_id == str(target.pk)
    assert event.reason == "Left the brokerage."
    assert event.before == {"is_active": True}
    assert event.after == {"is_active": False}
    assert event.metadata["sessions_revoked"] == 1
    assert event.office_id == office(FAIRFAX).stable_key


@pytest.mark.django_db
def test_a_denied_attempt_is_audited():
    target = agent_in(CONNECTICUT, email="elsewhere@example.com")
    actor = branch_manager(FAIRFAX)
    with pytest.raises(PermissionDenied):
        set_account_state(
            actor=actor,
            target=target,
            enabled=False,
            business_reason="crafted",
            expected_version=administration_version(target),
        )
    denial = AuditEvent.objects.get(action="security.account_state.denied")
    assert denial.outcome == AuditEvent.Outcome.DENIED
    assert denial.reason == "out_of_scope_or_unauthorized"


@pytest.mark.django_db
def test_the_change_publishes_a_domain_event():
    target = agent_in(FAIRFAX, email="target@example.com")
    set_account_state(
        actor=account_manager(),
        target=target,
        enabled=False,
        business_reason="Departed.",
        expected_version=administration_version(target),
    )
    event = DomainEvent.objects.get(name=DOMAIN_EVENT)
    assert event.payload["user_id"] == target.pk
    assert event.payload["is_active"] is False
    assert event.subject == f"user:{target.pk}"


@pytest.mark.django_db
def test_the_change_shows_up_in_the_records_recent_activity(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(account_manager())
    assert post_state(client, target, "disable").status_code == 302

    response = client.get(
        reverse("user_administration", args=[target.pk]), HTTP_X_INERTIA="true"
    )
    payload = json.loads(response.content)["props"]["administration"]
    assert payload["accountState"]["isActive"] is False
    assert payload["accountState"]["label"] == "Disabled"
    assert any(entry["action"] == DISABLED_ACTION for entry in payload["history"])


@pytest.mark.django_db
def test_the_panel_explains_why_it_is_read_only_for_your_own_record(client):
    actor = account_manager()
    client.force_login(actor)
    response = client.get(
        reverse("user_administration", args=[actor.pk]), HTTP_X_INERTIA="true"
    )
    state = json.loads(response.content)["props"]["administration"]["accountState"]
    assert state["canManage"] is False
    assert "own account access" in state["reason"]
