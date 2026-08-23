"""Quick Create: what each actor is offered, and what the offer does not buy.

The two halves this file keeps apart:

* the **registry** decides what is *serialized* — permission, feature, scope,
  all applied before the payload exists, so an unavailable action is absent
  rather than hidden; and
* the **endpoint** decides what actually happens. Withholding an action from
  the menu is never the control, so the crafted-navigation tests walk straight
  to destinations the menu refused and assert the server still says no.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission
from django.urls import NoReverseMatch, reverse

from apps.user.models import Office, User, UserRoleAssignment
from apps.user.services.role_assignments import get_effective_access
from apps.user.tests.test_profile import completed_user
from apps.web.quick_actions import (
    GROUP_ORDER,
    QUICK_ACTIONS,
    QUICK_ACTIONS_BY_KEY,
    SEARCH_THRESHOLD,
    actor_scopes,
    quick_actions_for,
    quick_create_payload,
    safe_return_path,
    unknown_feature_keys,
)


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        app_label, _, name = codename.partition(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=name)
        )
    return User.objects.get(pk=user.pk)


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def keys(user) -> list[str]:
    return [action["key"] for action in quick_actions_for(user)]


def agent(email="agent@example.com") -> User:
    return completed_user(email=email, office=office("fairfax-va"))


# --------------------------------------------------------------------------- #
# The registry itself
# --------------------------------------------------------------------------- #


def test_every_action_key_is_unique():
    assert len(QUICK_ACTIONS_BY_KEY) == len(QUICK_ACTIONS)


def test_every_destination_is_a_route_name_that_reverses(seeded):
    """A registry entry naming a route that no longer exists would serialize a
    dead link, so the catalog and ``urls.py`` are asserted to agree."""
    for action in QUICK_ACTIONS:
        try:
            reverse(action.route_name, args=action.route_args)
        except NoReverseMatch:  # pragma: no cover - the assertion is the report
            pytest.fail(f"{action.key} names an unreversible route")


def test_no_action_stores_a_url_or_a_callable():
    """The destination contract: a name and arguments, never a path."""
    for action in QUICK_ACTIONS:
        assert not action.route_name.startswith("/")
        assert "://" not in action.route_name
        assert isinstance(action.route_args, tuple)
        assert all(isinstance(arg, (str, int)) for arg in action.route_args)


def test_every_action_permission_is_in_the_reviewed_catalog():
    from apps.web.permission_catalog import CATALOG_CODENAMES

    unknown = {
        action.permission
        for action in QUICK_ACTIONS
        if action.permission not in CATALOG_CODENAMES
    }
    assert unknown == set()


def test_every_feature_dependency_is_a_real_feature_key():
    assert unknown_feature_keys() == frozenset()


def test_every_group_is_one_the_menu_knows_how_to_order():
    assert {action.group for action in QUICK_ACTIONS} <= set(GROUP_ORDER)


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_an_anonymous_visitor_is_offered_nothing(seeded):
    from django.contrib.auth.models import AnonymousUser

    assert quick_actions_for(AnonymousUser()) == []


def test_a_plain_agent_sees_no_administrative_actions(seeded):
    offered = keys(agent())

    assert all(QUICK_ACTIONS_BY_KEY[key].group != "Administration" for key in offered)


def test_an_action_is_absent_without_its_permission(seeded):
    """Absent from the payload, not hidden in the client: the set of actions a
    person can see describes what they are allowed to do."""
    user = agent("nobody@example.com")
    assert "new-announcement" not in keys(user)

    granted = grant(user, "web.manage_announcements")
    assign(granted, "regional_admin", "region", office("region-mid-atlantic"))

    assert "new-announcement" in keys(User.objects.get(pk=granted.pk))


def test_a_dark_feature_is_never_serialized_even_with_the_permission(seeded):
    """Training is catalogued and permitted but its module is not live."""
    from apps.web.navigation import HUB_FEATURES

    user = grant(agent("trainer@example.com"), "web.manage_training")
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))

    assert HUB_FEATURES["admin-training"] is False
    assert "new-training" not in keys(User.objects.get(pk=user.pk))


def test_an_out_of_scope_action_is_not_serialized(seeded):
    """A reservation action needs an office-shaped grant. A user with the
    permission but no office reach is offered nothing that depends on one."""
    user = grant(agent("scopeless@example.com"), "web.view_reservations")
    access = get_effective_access(User.objects.get(pk=user.pk))

    assert "office" not in actor_scopes(access)
    assert "reserve-room" not in keys(User.objects.get(pk=user.pk))


def test_company_wide_grant_fills_in_the_narrower_scope_shapes(seeded):
    user = agent("company@example.com")
    assign(user, "system_admin", "company")
    access = get_effective_access(User.objects.get(pk=user.pk))

    shapes = actor_scopes(access)

    assert {"company", "region", "office", "any"} <= shapes


def test_a_regional_grant_reaches_office_shaped_actions(seeded):
    user = agent("regional@example.com")
    assign(user, "regional_manager", "region", office("region-mid-atlantic"))
    access = get_effective_access(User.objects.get(pk=user.pk))

    assert {"region", "office"} <= actor_scopes(access)
    assert "company" not in actor_scopes(access)


# --------------------------------------------------------------------------- #
# Multi-role union
# --------------------------------------------------------------------------- #


def test_two_roles_granting_the_same_action_yield_one_entry(seeded):
    """The registry is consulted once, not once per role, so a union cannot
    duplicate. Asserted on the payload rather than on the implementation."""
    user = agent("multi@example.com")
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    assign(user, "branch_admin", "office", office("fairfax-va"))
    resolved = User.objects.get(pk=user.pk)

    offered = keys(resolved)

    assert len(offered) == len(set(offered))


def test_the_order_is_deterministic_across_renders(seeded):
    user = agent("stable@example.com")
    assign(user, "system_admin", "company")
    resolved = User.objects.get(pk=user.pk)

    assert keys(resolved) == keys(resolved)


def test_agent_actions_sort_before_administrative_ones(seeded):
    user = agent("ordered@example.com")
    assign(user, "system_admin", "company")
    offered = [
        QUICK_ACTIONS_BY_KEY[key].group for key in keys(User.objects.get(pk=user.pk))
    ]

    assert offered == sorted(offered, key=GROUP_ORDER.index)


# --------------------------------------------------------------------------- #
# Payload
# --------------------------------------------------------------------------- #


def test_the_payload_carries_scope_context_and_a_search_hint(seeded):
    user = agent("payload@example.com")
    assign(user, "system_admin", "company")
    payload = quick_create_payload(User.objects.get(pk=user.pk))

    assert payload["scope"]["level"] == "brokerage"
    assert payload["searchable"] is (len(payload["actions"]) >= SEARCH_THRESHOLD)
    assert all("href" in action for action in payload["actions"])


def test_every_serialized_href_is_a_site_relative_path(seeded):
    user = agent("paths@example.com")
    assign(user, "system_admin", "company")
    for action in quick_actions_for(User.objects.get(pk=user.pk)):
        assert action["href"].startswith("/")
        assert not action["href"].startswith("//")


def test_the_shared_prop_reaches_every_inertia_page(seeded, client):
    user = agent("shared@example.com")
    assign(user, "system_admin", "company")
    client.force_login(User.objects.get(pk=user.pk))

    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    props = json.loads(response.content.decode())["props"]

    assert "quickCreate" in props
    assert props["quickCreate"]["actions"]


def test_the_shared_prop_withholds_actions_from_a_plain_agent(seeded, client):
    client.force_login(agent("plain@example.com"))

    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    props = json.loads(response.content.decode())["props"]
    serialized = json.dumps(props["quickCreate"])

    assert "new-user" not in serialized
    assert "new-announcement" not in serialized


# --------------------------------------------------------------------------- #
# The menu is not the control
# --------------------------------------------------------------------------- #


def test_navigating_to_a_withheld_destination_is_still_refused(seeded, client):
    """The whole point of hiding never being enforcement."""
    user = agent("crafted@example.com")
    client.force_login(user)
    assert "new-user" not in keys(user)

    response = client.get(reverse("admin_add_user"))

    assert response.status_code == 403


def test_every_administrative_destination_refuses_an_unpermitted_agent(seeded, client):
    client.force_login(agent("sweep@example.com"))

    for action in QUICK_ACTIONS:
        if action.group != "Administration":
            continue
        response = client.get(reverse(action.route_name, args=action.route_args))
        assert response.status_code in {403, 404}, action.key


# --------------------------------------------------------------------------- #
# Return destinations
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "hostile",
    [
        "https://evil.test/steal",
        "//evil.test/steal",
        "javascript:alert(1)",
        "\\\\evil.test",
        "/ok\\path",
        "/ok\npath",
        "",
        None,
        "   ",
        "relative/path",
    ],
)
def test_an_unsafe_return_path_falls_back(hostile):
    assert safe_return_path(hostile, fallback="/dashboard") == "/dashboard"


@pytest.mark.parametrize(
    "accepted",
    ["/dashboard", "/operations/announcements?page=2", "/announcements/1"],
)
def test_a_same_origin_path_survives(accepted):
    assert safe_return_path(accepted, fallback="/dashboard") == accepted


# --------------------------------------------------------------------------- #
# Actions that open a drawer rather than a page
# --------------------------------------------------------------------------- #


def test_the_create_actions_point_at_a_list_page_drawer(seeded):
    """Announcements and Quick Access open in place, not on a standalone form."""
    for key in ("new-announcement", "new-quick-access"):
        action = QUICK_ACTIONS_BY_KEY[key]
        assert action.query == (("create", "1"),)


def test_a_drawer_action_serializes_the_query_string(seeded):
    user = agent("drawer@example.com")
    assign(user, "system_admin", "company")
    offered = {
        action["key"]: action["href"]
        for action in quick_actions_for(User.objects.get(pk=user.pk))
    }

    assert offered["new-announcement"].endswith("?create=1")
    assert offered["new-quick-access"].endswith("?create=1")


def test_the_announcement_queue_opens_its_drawer_on_the_query_flag(seeded, client):
    user = agent("open-ann@example.com")
    assign(user, "system_admin", "company")
    client.force_login(User.objects.get(pk=user.pk))

    closed = client.get(reverse("admin_announcements"), HTTP_X_INERTIA="true")
    opened = client.get(
        f"{reverse('admin_announcements')}?create=1", HTTP_X_INERTIA="true"
    )

    assert json.loads(closed.content.decode())["props"]["createSheet"] is None
    assert json.loads(opened.content.decode())["props"]["createSheet"]["open"] is True


def test_the_quick_access_queue_opens_its_drawer_on_the_query_flag(seeded, client):
    user = agent("open-qa@example.com")
    assign(user, "system_admin", "company")
    client.force_login(User.objects.get(pk=user.pk))

    closed = client.get(reverse("admin_quick_access"), HTTP_X_INERTIA="true")
    opened = client.get(
        f"{reverse('admin_quick_access')}?create=1", HTTP_X_INERTIA="true"
    )

    assert json.loads(closed.content.decode())["props"]["createSheet"] is None
    assert json.loads(opened.content.decode())["props"]["createSheet"]["open"] is True


def test_opening_a_drawer_is_still_refused_without_the_permission(seeded, client):
    """The query flag opens a drawer; it does not open a door."""
    client.force_login(agent("nope@example.com"))

    assert client.get(f"{reverse('admin_announcements')}?create=1").status_code == 403
    assert client.get(f"{reverse('admin_quick_access')}?create=1").status_code == 403


def test_a_rejected_drawer_create_reopens_on_the_quick_access_queue(seeded, client):
    user = agent("qa-reject@example.com")
    assign(user, "system_admin", "company")
    client.force_login(User.objects.get(pk=user.pk))

    response = client.post(
        reverse("quick_access_create"),
        {"context": "sheet", "name": "Missing everything else"},
        HTTP_X_INERTIA="true",
    )

    payload = json.loads(response.content.decode())
    assert response.status_code == 422
    assert payload["component"] == "QuickAccessAdministration"
    assert payload["props"]["createSheet"]["open"] is True
    assert payload["props"]["errors"]["fields"]
