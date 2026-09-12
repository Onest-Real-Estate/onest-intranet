"""Resumable onboarding profile: sections, headshot, review, and finalization."""

from __future__ import annotations

import dataclasses
import io
import json
import logging

import pytest
from allauth.socialaccount.models import SocialAccount
from django.core.files.storage import FileSystemStorage
from django.forms.models import model_to_dict
from django.urls import reverse

from apps.audit.models import AuditEvent, DomainEvent
from apps.user.models import Office, User, UserOnboardingCase
from apps.user.services import onboarding_profile
from apps.user.services.onboarding_operations import reset_required_setup
from apps.user.tests.test_onboarding import assignable_office, make_agent, make_image

INERTIA = {"HTTP_X_INERTIA": "true"}

IDENTITY = {"first_name": "Bob", "last_name": "Lee", "preferred_name": "  Bobby   B "}
CONTACT = {
    "phone_number": "202.555.0100",
    "preferred_contact_method": "text",
    "street_address": "1 Main St",
    "city": "Fairfax",
    "state": "VA",
    "zip_code": "22030",
}


def credentials(**overrides):
    office_id = assignable_office().pk
    data = {
        "office": str(office_id),
        "confirm_office": "true",
        "confirmed_office_id": str(office_id),
        "license_number": " va-99 11 ",
        "license_state": "VA",
        "license_expires_on": "2030-06-30",
        "mls_number": "",
        "nrds_number": "123-456-789",
        "bio": "Hello\r\n\r\n\r\nthere",
        "languages": ["es", "en", "es"],
        "website_url": "BobSells.example.com",
        "linkedin_url": "linkedin.com/in/bob",
        "facebook_url": "",
        "instagram_url": "",
        "x_url": "",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def agent(**fields) -> User:
    fields.setdefault("email", "agent@example.com")
    return make_agent(User.objects.create_user(**fields))


def link_microsoft(user: User, **names) -> SocialAccount:
    return SocialAccount.objects.create(
        user=user, provider="microsoft", uid=f"ms-{user.pk}", extra_data=names
    )


def flow(client, section: str | None = None) -> dict:
    url = reverse("onboarding")
    if section:
        url = f"{url}?section={section}"
    response = client.get(url, **INERTIA)
    assert response.status_code == 200, response.content[:300]
    return json.loads(response.content)["props"]


def revision(props: dict, section: str) -> str:
    return next(
        item["revision"]
        for item in props["profileFlow"]["sections"]
        if item["code"] == section
    )


def save(client, section: str, data: dict, *, props=None, json_body=False):
    props = props or flow(client, section)
    payload = {
        **data,
        "revision": revision(props, section),
        "expected_onboarding_version": props["profileFlow"]["onboardingVersion"],
    }
    url = reverse("onboarding_profile_save", args=[section])
    if json_body:
        return client.post(
            url, json.dumps(payload), content_type="application/json", **INERTIA
        )
    return client.post(url, payload, **INERTIA)


def finalize(client, *, confirm=True, version=None, json_body=False):
    if version is None:
        version = flow(client, "review")["profileFlow"]["onboardingVersion"]
    payload = {"confirm_review": confirm, "expected_onboarding_version": version}
    url = reverse("onboarding_profile_finalize")
    if json_body:
        return client.post(
            url, json.dumps(payload), content_type="application/json", **INERTIA
        )
    payload["confirm_review"] = "true" if confirm else "false"
    return client.post(url, payload, **INERTIA)


def upload_headshot(client, name="photo.jpg"):
    image = make_image("JPEG", (300, 300))
    image.name = name
    response = client.post(reverse("headshot_upload"), {"headshot": image})
    assert response.status_code == 200, response.content
    return response


def fill_sections(client) -> None:
    for section, data in (
        ("identity", IDENTITY),
        ("contact", CONTACT),
        ("credentials", credentials()),
    ):
        response = save(client, section, data)
        assert response.status_code == 302, response.content[:500]


def complete_profile(client) -> None:
    """Drive the real flow end to end. The caller provides a writable MEDIA_ROOT."""
    upload_headshot(client)
    fill_sections(client)
    response = finalize(client)
    assert response.status_code == 302, response.content[:500]
    assert response.url == reverse("dashboard")


def page(response) -> dict:
    return json.loads(response.content)["props"]


# ---------------------------------------------------------------------------
# Resume and policy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_new_agent_starts_at_identity_and_resumes_where_they_left_off(
    client, media_root
):
    user = agent()
    client.force_login(user)
    props = flow(client)
    assert props["profileFlow"]["currentSection"] == "identity"
    assert [item["status"] for item in props["profileFlow"]["sections"]] == [
        "not_started",
        "not_started",
        "not_started",
        None,
    ]

    upload_headshot(client)
    response = save(client, "identity", IDENTITY)
    assert response.status_code == 302
    assert response.url == f"{reverse('onboarding')}?section=contact"

    # A fresh visit, as after closing the tab or signing in again, resumes here.
    resumed = flow(client)
    assert resumed["profileFlow"]["currentSection"] == "contact"
    assert resumed["profileFlow"]["sections"][0]["status"] == "complete"
    user.refresh_from_db()
    assert user.profile_completed is False
    assert user.preferred_name == "Bobby B"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("review", "review"),
        ("credentials", "credentials"),
        ("../admin", "identity"),
        ("", "identity"),
    ],
)
def test_section_query_is_validated_against_the_server_catalog(
    client, requested, expected
):
    client.force_login(agent())
    assert flow(client, requested)["profileFlow"]["currentSection"] == expected


