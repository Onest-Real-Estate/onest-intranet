"""Scoped office and regional administration tests."""

from __future__ import annotations

import json

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.user.models import Office, OfficeContactAssignment, User
from apps.user.office_payloads import office_info_payload
from apps.user.roles import ADMIN, AGENT, BRANCH_MANAGER, REGION_MANAGER, ScopeType
from apps.user.services.office_administration import (
    ConfirmationRequired,
    StaleOfficeVersion,
    office_version,
    update_office_info,
    update_office_structure,
    upsert_contact,
)
from apps.user.tests.test_profile import completed_user

FAIRFAX = "fairfax-va"
CHARLOTTESVILLE = "charlottesville-va"
MID_ATLANTIC = "region-mid-atlantic"
CONNECTICUT = "connecticut"


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    from apps.user.models import UserRoleAssignment

    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def company_admin(email: str = "admin@example.com") -> User:
    user = completed_user(email=email, office=office(FAIRFAX))
    assign(user, ADMIN, ScopeType.COMPANY)
    return user


def branch_manager(slug: str = FAIRFAX, email: str = "branch@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office(slug))
    return user


def region_manager(
    region_slug: str = MID_ATLANTIC,
    seat: str = FAIRFAX,
    email: str = "region@example.com",
) -> User:
    user = completed_user(email=email, office=office(seat))
    assign(user, REGION_MANAGER, ScopeType.REGION, office(region_slug))
    return user


def agent_in(slug: str, email: str = "agent@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, AGENT, ScopeType.OFFICE, office(slug))
    return user


def props(response) -> dict:
    return json.loads(response.content)["props"]


@pytest.mark.django_db
def test_branch_manager_lists_only_own_office(client):
    client.force_login(branch_manager(FAIRFAX))
    response = client.get(reverse("admin_offices"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    items = props(response)["offices"]["items"]
    keys = {row["stableKey"] for row in items}
    assert FAIRFAX in keys
    assert CHARLOTTESVILLE not in keys


@pytest.mark.django_db
def test_region_manager_lists_region_descendants(client):
    client.force_login(region_manager())
    response = client.get(reverse("admin_offices"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    keys = {row["stableKey"] for row in props(response)["offices"]["items"]}
    assert FAIRFAX in keys
    assert CHARLOTTESVILLE in keys
    assert CONNECTICUT not in keys


@pytest.mark.django_db
def test_branch_manager_cannot_open_out_of_scope_office(client):
    client.force_login(branch_manager(FAIRFAX))
    other = office(CHARLOTTESVILLE)
    response = client.get(reverse("admin_office", args=[other.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_agent_cannot_reach_office_admin(client):
    client.force_login(agent_in(FAIRFAX))
    assert client.get(reverse("admin_offices")).status_code == 403


@pytest.mark.django_db
def test_branch_manager_can_update_info(client):
    actor = branch_manager(FAIRFAX)
    target = office(FAIRFAX)
    client.force_login(actor)
    response = client.post(
        reverse("admin_office_update", args=[target.pk]),
        {
            "expected_version": office_version(target),
            "name": "Fairfax VA Updated",
            "street_address": "1 Main St",
            "city": "Fairfax",
            "state": "VA",
            "zip_code": "22030",
            "main_phone": "(703) 555-0100",
            "public_email": "fairfax@example.com",
            "internal_email": "fairfax-internal@example.com",
            "office_hours_text": "Mon–Fri 9–5",
            "parking_instructions": "Lot B",
            "access_instructions": "Buzz 12",
            "access_instructions_internal": "on",
        },
    )
    assert response.status_code == 302
    target.refresh_from_db()
    assert target.name == "Fairfax VA Updated"
    assert target.street_address == "1 Main St"
    assert AuditEvent.objects.filter(action="office.updated").exists()


@pytest.mark.django_db
def test_branch_manager_cannot_restructure(client):
    actor = branch_manager(FAIRFAX)
    target = office(FAIRFAX)
    client.force_login(actor)
    response = client.post(
        reverse("admin_office_structure", args=[target.pk]),
        {
            "expected_version": office_version(target),
            "kind": target.kind,
            "parent": target.parent.pk if target.parent else "",
            "is_active": "on",
            "is_assignable": "on",
            "confirmed": "1",
        },
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_company_admin_deactivate_requires_confirmation():
    actor = company_admin()
    target = office(FAIRFAX)
    with pytest.raises(ConfirmationRequired) as raised:
        update_office_structure(
            actor=actor,
            office=target,
            cleaned={
                "parent": target.parent,
                "kind": target.kind,
                "is_active": False,
                "is_assignable": target.is_assignable,
            },
            expected_version=office_version(target),
            confirmed=False,
        )
    assert raised.value.impact
    assert any(item["label"] == "Active status" for item in raised.value.impact)


@pytest.mark.django_db
def test_company_admin_deactivate_with_confirmation():
    actor = company_admin()
    target = office(FAIRFAX)
    update_office_structure(
        actor=actor,
        office=target,
        cleaned={
            "parent": target.parent,
            "kind": target.kind,
            "is_active": False,
            "is_assignable": target.is_assignable,
        },
        expected_version=office_version(target),
        confirmed=True,
    )
    target.refresh_from_db()
    assert target.is_active is False
    assert AuditEvent.objects.filter(action="office.deactivated").exists()


@pytest.mark.django_db
def test_stale_version_rejected():
    actor = company_admin()
    target = office(FAIRFAX)
    with pytest.raises(StaleOfficeVersion):
        update_office_info(
            actor=actor,
            office=target,
            cleaned={"name": target.name},
            expected_version="stale",
        )


@pytest.mark.django_db
def test_contact_must_belong_to_office():
    actor = company_admin()
    target = office(FAIRFAX)
    outsider = agent_in(CHARLOTTESVILLE, email="outsider@example.com")
    with pytest.raises(ValidationError):
        upsert_contact(
            actor=actor,
            office=target,
            user=outsider,
            assignment_type=OfficeContactAssignment.AssignmentType.MANAGER,
            expected_version=office_version(target),
        )


@pytest.mark.django_db
def test_contact_primary_uniqueness():
    actor = company_admin()
    target = office(FAIRFAX)
    first = agent_in(FAIRFAX, email="first@example.com")
    second = agent_in(FAIRFAX, email="second@example.com")
    upsert_contact(
        actor=actor,
        office=target,
        user=first,
        assignment_type=OfficeContactAssignment.AssignmentType.MANAGER,
        is_primary=True,
        expected_version=office_version(target),
    )
    target.refresh_from_db()
    upsert_contact(
        actor=actor,
        office=target,
        user=second,
        assignment_type=OfficeContactAssignment.AssignmentType.MANAGER,
        is_primary=True,
        expected_version=office_version(target),
    )
    primaries = OfficeContactAssignment.objects.filter(
        office=target,
        assignment_type=OfficeContactAssignment.AssignmentType.MANAGER,
        is_primary=True,
    )
    assert primaries.count() == 1
    assert primaries.get().user.pk == second.pk


@pytest.mark.django_db
def test_tc_and_it_contact_types():
    actor = company_admin()
    target = office(FAIRFAX)
    person = agent_in(FAIRFAX, email="tc@example.com")
    upsert_contact(
        actor=actor,
        office=target,
        user=person,
        assignment_type=OfficeContactAssignment.AssignmentType.TRANSACTION_COORDINATOR,
        is_primary=True,
        expected_version=office_version(target),
    )
    target.refresh_from_db()
    upsert_contact(
        actor=actor,
        office=target,
        user=person,
        assignment_type=OfficeContactAssignment.AssignmentType.IT_SUPPORT,
        is_primary=True,
        expected_version=office_version(target),
    )
    payload = office_info_payload(target, include_internal=True)
    assert payload["contacts"]["transactionCoordinator"]["email"] == "tc@example.com"
    assert payload["contacts"]["itSupport"]["email"] == "tc@example.com"


@pytest.mark.django_db
def test_office_info_hides_internal_access_without_flag():
    target = office(FAIRFAX)
    target.access_instructions = "Door code 9999"
    target.access_instructions_internal = True
    target.internal_email = "secret@example.com"
    target.save()
    public = office_info_payload(target, include_internal=False)
    assert public["accessInstructions"] == ""
    assert public["internalEmail"] == ""
    internal = office_info_payload(target, include_internal=True)
    assert internal["accessInstructions"] == "Door code 9999"
    assert internal["internalEmail"] == "secret@example.com"


@pytest.mark.django_db
def test_office_info_page_uses_primary_office(client):
    user = agent_in(FAIRFAX)
    client.force_login(user)
    response = client.get(reverse("office_info"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    payload = props(response)["officeInfo"]
    assert payload["stableKey"] == FAIRFAX
    assert user.office is not None
    assert payload["id"] == user.office.pk


@pytest.mark.django_db
def test_office_info_no_cross_office_leak_when_primary_changes(client):
    user = agent_in(FAIRFAX)
    client.force_login(user)
    first = props(client.get(reverse("office_info"), HTTP_X_INERTIA="true"))[
        "officeInfo"
    ]
    user.office = office(CHARLOTTESVILLE)
    user.save(update_fields=["office"])
    second = props(client.get(reverse("office_info"), HTTP_X_INERTIA="true"))[
        "officeInfo"
    ]
    assert first["stableKey"] == FAIRFAX
    assert second["stableKey"] == CHARLOTTESVILLE
    assert first["id"] != second["id"]
    assert first["version"] != second["version"]


@pytest.mark.django_db
def test_detail_shows_agent_preview(client):
    client.force_login(company_admin())
    target = office(FAIRFAX)
    response = client.get(
        reverse("admin_office", args=[target.pk]), HTTP_X_INERTIA="true"
    )
    assert response.status_code == 200
    admin = props(response)["administration"]
    assert admin["agentPreview"]["stableKey"] == FAIRFAX
    assert admin["capabilities"]["canRestructure"] is True
