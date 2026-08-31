"""Nav feature state and primary-office context shared with the sidebar."""

import json

import pytest
from django.contrib.auth.models import Permission
from django.urls import NoReverseMatch, reverse

from apps.user.models import Office, User
from apps.user.roles import AGENT, BRANCH_MANAGER, ScopeType
from apps.user.services.role_assignments import create_role_assignment
from apps.web.dashboard import HUB_SECTIONS
from apps.web.navigation import (
    HUB_FEATURES,
    hub_feature_states,
    primary_office_payload,
)
from apps.web.operations import OPERATIONS_FEATURES


def shared_props(client):
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    return json.loads(response.content)["props"]


def agent(**kwargs):
    return User.objects.create_user(
        email=kwargs.pop("email", "agent@example.com"),
        profile_completed=True,
        **kwargs,
    )


def branch_office():
    office = Office.assignable_queryset().filter(kind=Office.Kind.BRANCH).first()
    assert office is not None, "office seed must provide at least one branch"
    return office


# ---------------------------------------------------------------------------
# Feature registry
# ---------------------------------------------------------------------------


def test_every_hub_section_declares_its_availability():
    assert set(HUB_FEATURES) == (
        set(HUB_SECTIONS) | set(OPERATIONS_FEATURES) | {"reports"}
    )


def test_only_the_live_destinations_are_enabled():
    # Flip the section's entry in the commit that gives it a real route; this
    # assertion is the reminder to update the nav registry at the same time.
    live_features = {
        key
        for key, enabled in {
            **OPERATIONS_FEATURES,
            "announcements": True,
            "office-info": True,
            "office-resources": True,
            "office-inventory": True,
            "my-contract": True,
            "reports": True,
            "admin-operational-tasks": True,
            "admin-feedback": True,
        }.items()
        if enabled
    }
    coming_soon = {
        key: value for key, value in HUB_FEATURES.items() if key not in live_features
    }
    assert set(coming_soon.values()) == {False}
    assert HUB_FEATURES["admin-new-agents"] is True
    assert HUB_FEATURES["admin-users"] is True
    assert HUB_FEATURES["admin-offices"] is True
    assert HUB_FEATURES["announcements"] is True
    assert HUB_FEATURES["office-info"] is True
    assert HUB_FEATURES["office-resources"] is True
    assert HUB_FEATURES["office-inventory"] is True
    assert HUB_FEATURES["my-contract"] is True
    assert HUB_FEATURES["reports"] is True


def test_feature_states_are_a_copy_callers_cannot_corrupt():
    states = hub_feature_states()
    states["agent-transactions"] = True
    assert HUB_FEATURES["agent-transactions"] is False


@pytest.mark.django_db
def test_unauthorized_administrative_feature_keys_are_not_shared(client):
    account = agent()
    client.force_login(account)

    props = shared_props(client)

    assert props["features"] == {
        **dict.fromkeys(HUB_SECTIONS, False),
        "announcements": True,
        "office-info": True,
        "office-resources": True,
        "office-inventory": True,
        "my-contract": True,
    }
    assert not any(key.startswith("admin-") for key in props["features"])


def test_every_unbuilt_section_has_a_reachable_placeholder_route():
    for section in HUB_SECTIONS:
        try:
            reverse("coming_soon", args=[section])
        except NoReverseMatch:  # pragma: no cover - guards a registry typo
            pytest.fail(f"{section} has no coming_soon route")


# ---------------------------------------------------------------------------
# Primary office context
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_primary_office_comes_from_the_users_own_record():
    office = branch_office()
    user = agent(office=office)
    assert primary_office_payload(user) == {
        "id": office.id,
        "name": office.name,
        "regionName": office.region_name(),
    }


@pytest.mark.django_db
def test_primary_office_is_null_when_the_user_has_none():
    assert primary_office_payload(agent()) is None


@pytest.mark.django_db
def test_primary_office_is_null_for_anonymous_visitors():
    from django.contrib.auth.models import AnonymousUser

    assert primary_office_payload(AnonymousUser()) is None


@pytest.mark.django_db
def test_office_context_ignores_any_office_identifier_in_the_request(client):
    """The client cannot ask for someone else's office by adding a parameter."""
    mine = branch_office()
    theirs = (
        Office.assignable_queryset()
        .filter(kind=Office.Kind.BRANCH)
        .exclude(pk=mine.pk)
        .first()
    )
    assert theirs is not None
    client.force_login(agent(office=mine))

    response = client.get(
        reverse("dashboard"),
        {"office": theirs.pk, "office_id": theirs.pk, "user": 999},
        HTTP_X_INERTIA="true",
    )
    props = json.loads(response.content)["props"]
    assert props["primaryOffice"]["id"] == mine.pk


