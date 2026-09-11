"""Privacy-aware peer Agent Directory."""

from __future__ import annotations

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.user.administration_fields import (
    ACTIVE,
    DEPARTED,
    ON_LEAVE,
    PROSPECTIVE,
    SUSPENDED,
)
from apps.user.services.agent_directory import (
    FORBIDDEN_PERSON_KEYS,
    apply_filters,
    build_agent_directory_page,
    directory_visible_queryset,
    parse_filters,
    project_directory_person,
)
from apps.user.tests.test_agent_administration import FAIRFAX, agent_in, office
from apps.user.tests.test_profile import completed_user


def _tiny_jpeg() -> SimpleUploadedFile:
    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", (220, 220), color=(20, 40, 60)).save(buffer, format="JPEG")
    return SimpleUploadedFile("head.jpg", buffer.getvalue(), content_type="image/jpeg")


def listing(client, **params) -> dict:
    response = client.get(reverse("agent_directory"), params, HTTP_X_INERTIA="true")
    assert response.status_code == 200
    return json.loads(response.content)["props"]


def person_ids(payload: dict) -> set[int]:
    return {row["id"] for row in payload["people"]["items"]}


@pytest.mark.django_db
def test_directory_lists_only_active_and_on_leave(client):
    viewer = agent_in(FAIRFAX, email="viewer@example.com")
    visible_active = agent_in(FAIRFAX, email="active@example.com")
    visible_leave = agent_in(FAIRFAX, email="leave@example.com")
    visible_leave.agent_status = ON_LEAVE
    visible_leave.save(update_fields=["agent_status"])

    for status, email in (
        (PROSPECTIVE, "prospective@example.com"),
        (SUSPENDED, "suspended@example.com"),
        (DEPARTED, "departed@example.com"),
    ):
        person = agent_in(FAIRFAX, email=email)
        person.agent_status = status
        person.save(update_fields=["agent_status"])

    disabled = agent_in(FAIRFAX, email="disabled@example.com")
    disabled.is_active = False
    disabled.save(update_fields=["is_active"])

    client.force_login(viewer)
    payload = listing(client)
    ids = person_ids(payload)
    assert visible_active.pk in ids
    assert visible_leave.pk in ids
    assert viewer.pk in ids
    assert (
        payload["people"]["pagination"]["totalItems"]
        == directory_visible_queryset().count()
    )
    assert ids == set(directory_visible_queryset().values_list("pk", flat=True))


@pytest.mark.django_db
def test_projection_omits_private_and_admin_keys(client):
    viewer = agent_in(FAIRFAX, email="viewer2@example.com")
    target = agent_in(FAIRFAX, email="target@example.com")
    target.preferred_name = "T"
    target.phone_number = "(703) 555-0199"
    target.languages = ["en", "es"]
    target.specialties = ["residential", "luxury"]
    target.license_state = "VA"
    target.street_address = "99 Secret Lane"
    target.internal_notes = "do not leak"
    target.agent_identifier = "ON-SECRET"
    target.mls_number = "MLS-1"
    target.license_number = "LIC-1"
    target.save()

    client.force_login(viewer)
    payload = listing(client, q="target@")
    # Name search does not match email — use preferred name / last name.
    payload = listing(client, q="T")
    row = next(item for item in payload["people"]["items"] if item["id"] == target.pk)

    assert row["preferredName"] == "T"
    assert row["workPhone"] == "(703) 555-0199"
    assert row["workEmail"] == "target@example.com"
    assert {item["code"] for item in row["languages"]} == {"en", "es"}
    assert {item["code"] for item in row["specialties"]} == {"residential", "luxury"}
    assert row["licenseState"] == "VA"
    assert FORBIDDEN_PERSON_KEYS.isdisjoint(row.keys())
    assert "streetAddress" not in row
    assert "internalNotes" not in row
    assert "agentIdentifier" not in row
    assert "agentStatus" not in row
    assert "mlsNumber" not in row
    assert "licenseNumber" not in row
    assert "headshotUrl" not in row


@pytest.mark.django_db
def test_detail_and_headshot_404_for_invisible(client):
    viewer = agent_in(FAIRFAX, email="viewer3@example.com")
    hidden = agent_in(FAIRFAX, email="hidden@example.com")
    hidden.agent_status = DEPARTED
    hidden.save(update_fields=["agent_status"])
    hidden.headshot.save("head.jpg", _tiny_jpeg(), save=True)

    client.force_login(viewer)
    assert (
        client.get(
            reverse("agent_directory_detail", args=[hidden.pk]),
            HTTP_X_INERTIA="true",
        ).status_code
        == 404
    )
    assert (
        client.get(reverse("agent_directory_headshot", args=[hidden.pk])).status_code
        == 404
    )


