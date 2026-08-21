"""Seed idempotency + directory data tests (offices, staff, contacts)."""

from __future__ import annotations

import pytest

from apps.user.models import Office, OfficeContactAssignment
from apps.user.office_payloads import office_info_payload
from apps.user.office_seed import seed_offices
from apps.user.user_seed import seed_staff


@pytest.mark.django_db
def test_seed_offices_populates_directory_details():
    seed_offices()
    massachusetts = Office.objects.get(slug="massachusetts")
    assert massachusetts.street_address == "301 Edgewater Pl"
    assert massachusetts.city == "Wakefield"
    assert massachusetts.state == "MA"
    assert massachusetts.main_phone == "(857) 869-2765"
    assert massachusetts.public_email == "suman@onest.realestate"
    assert isinstance(massachusetts.office_hours, list)
    assert {"day": "monday", "open": "09:00", "close": "17:00"} in (
        massachusetts.office_hours
    )


@pytest.mark.django_db
def test_seed_offices_is_idempotent_and_refreshes_details():
    first = seed_offices()
    assert not first.conflicting
    Office.objects.filter(slug="harrisburg").update(main_phone="")
    second = seed_offices()
    assert not second.conflicting
    harrisburg = Office.objects.get(slug="harrisburg")
    assert harrisburg.main_phone == "(730) 608-9412"


@pytest.mark.django_db
def test_seed_offices_covers_all_seven_markets():
    seed_offices()
    for slug in (
        "massachusetts",
        "harrisburg",
        "pittsburgh",
        "philadelphia",
        "connecticut",
        "new-hampshire",
        "charlottesville-va",
    ):
        target = Office.objects.get(slug=slug)
        assert target.street_address, f"{slug} missing address"
        assert target.main_phone, f"{slug} missing phone"


@pytest.mark.django_db
def test_seed_offices_does_not_invent_access_instructions():
    seed_offices()
    assert not Office.objects.exclude(parking_instructions="").exists()
    assert not Office.objects.exclude(access_instructions="").exists()


@pytest.mark.django_db
def test_seed_staff_creates_users_and_contact_assignments():
    from apps.user.roles import seed_role_groups

    seed_offices()
    seed_role_groups()
    report = seed_staff()
    assert report.created or report.matched

    suman = OfficeContactAssignment.objects.get(
        office__slug="massachusetts",
        user__email="suman@onest.realestate",
        assignment_type=OfficeContactAssignment.AssignmentType.MANAGER,
    )
    assert suman.is_primary is True

    # Coverage roles span offices beyond the holder's seat.
    roma_covered = set(
        OfficeContactAssignment.objects.filter(
            user__email="roma@onest.realestate",
            assignment_type=OfficeContactAssignment.AssignmentType.ADMIN,
        ).values_list("office__slug", flat=True)
    )
    assert roma_covered == {"harrisburg", "philadelphia", "pittsburgh"}

    # Corporate directory lives on the head office.
    head_types = set(
        OfficeContactAssignment.objects.filter(
            office__slug="onest-head-office"
        ).values_list("assignment_type", flat=True)
    )
    assert "principal_broker" in head_types
    assert "tc_manager" in head_types
    assert "it_manager" in head_types
    assert "accounting" in head_types


@pytest.mark.django_db
def test_seed_staff_is_idempotent():
    from apps.user.roles import seed_role_groups

    seed_offices()
    seed_role_groups()
    seed_staff()
    second = seed_staff()
    assert not second.contacts_created
    assert second.contacts_matched
    assert OfficeContactAssignment.objects.count() > 0


@pytest.mark.django_db
def test_seeded_office_page_shows_manager_and_corporate_contacts():
    from apps.user.roles import seed_role_groups

    seed_offices()
    seed_role_groups()
    seed_staff()
    payload = office_info_payload(
        Office.objects.get(slug="philadelphia"), include_internal=True
    )
    manager = payload["contacts"]["branchManager"]
    assert manager is not None
    assert manager["email"] == "malladhakal@onest.realestate"
    assert payload["directionsUrl"].startswith(
        "https://www.google.com/maps/search/?api=1&query="
    )
    corporate_emails = {person["email"] for person in payload["corporateContacts"]}
    assert "info@onest.realestate" in corporate_emails
    assert "sid@onest.realestate" in corporate_emails