@pytest.mark.django_db
def test_microsoft_and_brokerage_owned_fields_are_distinguished(client):
    user = agent(first_name="Bob", last_name="Lee")
    link_microsoft(user, givenName="Bob", surname="Lee")
    client.force_login(user)

    props = flow(client)
    fields = props["profileFlow"]["fields"]
    assert props["identity"]["email"] == "agent@example.com"
    assert props["identity"]["emailOwner"] == "microsoft"
    assert props["identity"]["legalNameLocked"] is True
    assert props["identity"]["legalNameNotice"] is None
    assert fields["first_name"]["owner"] == "microsoft"
    assert fields["first_name"]["readOnly"] is True
    assert fields["office"]["owner"] == "brokerage"
    assert fields["phone_number"]["owner"] == "agent"
    assert fields["headshot"]["required"] is True
    assert fields["mls_number"]["required"] is False
    # Availability reasons are server-owned, not hard-coded in React.
    assert "placeholder" in fields["mls_number"]["guidance"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "names",
    [{}, {"givenName": "Bob"}, {"givenName": "  ", "surname": "Lee"}],
)
def test_empty_or_partial_microsoft_name_stays_editable_and_required(client, names):
    user = agent()
    link_microsoft(user, **names)
    client.force_login(user)

    props = flow(client)
    assert props["identity"]["legalNameLocked"] is False
    assert "full name" in props["identity"]["legalNameNotice"]
    assert props["profileFlow"]["fields"]["first_name"]["readOnly"] is False

    response = save(client, "identity", {"first_name": "", "last_name": ""})
    assert response.status_code == 422
    assert {"first_name", "last_name"} <= set(page(response)["validation"]["fields"])