@pytest.mark.django_db
def test_detail_and_headshot_serve_visible_person(client):
    viewer = agent_in(FAIRFAX, email="viewer4@example.com")
    target = agent_in(FAIRFAX, email="photo@example.com")
    target.headshot.save("head.jpg", _tiny_jpeg(), save=True)

    client.force_login(viewer)
    detail = client.get(
        reverse("agent_directory_detail", args=[target.pk]),
        HTTP_X_INERTIA="true",
    )
    assert detail.status_code == 200
    props = json.loads(detail.content)["props"]
    assert props["person"]["id"] == target.pk
    assert props["person"]["headshotPath"] == reverse(
        "agent_directory_headshot", args=[target.pk]
    )
    assert FORBIDDEN_PERSON_KEYS.isdisjoint(props["person"].keys())

    photo = client.get(reverse("agent_directory_headshot", args=[target.pk]))
    assert photo.status_code == 200
    assert photo["Cache-Control"].startswith("private")


@pytest.mark.django_db
def test_filters_specialty_language_license_and_invalid_office(client):
    viewer = agent_in(FAIRFAX, email="viewer5@example.com")
    match = agent_in(FAIRFAX, email="match@example.com")
    match.specialties = ["commercial"]
    match.languages = ["es"]
    match.license_state = "MD"
    match.save()

    other = agent_in(FAIRFAX, email="other@example.com")
    other.specialties = ["residential"]
    other.languages = ["en"]
    other.license_state = "VA"
    other.save()

    client.force_login(viewer)
    by_specialty = listing(client, specialty="commercial")
    assert person_ids(by_specialty) == {match.pk}

    by_language = listing(client, language="es")
    assert person_ids(by_language) == {match.pk}

    by_license = listing(client, licenseState="MD")
    assert person_ids(by_license) == {match.pk}

    # Unknown office id intersects the visible set and returns empty — no leak.
    empty = listing(client, office="999999")
    assert empty["people"]["items"] == []
    assert empty["people"]["pagination"]["totalItems"] == 0
    assert empty["empty"]["kind"] == "no-results"

    # Invalid specialty is dropped, not used as an oracle.
    filters = parse_filters({"specialty": "not-a-real-specialty"})
    assert filters.specialty == ""


@pytest.mark.django_db
def test_name_search_does_not_match_private_agent_id(client):
    viewer = agent_in(FAIRFAX, email="viewer6@example.com")
    target = agent_in(FAIRFAX, email="seek@example.com")
    target.agent_identifier = "SECRETID99"
    target.first_name = "Seekable"
    target.save()

    client.force_login(viewer)
    by_secret = listing(client, q="SECRETID99")
    assert target.pk not in person_ids(by_secret)

    by_name = listing(client, q="Seekable")
    assert target.pk in person_ids(by_name)


@pytest.mark.django_db
def test_unauthenticated_directory_redirects(client):
    response = client.get(reverse("agent_directory"))
    assert response.status_code in {302, 401}


@pytest.mark.django_db
def test_project_directory_person_uses_gated_headshot_only():
    user = completed_user(email="gate@example.com", office=office(FAIRFAX))
    user.agent_status = ACTIVE
    user.save(update_fields=["agent_status"])
    user.headshot.save("head.jpg", _tiny_jpeg(), save=True)
    user.refresh_from_db()
    person = project_directory_person(user)
    assert person["headshotPath"] == reverse("agent_directory_headshot", args=[user.pk])
    assert "media" not in (person["headshotPath"] or "")
    assert "headshotUrl" not in person


@pytest.mark.django_db
def test_apply_filters_only_narrows_visible_queryset():
    visible = agent_in(FAIRFAX, email="narrow@example.com")
    visible.specialties = ["land"]
    visible.save(update_fields=["specialties"])
    qs = directory_visible_queryset()
    filtered = apply_filters(qs, parse_filters({"specialty": "land"}))
    assert list(filtered.values_list("pk", flat=True)) == [visible.pk]
    page = build_agent_directory_page(
        filters=parse_filters({"specialty": "land"}),
        page=1,
    )
    assert page["people"]["pagination"]["totalItems"] == 1
