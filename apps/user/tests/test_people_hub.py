"""The People tabs: one entry point, richer Users rows, and lockouts from a row.

Covers what the tabbed page added on top of the existing directory and
account-state contracts, which keep their own suites:

* ``/operations/people`` lands on the first tab the reader may open;
* a Users row carries its live roles and — only for a reader who may change
  it — the account action and its freshness token;
* a disable or reactivate started from a row comes back to the list, with its
  filters, on success and on refusal.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.user.models import User
from apps.user.roles import ScopeType
from apps.user.services.agent_administration import administration_version
from apps.user.tests.test_agent_administration import (
    FAIRFAX,
    agent_in,
    assign,
    company_admin,
    office,
)
from apps.user.tests.test_profile import completed_user
from apps.user.tests.test_user_directory import reader
from apps.web.tests.test_permissions import inertia_page_script


def holder_of(email: str, *codenames: str) -> User:
    user = completed_user(email=email, office=office(FAIRFAX))
    for codename in codenames:
        app_label, name = codename.split(".", 1)
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=name)
        )
    return user


def users_props(client, **params) -> dict:
    response = client.get(reverse("admin_users"), params, HTTP_X_INERTIA="true")
    assert response.status_code == 200
    return json.loads(response.content)["props"]


def row_for(props: dict, email: str) -> dict:
    return next(row for row in props["users"]["items"] if row["email"] == email)


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("grants", "landing"),
    [
        (("web.view_users", "web.view_new_agents"), "admin_users"),
        (("web.assign_user_roles", "web.view_new_agents"), "admin_assign_roles"),
        (("web.view_new_agents",), "admin_new_agents"),
    ],
)
def test_people_lands_on_the_first_tab_the_reader_may_open(client, grants, landing):
    client.force_login(holder_of("reader@example.com", *grants))

    response = client.get(reverse("admin_people"))

    assert response.status_code == 302
    assert response["Location"] == reverse(landing)


@pytest.mark.django_db
def test_people_refuses_a_reader_with_none_of_the_grants(client):
    client.force_login(holder_of("nobody@example.com"))
    response = client.get(reverse("admin_people"))
    assert response.status_code in {302, 403}
    assert response.get("Location", "") not in {
        reverse("admin_users"),
        reverse("admin_assign_roles"),
        reverse("admin_new_agents"),
    }


# ---------------------------------------------------------------------------
# Users rows
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_row_carries_its_live_roles_in_catalog_order(client):
    person = agent_in(FAIRFAX, email="multi@example.com")
    assign(person, "branch_manager", ScopeType.OFFICE, office(FAIRFAX))
    client.force_login(company_admin())

    row = row_for(users_props(client), "multi@example.com")

    assert "Branch Manager" in row["roles"]
    assert len(row["roles"]) == len(set(row["roles"]))


@pytest.mark.django_db
def test_rows_offer_the_account_action_only_with_the_grant(client):
    agent_in(FAIRFAX, email="target@example.com")
    client.force_login(reader("viewer@example.com", "web.view_users"))

    row = row_for(users_props(client), "target@example.com")

    assert "account" not in row


@pytest.mark.django_db
def test_an_account_manager_gets_the_action_but_never_on_their_own_row(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    admin = company_admin()
    client.force_login(admin)

    props = users_props(client, pageSize=100)

    assert row_for(props, "target@example.com")["account"] == {
        "version": administration_version(target)
    }
    assert "account" not in row_for(props, admin.email)


@pytest.mark.django_db
def test_page_size_is_one_of_the_offered_sizes(client):
    client.force_login(company_admin())

    assert users_props(client, pageSize=10)["users"]["pagination"]["pageSize"] == 10
    # Anything else falls back rather than being honoured.
    assert users_props(client, pageSize=7)["users"]["pagination"]["pageSize"] == 25
    assert users_props(client)["pageSizeOptions"] == [10, 25, 50, 100]


@pytest.mark.django_db
def test_roles_and_office_paths_do_not_cost_a_query_per_row(client):
    """Read as somebody without the contract grant: the contract column is a
    separate domain call per row and is not what this pins."""
    client.force_login(
        reader(
            "counter@example.com",
            "web.view_users",
            "user.view_user_administration",
            "user.manage_account_state",
        )
    )
    for index in range(3):
        agent_in(FAIRFAX, email=f"first{index}@example.com")
    users_props(client)  # warm caches

    with CaptureQueriesContext(connection) as queries:
        users_props(client)
    before = len(queries)

    for index in range(6):
        person = agent_in(FAIRFAX, email=f"more{index}@example.com")
        assign(person, "branch_manager", ScopeType.OFFICE, office(FAIRFAX))
    with CaptureQueriesContext(connection) as queries:
        users_props(client)
    assert len(queries) == before


# ---------------------------------------------------------------------------
# Lockouts from a row
# ---------------------------------------------------------------------------


def post_from_list(client, target: User, **overrides):
    data = {
        "action": "disable",
        "business_reason": "Left the brokerage on Friday.",
        "expected_version": administration_version(target),
        "returnTo": "users",
        "returnQuery": "?role=realtor&page=2&evil=1",
    }
    data.update(overrides)
    # JSON, because that is what the row's dialog sends through Inertia.
    return client.post(
        reverse("user_account_state", args=[target.pk]),
        data=json.dumps(data),
        content_type="application/json",
    )


@pytest.mark.django_db
def test_disabling_from_a_row_returns_to_the_list_with_its_filters(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())

    response = post_from_list(client, target)

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('admin_users')}?role=realtor&page=2"
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_a_refused_row_lockout_re_renders_the_list_not_the_record(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())

    response = post_from_list(client, target, business_reason="  ")

    assert response.status_code == 422
    page = inertia_page_script(response)
    assert page["component"] == "UserDirectory"
    assert "business_reason" in page["props"]["errors"]["fields"]
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_a_stale_row_lockout_says_so_on_the_list(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())

    response = post_from_list(client, target, expected_version="stale")

    assert response.status_code == 409
    page = inertia_page_script(response)
    assert page["component"] == "UserDirectory"
    assert page["props"]["errors"]["form"]


@pytest.mark.django_db
def test_without_the_marker_the_record_page_flow_is_unchanged(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())

    response = post_from_list(client, target, returnTo="")

    assert response.status_code == 302
    assert response["Location"] == reverse("user_administration", args=[target.pk])