@pytest.mark.django_db
def test_complete_microsoft_name_wins_over_posted_and_conflicting_names(client):
    user = agent(first_name="Robert", last_name="Lee-Old")
    link_microsoft(user, givenName="Bob", surname="Lee")
    client.force_login(user)

    props = flow(client)
    assert "Microsoft name" in props["identity"]["legalNameNotice"]
    assert props["identity"]["legalName"] == {"firstName": "Bob", "lastName": "Lee"}

    response = save(
        client, "identity", {"first_name": "Mallory", "last_name": "X"}, props=props
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert (user.first_name, user.last_name, user.display_name) == (
        "Bob",
        "Lee",
        "Bob Lee",
    )


@pytest.mark.django_db
def test_field_policy_can_require_a_field_from_a_later_onboarding_version(
    client, monkeypatch
):
    specs = tuple(
        dataclasses.replace(spec, required=True, required_from_version=1)
        if spec.key == "mls_number"
        else spec
        for spec in onboarding_profile.PROFILE_FIELD_SPECS
    )
    monkeypatch.setattr(onboarding_profile, "PROFILE_FIELD_SPECS", specs)

    earlier = agent(email="v0@example.com")
    client.force_login(earlier)
    assert flow(client)["profileFlow"]["fields"]["mls_number"]["required"] is False
    assert save(client, "credentials", credentials()).status_code == 302

    later = agent(email="v1@example.com", onboarding_version=1)
    client.force_login(later)
    assert flow(client)["profileFlow"]["fields"]["mls_number"]["required"] is True
    response = save(client, "credentials", credentials())
    assert response.status_code == 422
    assert "mls_number" in page(response)["validation"]["fields"]


# ---------------------------------------------------------------------------
# Section saves
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_contact_section_saves_normalized_values_through_inertia_json(client):
    user = agent()
    client.force_login(user)

    response = save(client, "contact", CONTACT, json_body=True)
    assert response.status_code == 302
    assert response.url == f"{reverse('onboarding')}?section=credentials"
    user.refresh_from_db()
    assert user.phone_number == "(202) 555-0100"
    assert user.preferred_contact_method == "text"
    assert (user.street_address, user.city, user.state, user.zip_code) == (
        "1 Main St",
        "Fairfax",
        "VA",
        "22030",
    )
    assert user.profile_completed is False


@pytest.mark.django_db
@pytest.mark.parametrize("json_body", [False, True])
def test_credentials_section_uses_the_profile_normalizers(client, json_body):
    user = agent()
    client.force_login(user)

    assert (
        save(client, "credentials", credentials(), json_body=json_body).status_code
        == 302
    )
    user.refresh_from_db()
    assert user.office == assignable_office()
    assert user.license_number == "VA-99 11"
    assert user.nrds_number == "123456789"
    assert user.mls_number == ""
    assert user.website_url == "https://bobsells.example.com"
    assert user.linkedin_url == "https://linkedin.com/in/bob"
    assert user.languages == ["en", "es"]
    assert user.bio == "Hello\n\nthere"


@pytest.mark.django_db
def test_credentials_requires_confirmation_for_the_exact_selected_office(client):
    user = agent(street_address="Agent home address")
    client.force_login(user)
    selected = assignable_office()
    response = save(
        client,
        "credentials",
        credentials(confirm_office="false", confirmed_office_id=str(selected.pk)),
    )

    assert response.status_code == 422
    assert page(response)["validation"]["fields"]["confirm_office"]
    user.refresh_from_db()
    assert user.office is None
    assert user.street_address == "Agent home address"


@pytest.mark.django_db
def test_changing_office_invalidates_confirmation_without_overwriting_home_address(
    client,
):
    user = agent(street_address="99 Private Home Lane")
    client.force_login(user)
    first = assignable_office()
    second = Office.assignable_queryset().exclude(pk=first.pk).first()
    assert second is not None
    assert save(client, "credentials", credentials()).status_code == 302

    response = save(
        client,
        "credentials",
        credentials(
            office=str(second.pk),
            confirm_office="true",
            confirmed_office_id=str(first.pk),
        ),
    )

    assert response.status_code == 422
    user.refresh_from_db()
    assert user.office == first
    assert user.street_address == "99 Private Home Lane"
    case = UserOnboardingCase.objects.get(user=user)
    assert case.office_confirmed_for == first
    assert user.license_expires_on is not None
    assert user.license_expires_on.isoformat() == "2030-06-30"


@pytest.mark.django_db
def test_invalid_section_returns_validation_shape_and_keeps_typed_values(client):
    user = agent()
    client.force_login(user)

    response = save(
        client,
        "credentials",
        credentials(
            nrds_number="12",
            linkedin_url="https://evil.example.com/bob",
            license_number="",
            languages=["en", "xx"],
            office="999999",
        ),
    )
    assert response.status_code == 422
    body = json.loads(response.content)
    assert body["component"] == "Onboarding"
    validation = body["props"]["validation"]
    assert set(validation) == {"fields", "form"}
    assert {
        "nrds_number",
        "linkedin_url",
        "license_number",
        "languages",
        "office",
    } <= set(validation["fields"])
    assert body["props"]["profileFlow"]["currentSection"] == "credentials"
    assert body["props"]["initial"]["nrdsNumber"] == "12"
    assert body["props"]["initial"]["linkedinUrl"] == "https://evil.example.com/bob"
    user.refresh_from_db()
    assert user.nrds_number == ""
    assert user.office is None


@pytest.mark.django_db
@pytest.mark.parametrize("office", ["region", "inactive", "unknown"])
def test_office_must_be_an_active_assignable_office(client, office):
    client.force_login(agent())
    if office == "region":
        value = str(Office.objects.get(slug="region-mid-atlantic").pk)
    elif office == "inactive":
        chosen = assignable_office()
        chosen.is_active = False
        chosen.save()
        value = str(chosen.pk)
    else:
        value = "999999"

    response = save(client, "credentials", credentials(office=value))
    assert response.status_code == 422
    assert "office" in page(response)["validation"]["fields"]


@pytest.mark.django_db
def test_required_contact_facts_are_enforced_server_side(client):
    user = agent()
    client.force_login(user)

    response = save(client, "contact", {**CONTACT, "phone_number": "", "zip_code": ""})
    assert response.status_code == 422
    assert {"phone_number", "zip_code"} <= set(page(response)["validation"]["fields"])
    user.refresh_from_db()
    assert user.street_address == ""


@pytest.mark.django_db
@pytest.mark.parametrize("section", ["review", "finalize", "unknown"])
def test_only_editable_sections_accept_values(client, section):
    client.force_login(agent())
    response = client.post(
        reverse("onboarding_profile_save", args=[section]), CONTACT, **INERTIA
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_completed_user_is_sent_to_the_dashboard_without_writing(client):
    user = User.objects.create_user(email="done@example.com", profile_completed=True)
    client.force_login(user)
    response = client.post(
        reverse("onboarding_profile_save", args=["contact"]),
        {**CONTACT, "revision": "x", "expected_onboarding_version": "0"},
    )
    assert response.status_code == 302
    assert response.url == reverse("dashboard")
    user.refresh_from_db()
    assert user.phone_number == ""


# ---------------------------------------------------------------------------
# Security and concurrency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_crafted_user_identifiers_are_ignored_and_only_the_session_user_changes(
    client,
):
    other = User.objects.create_user(email="other@example.com")
    user = agent()
    client.force_login(user)

    crafted = {**CONTACT, "user": str(other.pk), "user_id": str(other.pk)}
    assert save(client, "contact", crafted).status_code == 302

    user.refresh_from_db()
    other.refresh_from_db()
    assert user.phone_number == "(202) 555-0100"
    assert other.phone_number == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field",
    [
        "is_staff",
        "profile_completed",
        "onboarding_version",
        "email",
        "display_name",
        "id",
    ],
)
@pytest.mark.parametrize("endpoint", ["section", "finalize"])
def test_protected_and_identifier_fields_are_rejected_and_audited(
    client, field, endpoint
):
    other = User.objects.create_user(email="other@example.com")
    user = agent()
    client.force_login(user)
    value = str(other.pk) if field == "id" else "1"

    if endpoint == "section":
        response = save(client, "contact", {**CONTACT, field: value})
    else:
        response = client.post(
            reverse("onboarding_profile_finalize"),
            {
                "confirm_review": "true",
                "expected_onboarding_version": "0",
                field: value,
            },
        )

    assert response.status_code == 403
    assert (
        AuditEvent.objects.filter(
            action="security.profile.protected_field_rejected"
        ).count()
        == 1
    )
    user.refresh_from_db()
    other.refresh_from_db()
    assert user.phone_number == ""
    assert user.is_staff is False
    assert user.profile_completed is False
    assert other.phone_number == ""


