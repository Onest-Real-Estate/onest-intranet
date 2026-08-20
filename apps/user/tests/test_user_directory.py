"""The scoped people directory.

Four things could leak here and each has its own section: the row set (scope),
the columns (field-level permissions), the counts (aggregation), and the
parameters (a crafted office, region, role, or sort). Everything else —
paging, sorting, empty states — is behaviour the page depends on.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import AGENT, ScopeType
from apps.user.services.user_directory import (
    DirectoryFilters,
    FieldGroup,
    build_directory_page,
    parse_filters,
    parse_sort,
    visible_field_groups,
)
from apps.user.tests.test_agent_administration import (
    CHARLOTTESVILLE,
    CONNECTICUT,
    FAIRFAX,
    MID_ATLANTIC,
    agent_in,
    assign,
    branch_manager,
    company_admin,
    office,
    region_manager,
)
from apps.user.tests.test_profile import completed_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def listing(client, **params) -> dict:
    response = client.get(reverse("admin_users"), params, HTTP_X_INERTIA="true")
    assert response.status_code == 200
    return json.loads(response.content)["props"]


def emails(payload: dict) -> set[str]:
    return {row["email"] for row in payload["users"]["items"]}


def reader(email: str, *codenames: str, office_slug: str = FAIRFAX) -> User:
    """Somebody with exactly the named permissions, seated in one office.

    Built from bare Django permissions rather than a role so the field-level
    matrix can name one grant at a time — a role bundle would always drag its
    neighbours in and hide which permission the column actually needs.
    """
    user = completed_user(email=email, office=office(office_slug))
    assign(user, AGENT, ScopeType.OFFICE, office(office_slug))
    for codename in codenames:
        app_label, name = codename.split(".", 1)
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=name)
        )
    return user


# ---------------------------------------------------------------------------
# Scope: which rows exist at all
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_directory_requires_the_view_permission(client):
    client.force_login(agent_in(FAIRFAX))
    assert client.get(reverse("admin_users")).status_code == 403


@pytest.mark.django_db
def test_a_branch_manager_sees_only_their_own_office(client):
    agent_in(FAIRFAX, email="inscope@example.com")
    agent_in(CONNECTICUT, email="outofscope@example.com")
    client.force_login(branch_manager(FAIRFAX))
    found = emails(listing(client))
    assert "inscope@example.com" in found
    assert "outofscope@example.com" not in found


@pytest.mark.django_db
def test_a_region_manager_sees_every_office_in_their_region(client):
    agent_in(FAIRFAX, email="fairfax@example.com")
    agent_in(CHARLOTTESVILLE, email="charlottesville@example.com")
    agent_in(CONNECTICUT, email="connecticut@example.com")
    client.force_login(region_manager(MID_ATLANTIC))
    found = emails(listing(client))
    assert {"fairfax@example.com", "charlottesville@example.com"} <= found
    assert "connecticut@example.com" not in found


@pytest.mark.django_db
def test_search_cannot_reach_across_the_scope_boundary(client):
    agent_in(CONNECTICUT, email="outofscope@example.com")
    client.force_login(branch_manager(FAIRFAX))
    payload = listing(client, q="outofscope")
    assert payload["users"]["items"] == []
    assert payload["users"]["pagination"]["totalItems"] == 0


@pytest.mark.django_db
def test_counts_are_computed_over_the_scoped_set_only(client):
    agent_in(FAIRFAX, email="one@example.com")
    agent_in(CONNECTICUT, email="two@example.com")
    agent_in(CONNECTICUT, email="three@example.com")
    manager = branch_manager(FAIRFAX)
    client.force_login(manager)
    summary = listing(client)["summary"]
    # The manager themselves plus the one agent in their office. A summary
    # that counted the brokerage would be an enumeration oracle.
    assert summary["total"] == 2
    assert summary["active"] == 2
    assert summary["disabled"] == 0


# ---------------------------------------------------------------------------
# Crafted parameters
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_crafted_office_id_cannot_widen_the_listing(client):
    agent_in(CONNECTICUT, email="outofscope@example.com")
    client.force_login(branch_manager(FAIRFAX))
    payload = listing(client, office=str(office(CONNECTICUT).pk))
    assert payload["users"]["items"] == []


@pytest.mark.django_db
def test_a_crafted_region_id_cannot_widen_the_listing(client):
    agent_in(CONNECTICUT, email="outofscope@example.com")
    client.force_login(branch_manager(FAIRFAX))
    payload = listing(client, region=str(office("region-new-england").pk))
    assert payload["users"]["items"] == []


@pytest.mark.django_db
def test_filter_options_never_exceed_the_actors_scope(client):
    client.force_login(branch_manager(FAIRFAX))
    options = listing(client)["filterOptions"]
    labels = {option["label"] for option in options["offices"]}
    assert labels == {office(FAIRFAX).path_label()}


@pytest.mark.django_db
def test_an_unknown_filter_value_is_dropped_rather_than_echoed(client):
    agent_in(FAIRFAX, email="inscope@example.com")
    client.force_login(company_admin())
    payload = listing(client, status="not-a-status", account="maybe", sort="salary")
    assert payload["users"]["filters"]["status"] == ""
    assert payload["users"]["filters"]["account"] == ""
    assert payload["users"]["sort"]["key"] == "name"
    assert "inscope@example.com" in emails(payload)


@pytest.mark.django_db
def test_a_non_numeric_page_falls_back_to_the_first_page(client):
    client.force_login(company_admin())
    payload = listing(client, page="../../etc/passwd")
    assert payload["users"]["pagination"]["page"] == 1


# ---------------------------------------------------------------------------
# Field-level permissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_view_users_alone_omits_every_administrative_column(client):
    agent_in(FAIRFAX, email="subject@example.com")
    client.force_login(reader("support@example.com", "web.view_users"))
    payload = listing(client)
    row = next(item for item in payload["users"]["items"] if item["email"])
    assert "agentStatus" not in row
    assert "agentIdentifier" not in row
    assert "startDate" not in row
    assert payload["visible"]["administration"] is False
    assert "agentStatuses" not in payload["filterOptions"]


@pytest.mark.django_db
def test_it_support_visibility_does_not_imply_contract_visibility(client):
    agent_in(FAIRFAX, email="subject@example.com")
    client.force_login(reader("support@example.com", "web.view_users"))
    payload = listing(client)
    assert payload["visible"]["contract"] is False
    assert all("contract" not in row for row in payload["users"]["items"])


@pytest.mark.django_db
def test_the_contract_column_appears_with_its_own_permission(client):
    agent_in(FAIRFAX, email="subject@example.com")
    client.force_login(
        reader("tc@example.com", "web.view_users", "web.view_agent_contracts")
    )
    payload = listing(client)
    assert payload["visible"]["contract"] is True
    assert all("contract" in row for row in payload["users"]["items"])


@pytest.mark.django_db
def test_administrative_columns_appear_with_the_administration_grant(client):
    agent_in(FAIRFAX, email="subject@example.com")
    client.force_login(
        reader(
            "admin@example.com",
            "web.view_users",
            "user.view_user_administration",
        )
    )
    payload = listing(client)
    row = next(
        item
        for item in payload["users"]["items"]
        if item["email"] == "subject@example.com"
    )
    assert row["agentStatus"]["value"] == "active"
    assert payload["visible"]["administration"] is True
    assert payload["canOpenRecord"] is True


@pytest.mark.django_db
def test_search_matches_an_agent_id_only_for_readers_who_may_see_it(client):
    target = agent_in(FAIRFAX, email="subject@example.com")
    target.agent_identifier = "ON-4417"
    target.save(update_fields=["agent_identifier"])

    client.force_login(reader("support@example.com", "web.view_users"))
    assert listing(client, q="ON-4417")["users"]["items"] == []

    client.logout()
    client.force_login(
        reader(
            "admin@example.com",
            "web.view_users",
            "user.view_user_administration",
        )
    )
    assert "subject@example.com" in emails(listing(client, q="ON-4417"))


@pytest.mark.django_db
def test_sorting_by_a_hidden_column_falls_back_to_name(client):
    agent_in(FAIRFAX, email="subject@example.com")
    client.force_login(reader("support@example.com", "web.view_users"))
    payload = listing(client, sort="status")
    assert payload["users"]["sort"]["key"] == "name"


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_account_filter_separates_active_from_disabled(client):
    disabled = agent_in(FAIRFAX, email="disabled@example.com")
    disabled.is_active = False
    disabled.save(update_fields=["is_active"])
    agent_in(CHARLOTTESVILLE, email="active@example.com")
    client.force_login(company_admin())

    assert "disabled@example.com" in emails(listing(client, account="disabled"))
    assert "active@example.com" not in emails(listing(client, account="disabled"))
    assert "disabled@example.com" not in emails(listing(client, account="active"))


@pytest.mark.django_db
def test_the_onboarding_filter_uses_the_hubs_own_completion_state(client):
    started = User.objects.create_user(
        email="started@example.com",
        office=office(FAIRFAX),
        profile_completed=False,
        last_login=timezone.now(),
    )
    User.objects.create_user(
        email="untouched@example.com",
        office=office(FAIRFAX),
        profile_completed=False,
    )
    client.force_login(company_admin())

    assert emails(listing(client, onboarding="in_progress")) == {started.email}
    assert emails(listing(client, onboarding="not_started")) == {
        "untouched@example.com"
    }
    assert "started@example.com" not in emails(listing(client, onboarding="complete"))


@pytest.mark.django_db
def test_the_last_login_filter_finds_dormant_accounts(client):
    dormant = agent_in(FAIRFAX, email="dormant@example.com")
    dormant.last_login = timezone.now() - dt.timedelta(days=200)
    dormant.save(update_fields=["last_login"])
    recent = agent_in(CHARLOTTESVILLE, email="recent@example.com")
    recent.last_login = timezone.now() - dt.timedelta(days=2)
    recent.save(update_fields=["last_login"])
    client.force_login(company_admin())

    assert emails(listing(client, lastLogin="over_90d")) == {"dormant@example.com"}
    assert "recent@example.com" in emails(listing(client, lastLogin="7d"))
    assert "dormant@example.com" not in emails(listing(client, lastLogin="never"))


@pytest.mark.django_db
def test_the_role_filter_matches_live_assignments_only(client):
    holder = agent_in(FAIRFAX, email="holder@example.com")
    agent_in(CHARLOTTESVILLE, email="other@example.com")
    assign(holder, "branch_manager", ScopeType.OFFICE, office(FAIRFAX))
    client.force_login(company_admin())

    found = emails(listing(client, role="branch_manager"))
    assert "holder@example.com" in found
    assert "other@example.com" not in found


@pytest.mark.django_db
def test_the_status_filter_needs_the_administration_grant(client):
    departed = agent_in(FAIRFAX, email="departed@example.com")
    departed.agent_status = "departed"
    departed.save(update_fields=["agent_status"])
    client.force_login(reader("support@example.com", "web.view_users"))
    # The filter is not offered and is not honoured: a reader who cannot see
    # the column must not be able to partition the directory by it either.
    assert "departed@example.com" in emails(listing(client, status="active"))


# ---------------------------------------------------------------------------
# Paging and empty states
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_pagination_reports_a_stable_slice(client):
    for index in range(30):
        completed_user(email=f"agent{index:02d}@example.com", office=office(FAIRFAX))
    client.force_login(company_admin())

    first = listing(client)["users"]
    second = listing(client, page=2)["users"]
    assert first["pagination"]["pageSize"] == 25
    assert len(first["items"]) == 25
    assert first["pagination"]["hasNext"] is True
    assert second["pagination"]["page"] == 2
    assert not (
        {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}
    )


@pytest.mark.django_db
def test_a_page_beyond_the_end_clamps_to_the_last_page(client):
    agent_in(FAIRFAX, email="only@example.com")
    client.force_login(company_admin())
    payload = listing(client, page=99)
    assert payload["users"]["pagination"]["page"] == 1


@pytest.mark.django_db
def test_an_actor_with_no_scope_gets_an_empty_directory(client):
    agent_in(FAIRFAX, email="somebody@example.com")
    orphan = reader("orphan@example.com", "web.view_users")
    orphan.office = None
    orphan.save(update_fields=["office"])
    UserRoleAssignment.objects.filter(user=orphan).delete()
    client.force_login(orphan)
    payload = listing(client)
    assert payload["users"]["items"] == []
    assert payload["summary"]["total"] == 0


# ---------------------------------------------------------------------------
# Service-level contracts the view relies on
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_field_groups_track_the_actors_grants():
    support = reader("support@example.com", "web.view_users")
    assert visible_field_groups(support) == frozenset({FieldGroup.IDENTITY})

    admin = company_admin("boss@example.com")
    groups = visible_field_groups(admin)
    assert FieldGroup.ADMINISTRATION in groups
    assert FieldGroup.NOTES in groups


@pytest.mark.django_db
def test_the_disabled_summary_counts_disabled_accounts():
    disabled = agent_in(FAIRFAX, email="disabled@example.com")
    disabled.is_active = False
    disabled.save(update_fields=["is_active"])
    actor = company_admin()
    _page, summary, _groups = build_directory_page(
        actor,
        filters=DirectoryFilters(),
        sort="name",
        direction="asc",
        page=1,
    )
    assert summary["disabled"] == 1
    assert summary["active"] == summary["total"] - 1


def test_parse_filters_rejects_values_it_does_not_recognize():
    filters = parse_filters(
        {
            "q": "  bob ",
            "office": "12; DROP TABLE",
            "region": "7",
            "role": "not_a_role",
            "status": "active",
            "account": "disabled",
            "onboarding": "complete",
            "lastLogin": "7d",
        }
    )
    assert filters.q == "bob"
    assert filters.office == ""
    assert filters.region == "7"
    assert filters.role == ""
    assert filters.status == "active"
    # region, status, account, onboarding, lastLogin — q never counts.
    assert filters.active_count == 5


def test_parse_sort_defaults_to_name_ascending():
    assert parse_sort({}) == ("name", "asc")
    assert parse_sort({"sort": "email", "direction": "desc"}) == ("email", "desc")
    assert parse_sort({"sort": "nope"}) == ("name", "asc")


@pytest.mark.django_db
def test_a_user_without_an_office_is_listed_only_company_wide(client):
    User.objects.create_user(email="floating@example.com", profile_completed=True)
    client.force_login(branch_manager(FAIRFAX))
    assert "floating@example.com" not in emails(listing(client))

    client.logout()
    client.force_login(company_admin())
    assert "floating@example.com" in emails(listing(client))


@pytest.mark.django_db
def test_every_row_carries_the_office_path_for_disambiguation(client):
    agent_in(FAIRFAX, email="subject@example.com")
    client.force_login(company_admin())
    row = next(
        item
        for item in listing(client)["users"]["items"]
        if item["email"] == "subject@example.com"
    )
    assert row["officePathLabel"] == office(FAIRFAX).path_label()
    assert row["regionName"] == office(FAIRFAX).region_name()
    assert row["accountState"]["value"] == "active"


@pytest.mark.django_db
def test_the_scope_label_describes_the_actor_not_the_brokerage(client):
    client.force_login(branch_manager(FAIRFAX))
    assert listing(client)["scope"]["level"] == "office"

    client.logout()
    client.force_login(company_admin())
    assert listing(client)["scope"] == {
        "level": "brokerage",
        "label": "Brokerage-wide",
    }


@pytest.mark.django_db
def test_regions_are_offered_as_a_filter_to_a_region_manager(client):
    client.force_login(region_manager(MID_ATLANTIC))
    options = listing(client)["filterOptions"]
    assert {option["label"] for option in options["regions"]} == {
        Office.objects.get(slug=MID_ATLANTIC).name
    }