@pytest.mark.django_db
def test_office_transfer_is_reflected_on_the_next_request(client):
    user = agent(office=branch_office())
    client.force_login(user)
    assert shared_props(client)["primaryOffice"]["id"] == user.office_id

    moved_to = (
        Office.assignable_queryset()
        .filter(kind=Office.Kind.BRANCH)
        .exclude(pk=user.office_id)
        .first()
    )
    user.office = moved_to
    user.save(update_fields=["office"])
    assert shared_props(client)["primaryOffice"]["id"] == moved_to.pk


# ---------------------------------------------------------------------------
# Shared props
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_shared_props_carry_feature_state_and_office(client):
    office = branch_office()
    client.force_login(agent(office=office))
    props = shared_props(client)
    assert props["features"] == {
        **dict.fromkeys(HUB_SECTIONS, False),
        "announcements": True,
        "office-info": True,
        "office-resources": True,
        "office-inventory": True,
        "my-contract": True,
    }
    assert props["primaryOffice"] == {
        "id": office.id,
        "name": office.name,
        "regionName": office.region_name(),
    }


@pytest.mark.django_db
def test_an_agent_without_an_office_still_gets_a_usable_page(client):
    client.force_login(agent())
    props = shared_props(client)
    assert props["primaryOffice"] is None
    assert props["features"]


@pytest.mark.django_db
def test_a_manager_who_is_also_an_agent_gets_one_set_of_context(client):
    office = branch_office()
    user = agent(office=office)
    admin = User.objects.create_superuser(email="admin@example.com")
    for role in (BRANCH_MANAGER, AGENT):
        create_role_assignment(
            actor=admin,
            target_user=user,
            role=role,
            scope_type=ScopeType.OFFICE,
            scope_office=office,
        )
    client.force_login(user)
    props = shared_props(client)
    assert props["user"]["roles"] == [BRANCH_MANAGER, AGENT]
    assert props["primaryOffice"]["id"] == office.pk
    assert props["features"] == hub_feature_states(user)


@pytest.mark.django_db
def test_unauthenticated_visitors_get_no_office_context(client):
    response = client.get(reverse("login"), HTTP_X_INERTIA="true")
    props = json.loads(response.content)["props"]
    assert props["user"] is None
    assert props["primaryOffice"] is None


# ---------------------------------------------------------------------------
# Server-side enforcement — menu visibility never stands in for authorization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_hub_destinations_reject_anonymous_direct_access(client):
    for section in HUB_SECTIONS:
        response = client.get(reverse("coming_soon", args=[section]))
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_shared_user_carries_headshot_url(client, settings, tmp_path):
    from apps.user.tests.test_onboarding import make_image

    settings.MEDIA_ROOT = str(tmp_path)
    user = agent()
    client.force_login(user)
    assert shared_props(client)["user"]["headshotUrl"] is None

    client.post(
        reverse("headshot_upload"),
        {"headshot": make_image("JPEG", (300, 300))},
        format="multipart",
    )
    user.refresh_from_db()
    assert shared_props(client)["user"]["headshotUrl"] == (
        "http://testserver/account/headshot/file"
    )


@pytest.mark.django_db
def test_effective_permissions_are_recomputed_each_request(client):
    """Access revoked mid-session must not survive in the shared props."""
    user = agent(office=branch_office())
    permission = Permission.objects.get(codename="view_user")
    user.user_permissions.add(permission)
    client.force_login(user)
    assert shared_props(client)["user"]["permissions"] == ["user.view_user"]

    user.user_permissions.remove(permission)
    assert shared_props(client)["user"]["permissions"] == []


@pytest.mark.django_db
def test_an_unknown_hub_section_is_a_404_not_a_placeholder(client):
    client.force_login(agent())
    response = client.get(reverse("coming_soon", args=["not-a-real-section"]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_live_administrative_features_reach_only_their_permission_holders(client):
    """A live destination is shared as available; an agent never learns of it."""
    account = agent()
    client.force_login(account)
    assert "admin-users" not in shared_props(client)["features"]

    manager = User.objects.create_user(
        email="branch@example.com", office=branch_office(), profile_completed=True
    )
    create_role_assignment(
        actor=User.objects.create_superuser(email="root@example.com", password="x"),
        target_user=manager,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=branch_office(),
    )
    client.force_login(manager)
    assert shared_props(client)["features"]["admin-users"] is True