@pytest.mark.django_db
def test_double_submitted_section_is_saved_once(client):
    client.force_login(agent())
    props = flow(client, "contact")

    first = save(client, "contact", CONTACT, props=props)
    # The same payload again, carrying the revision that is now out of date.
    second = save(client, "contact", CONTACT, props=props)

    assert first.status_code == second.status_code == 302
    assert (
        AuditEvent.objects.filter(
            action="user.onboarding.profile_section_saved"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_stale_tab_cannot_silently_overwrite_a_newer_save(client):
    user = agent()
    client.force_login(user)
    stale = flow(client, "contact")
    assert save(client, "contact", CONTACT).status_code == 302

    changed = {**CONTACT, "phone_number": "703-555-0199"}
    response = save(client, "contact", changed, props=stale)
    assert response.status_code == 409
    props = page(response)
    assert "another tab" in props["validation"]["form"][0]
    assert props["initial"]["phoneNumber"] == "703-555-0199"
    assert revision(props, "contact") != revision(stale, "contact")
    user.refresh_from_db()
    assert user.phone_number == "(202) 555-0100"

    # Saving again from the refreshed page is a deliberate overwrite.
    assert save(client, "contact", changed, props=props).status_code == 302
    user.refresh_from_db()
    assert user.phone_number == "(703) 555-0199"


@pytest.mark.django_db
def test_page_from_an_earlier_onboarding_cycle_cannot_write(client):
    user = agent()
    client.force_login(user)
    props = flow(client, "contact")
    User.objects.filter(pk=user.pk).update(onboarding_version=1)

    response = save(client, "contact", CONTACT, props=props)
    assert response.status_code == 409
    assert page(response)["profileFlow"]["onboardingVersion"] == 1
    user.refresh_from_db()
    assert user.phone_number == ""


@pytest.mark.django_db
def test_write_without_concurrency_tokens_is_refused(client):
    user = agent()
    client.force_login(user)
    response = client.post(
        reverse("onboarding_profile_save", args=["contact"]), CONTACT, **INERTIA
    )
    assert response.status_code == 409
    user.refresh_from_db()
    assert user.phone_number == ""


# ---------------------------------------------------------------------------
# Headshot
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_failed_section_save_never_loses_an_uploaded_headshot(client, media_root):
    user = agent()
    client.force_login(user)
    upload_headshot(client)

    response = save(client, "identity", {"first_name": "", "last_name": "Lee"})
    assert response.status_code == 422
    assert page(response)["initial"]["headshotUrl"]
    user.refresh_from_db()
    assert user.headshot


@pytest.mark.django_db
def test_failed_upload_never_discards_saved_text_fields(client, media_root):
    user = agent()
    client.force_login(user)
    assert save(client, "contact", CONTACT).status_code == 302

    spoofed = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"not really an image")
    spoofed.name = "photo.png"
    response = client.post(reverse("headshot_upload"), {"headshot": spoofed})

    assert response.status_code == 422
    assert json.loads(response.content)["retryable"] is False
    user.refresh_from_db()
    assert user.phone_number == "(202) 555-0100"
    assert not user.headshot


@pytest.mark.django_db
def test_storage_outage_keeps_the_previous_photo_and_is_retryable(
    client, media_root, monkeypatch, caplog
):
    user = agent()
    client.force_login(user)
    upload_headshot(client)
    user.refresh_from_db()
    previous = user.headshot.name

    def unavailable(self, name, content, *args, **kwargs):
        raise OSError(f"disk offline while writing {name}")

    monkeypatch.setattr(FileSystemStorage, "_save", unavailable)
    with caplog.at_level(logging.WARNING):
        response = client.post(
            reverse("headshot_upload"), {"headshot": make_image("JPEG", (300, 300))}
        )

    assert response.status_code == 503
    assert json.loads(response.content)["retryable"] is True
    assert "headshots/" not in response.content.decode()
    assert "headshots/" not in caplog.text
    user.refresh_from_db()
    assert user.headshot.name == previous
    assert (media_root / previous).exists()


@pytest.mark.django_db
def test_replacing_a_photo_retires_the_old_file_only_after_commit(
    client, media_root, django_capture_on_commit_callbacks
):
    user = agent()
    client.force_login(user)
    upload_headshot(client)
    user.refresh_from_db()
    first = user.headshot.name

    with django_capture_on_commit_callbacks(execute=True):
        response = upload_headshot(client)

    user.refresh_from_db()
    assert user.headshot.name != first
    assert not (media_root / first).exists()
    assert (media_root / user.headshot.name).exists()
    url = json.loads(response.content)["url"]
    assert "?v=" in url
    assert "headshots/" not in url


@pytest.mark.django_db
def test_props_and_events_never_carry_storage_paths_or_original_filenames(
    client, media_root
):
    client.force_login(agent())
    upload_headshot(client, name="Vacation Selfie.jpg")

    body = client.get(reverse("onboarding"), **INERTIA).content.decode()
    assert "headshots/" not in body
    assert "Vacation" not in body
    event = AuditEvent.objects.get(action="user.headshot.updated")
    recorded = json.dumps(model_to_dict(event), default=str)
    assert "headshots/" not in recorded
    assert "Vacation" not in recorded


# ---------------------------------------------------------------------------
# Review and finalization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_review_shows_the_normalized_values_that_will_be_saved(client, media_root):
    client.force_login(agent())
    upload_headshot(client)
    fill_sections(client)

    review = flow(client, "review")["profileFlow"]["review"]
    rows = {
        row["field"]: row["display"]
        for group in review["groups"]
        for row in group["rows"]
    }
    assert review["ready"] is True
    assert review["missing"] == []
    assert rows["phone_number"] == "(202) 555-0100"
    assert rows["state"] == "Virginia"
    assert rows["license_number"] == "VA-99 11"
    assert rows["license_expires_on"] == "June 30, 2030"
    assert rows["languages"] == "English, Spanish"
    assert rows["office"] == assignable_office().path_label()
    assert rows["headshot"] == "Photo on file"
    assert rows["mls_number"] == ""


@pytest.mark.django_db
def test_finalize_enforces_every_required_fact_server_side(client, media_root):
    user = agent()
    client.force_login(user)

    response = finalize(client, confirm=False)
    assert response.status_code == 422
    props = page(response)
    assert props["profileFlow"]["currentSection"] == "review"
    assert props["profileFlow"]["review"]["ready"] is False
    assert {
        "headshot",
        "first_name",
        "last_name",
        "phone_number",
        "street_address",
        "city",
        "state",
        "zip_code",
        "office",
        "confirm_review",
    } <= set(props["validation"]["fields"])
    user.refresh_from_db()
    assert user.profile_completed is False
    assert not DomainEvent.objects.filter(name="user.onboarded").exists()


@pytest.mark.django_db
def test_removed_headshot_blocks_finalization(client, media_root):
    client.force_login(agent())
    upload_headshot(client)
    fill_sections(client)
    assert client.post(reverse("headshot_upload"), {"remove": "1"}).status_code == 200

    response = finalize(client)
    assert response.status_code == 422
    assert "headshot" in page(response)["validation"]["fields"]


@pytest.mark.django_db
def test_finalize_requires_the_headshot_to_exist_in_storage(client, media_root):
    user = agent()
    client.force_login(user)
    fill_sections(client)
    User.objects.filter(pk=user.pk).update(headshot="headshots/missing.jpg")

    response = finalize(client)
    assert response.status_code == 422
    assert "could not find" in page(response)["validation"]["fields"]["headshot"][0]


@pytest.mark.django_db
def test_finalize_storage_outage_is_reported_as_retryable_not_missing(
    client, media_root, monkeypatch
):
    user = agent()
    client.force_login(user)
    upload_headshot(client)
    fill_sections(client)
    version = flow(client, "review")["profileFlow"]["onboardingVersion"]

    def unavailable(self, name):
        raise OSError("storage offline")

    monkeypatch.setattr(FileSystemStorage, "exists", unavailable)
    response = finalize(client, version=version)

    assert response.status_code == 503
    assert "unavailable" in page(response)["validation"]["form"][0]
    user.refresh_from_db()
    assert user.profile_completed is False


@pytest.mark.django_db
def test_finalize_rechecks_an_office_retired_while_the_dialog_was_open(
    client, media_root
):
    client.force_login(agent())
    upload_headshot(client)
    fill_sections(client)
    Office.objects.filter(pk=assignable_office().pk).update(is_active=False)

    response = finalize(client)
    assert response.status_code == 422
    assert "office" in page(response)["validation"]["fields"]


@pytest.mark.django_db
def test_finalize_is_atomic_idempotent_and_emits_user_onboarded_once(
    client, media_root
):
    user = agent()
    client.force_login(user)
    complete_profile(client)

    user.refresh_from_db()
    assert user.profile_completed is True
    completed_at = user.profile_completed_at
    assert completed_at is not None
    case = user.onboarding_case  # ty: ignore[unresolved-attribute]
    assert case.required_setup_completed_at is not None
    assert DomainEvent.objects.filter(name="user.onboarded").count() == 1
    assert AuditEvent.objects.filter(action="user.onboarding.completed").count() == 1

    again = client.post(
        reverse("onboarding_profile_finalize"),
        {"confirm_review": "true", "expected_onboarding_version": "0"},
    )
    assert again.status_code == 302
    assert again.url == reverse("dashboard")
    user.refresh_from_db()
    assert user.profile_completed_at == completed_at
    assert DomainEvent.objects.filter(name="user.onboarded").count() == 1
    assert AuditEvent.objects.filter(action="user.onboarding.completed").count() == 1


@pytest.mark.django_db
def test_finalize_accepts_inertia_json(client, media_root):
    user = agent()
    client.force_login(user)
    upload_headshot(client)
    fill_sections(client)

    response = finalize(client, json_body=True)
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.profile_completed is True


@pytest.mark.django_db
def test_reset_user_resumes_with_saved_values_and_must_confirm_again(
    client, media_root
):
    user = agent()
    client.force_login(user)
    complete_profile(client)
    admin = User.objects.create_superuser(email="admin@example.com", password="x")
    reset_required_setup(actor=admin, user=user)

    props = flow(client)
    assert props["profileFlow"]["onboardingVersion"] == 1
    assert props["profileFlow"]["currentSection"] == "credentials"
    assert props["profileFlow"]["review"]["ready"] is False

    assert finalize(client, version=0).status_code == 409
    assert save(client, "credentials", credentials()).status_code == 302
    assert finalize(client).status_code == 302
    user.refresh_from_db()
    assert user.profile_completed is True
    assert DomainEvent.objects.filter(name="user.onboarded").count() == 2


# ---------------------------------------------------------------------------
# Validation coverage for every field the flow collects
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("identity", "first_name", ""),
        ("identity", "last_name", ""),
        ("identity", "preferred_name", "x" * 151),
        ("contact", "phone_number", "123"),
        ("contact", "preferred_contact_method", "carrier-pigeon"),
        ("contact", "street_address", ""),
        ("contact", "city", ""),
        ("contact", "state", "ZZ"),
        ("contact", "zip_code", "2203"),
        ("credentials", "office", "999999"),
        ("credentials", "license_number", "x" * 33),
        ("credentials", "license_state", "ZZ"),
        ("credentials", "license_expires_on", "06/30/2030"),
        ("credentials", "mls_number", "x" * 33),
        ("credentials", "nrds_number", "1234567"),
        ("credentials", "bio", "x" * 1501),
        ("credentials", "languages", ["xx"]),
        ("credentials", "website_url", "ftp://bobsells.example.com"),
        ("credentials", "linkedin_url", "https://example.com/in/bob"),
        ("credentials", "facebook_url", "https://example.com/bob"),
        ("credentials", "instagram_url", "https://example.com/bob"),
        ("credentials", "x_url", "https://example.com/bob"),
    ],
)
def test_every_onboarding_field_rejects_invalid_values_without_writing(
    client, section, field, value
):
    user = agent()
    client.force_login(user)
    base = {"identity": IDENTITY, "contact": CONTACT, "credentials": credentials()}

    response = save(client, section, {**base[section], field: value})

    assert response.status_code == 422
    assert field in page(response)["validation"]["fields"]
    user.refresh_from_db()
    assert user.first_name == ""
    assert user.street_address == ""
    assert user.office is None


@pytest.mark.django_db
def test_social_links_are_normalized_against_their_own_hosts(client):
    user = agent()
    client.force_login(user)

    data = credentials(
        linkedin_url="",
        facebook_url="facebook.com/BobSells",
        instagram_url="www.instagram.com/bobsells",
        x_url="twitter.com/bobsells",
    )
    assert save(client, "credentials", data).status_code == 302

    user.refresh_from_db()
    assert user.linkedin_url == ""
    assert user.facebook_url == "https://facebook.com/BobSells"
    assert user.instagram_url == "https://www.instagram.com/bobsells"
    assert user.x_url == "https://twitter.com/bobsells"
