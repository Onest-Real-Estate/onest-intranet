"""Self-service profile: authorization, validation, persistence, and audit."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import ADMIN, AGENT, BRANCH_MANAGER, ScopeType
from apps.user.tests.test_onboarding import (
    assignable_office,
    make_image,
    valid_profile_post,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def other_office() -> Office:
    return Office.objects.get(slug="fairfax-va")


def completed_user(**overrides) -> User:
    defaults = {
        "email": "bob@example.com",
        "first_name": "Bob",
        "last_name": "Lee",
        "phone_number": "(202) 555-0100",
        "street_address": "1 Main St",
        "city": "Fairfax",
        "state": "VA",
        "zip_code": "22030",
        "profile_completed": True,
        "office": assignable_office(),
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def valid_self_profile_post(**overrides):
    """Every self-editable field, filled with values that should round-trip."""
    data = valid_profile_post()
    data.update(
        {
            "preferred_name": "Bobby",
            "preferred_contact_method": "text",
            "license_number": "va-9911",
            "license_state": "VA",
            "license_expires_on": "2030-06-30",
            "bio": "Serving Northern Virginia since 2015.",
            "languages": ["es", "en"],
            "website_url": "bobsells.example.com",
            "linkedin_url": "https://www.linkedin.com/in/bob",
            "facebook_url": "",
            "instagram_url": "",
            "x_url": "",
        }
    )
    data.update(overrides)
    return data


def props(response) -> dict:
    return json.loads(response.content)["props"]


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_profile_requires_login(client):
    response = client.get(reverse("profile"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_profile_renders_full_self_service_payload(client):
    user = completed_user(
        preferred_name="Bobby",
        license_number="VA-9911",
        license_state="VA",
        languages=["en", "es"],
        website_url="https://bobsells.example.com",
    )
    client.force_login(user)
    response = client.get(reverse("profile"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["component"] == "Profile"
    page = data["props"]

    assert page["initial"]["firstName"] == "Bob"
    assert page["initial"]["preferredName"] == "Bobby"
    assert page["initial"]["licenseNumber"] == "VA-9911"
    assert page["initial"]["languages"] == ["en", "es"]
    assert page["initial"]["officeId"] == str(assignable_office().pk)

    assert page["identity"]["email"] == "bob@example.com"
    assert page["identity"]["office"]["name"] == assignable_office().name
    assert page["identity"]["accountStatus"] == "active"
    assert page["editable"]["office"] is True
    assert 0 <= page["completeness"]["percent"] <= 100
    assert any(option["code"] == "es" for option in page["languageOptions"])
    assert [item["value"] for item in page["contactMethods"]] == [
        "email",
        "phone",
        "text",
    ]
    assert [item["name"] for item in page["socialPlatforms"]] == [
        "linkedin_url",
        "facebook_url",
        "instagram_url",
        "x_url",
    ]
    assert page["limits"]["bioMaxLength"] > 0


@pytest.mark.django_db
def test_profile_never_exposes_another_users_record(client):
    completed_user(email="alice@example.com", first_name="Alice")
    bob = completed_user(email="bob@example.com")
    client.force_login(bob)
    # A user identifier in the query string changes nothing: the view only ever
    # reads request.user.
    response = client.get(f"{reverse('profile')}?user=1&id=1", HTTP_X_INERTIA="true")
    assert response.status_code == 200
    assert props(response)["identity"]["email"] == "bob@example.com"


# ---------------------------------------------------------------------------
# POST — persistence and normalization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_profile_submit_saves_every_self_editable_field(client):
    user = completed_user()
    client.force_login(user)
    response = client.post(reverse("profile_submit"), valid_self_profile_post())
    assert response.status_code == 302
    assert response.url == reverse("profile")

    user.refresh_from_db()
    assert user.preferred_name == "Bobby"
    assert user.preferred_contact_method == "text"
    assert user.license_number == "VA-9911"
    assert user.license_state == "VA"
    assert user.license_expires_on == dt.date(2030, 6, 30)
    assert user.bio == "Serving Northern Virginia since 2015."
    assert user.languages == ["en", "es"]
    assert user.website_url == "https://bobsells.example.com"
    assert user.linkedin_url == "https://www.linkedin.com/in/bob"
    assert user.profile_completed is True


@pytest.mark.django_db
def test_reloading_the_page_returns_the_normalized_values(client):
    user = completed_user()
    client.force_login(user)
    client.post(
        reverse("profile_submit"),
        valid_self_profile_post(
            license_number=" va-9911 ",
            website_url="bobsells.example.com",
            languages=["es", "en", "es"],
            phone_number="2025550100",
        ),
    )
    page = props(client.get(reverse("profile"), HTTP_X_INERTIA="true"))
    assert page["initial"]["licenseNumber"] == "VA-9911"
    assert page["initial"]["websiteUrl"] == "https://bobsells.example.com"
    assert page["initial"]["languages"] == ["en", "es"]
    assert page["initial"]["phoneNumber"] == "(202) 555-0100"
    assert page["initial"]["licenseExpiresOn"] == "2030-06-30"


@pytest.mark.django_db
def test_profile_submit_clears_optional_fields_when_emptied(client):
    user = completed_user(
        bio="Old bio", languages=["en"], website_url="https://old.example.com"
    )
    client.force_login(user)
    client.post(
        reverse("profile_submit"),
        valid_self_profile_post(
            bio="",
            languages=[],
            website_url="",
            license_number="",
            license_state="",
            license_expires_on="",
            preferred_contact_method="",
        ),
    )
    user.refresh_from_db()
    assert user.bio == ""
    assert user.languages == []
    assert user.website_url == ""
    assert user.license_expires_on is None


# ---------------------------------------------------------------------------
# POST — validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"zip_code": "nope"}, "zip_code"),
        ({"phone_number": "123"}, "phone_number"),
        ({"nrds_number": "12"}, "nrds_number"),
        ({"website_url": "javascript:alert(1)"}, "website_url"),
        ({"linkedin_url": "https://evil.example/in/bob"}, "linkedin_url"),
        ({"languages": ["klingon"]}, "languages"),
        ({"bio": "a" * 5000}, "bio"),
        ({"license_number": "", "license_state": "VA"}, "license_number"),
        ({"license_expires_on": "not-a-date"}, "license_expires_on"),
        ({"preferred_contact_method": "smoke-signal"}, "preferred_contact_method"),
    ],
)
def test_profile_submit_reports_field_errors(client, payload, field):
    user = completed_user()
    client.force_login(user)
    response = client.post(
        reverse("profile_submit"),
        valid_self_profile_post(**payload),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert data["component"] == "Profile"
    assert field in data["props"]["validation"]["fields"]


@pytest.mark.django_db
def test_invalid_submission_makes_no_partial_update(client):
    user = completed_user(preferred_name="Original")
    client.force_login(user)
    response = client.post(
        reverse("profile_submit"),
        valid_self_profile_post(preferred_name="Changed", zip_code="nope"),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    user.refresh_from_db()
    assert user.preferred_name == "Original"
    assert user.license_number == ""


@pytest.mark.django_db
def test_invalid_submission_preserves_what_was_typed(client):
    user = completed_user()
    client.force_login(user)
    response = client.post(
        reverse("profile_submit"),
        valid_self_profile_post(zip_code="nope", preferred_name="Bobby", bio="Kept"),
        HTTP_X_INERTIA="true",
    )
    page = props(response)
    assert page["initial"]["preferredName"] == "Bobby"
    assert page["initial"]["bio"] == "Kept"
    assert page["initial"]["zipCode"] == "nope"
    assert page["initial"]["languages"] == ["es", "en"]


# ---------------------------------------------------------------------------
# POST — protected fields and cross-user attempts
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field",
    [
        "email",
        "is_staff",
        "is_superuser",
        "is_active",
        "groups",
        "user_permissions",
        "profile_completed",
        "onboarding_version",
        "id",
        "pk",
        "password",
        "display_name",
        "role",
    ],
)
def test_profile_submit_rejects_protected_fields(client, field):
    user = completed_user()
    client.force_login(user)
    post = valid_self_profile_post()
    post[field] = "1"
    response = client.post(reverse("profile_submit"), post)
    assert response.status_code == 403
    user.refresh_from_db()
    assert user.email == "bob@example.com"
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.preferred_name == ""


@pytest.mark.django_db
def test_protected_field_rejection_is_audited_without_values(client):
    user = completed_user()
    client.force_login(user)
    post = valid_self_profile_post()
    post["is_superuser"] = "true"
    client.post(reverse("profile_submit"), post)

    event = AuditEvent.objects.filter(
        action="security.profile.protected_field_rejected"
    ).latest("occurred_at")
    assert event.outcome == AuditEvent.Outcome.DENIED
    assert event.target_snapshot["fields"] == ["is_superuser"]
    assert "true" not in json.dumps(event.target_snapshot)


@pytest.mark.django_db
def test_profile_submit_only_ever_writes_the_signed_in_user(client):
    alice = completed_user(email="alice@example.com", first_name="Alice")
    bob = completed_user(email="bob@example.com")
    client.force_login(bob)
    post = valid_self_profile_post()
    # Crafted ownership hints are simply not part of the form's allowlist.
    post["user"] = str(alice.pk)
    post["user_id"] = str(alice.pk)
    post["instance"] = str(alice.pk)
    response = client.post(reverse("profile_submit"), post)

    assert response.status_code == 302
    alice.refresh_from_db()
    bob.refresh_from_db()
    assert alice.first_name == "Alice"
    assert alice.preferred_name == ""
    assert bob.preferred_name == "Bobby"


# ---------------------------------------------------------------------------
# Office: self-assignable for agents, administrative for everyone else
# ---------------------------------------------------------------------------


def _assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


@pytest.mark.django_db
def test_agent_may_move_their_own_office(client):
    user = completed_user()
    _assign(user, AGENT, ScopeType.OFFICE, assignable_office())
    client.force_login(user)
    response = client.post(
        reverse("profile_submit"),
        valid_self_profile_post(office=str(other_office().pk)),
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.office == other_office()


@pytest.mark.django_db
def test_moving_office_retires_the_stale_agent_assignment(client):
    """The old office-scoped assignment must not linger and widen scope."""
    user = completed_user()
    _assign(user, AGENT, ScopeType.OFFICE, assignable_office())
    client.force_login(user)
    client.post(
        reverse("profile_submit"),
        valid_self_profile_post(office=str(other_office().pk)),
    )

    live = UserRoleAssignment.objects.filter(
        user=user, role=AGENT, status__in=["scheduled", "active"]
    )
    assert [item.scope_office for item in live] == [other_office()]


@pytest.mark.django_db
def test_branch_manager_cannot_move_their_own_office(client):
    user = completed_user()
    _assign(user, BRANCH_MANAGER, ScopeType.OFFICE, assignable_office())
    client.force_login(user)
    response = client.post(
        reverse("profile_submit"),
        valid_self_profile_post(office=str(other_office().pk)),
    )
    assert response.status_code == 403
    user.refresh_from_db()
    assert user.office == assignable_office()


@pytest.mark.django_db
def test_admin_profile_page_marks_office_read_only(client):
    user = completed_user()
    _assign(user, ADMIN, ScopeType.COMPANY)
    client.force_login(user)
    page = props(client.get(reverse("profile"), HTTP_X_INERTIA="true"))
    assert page["editable"]["office"] is False
    assert page["offices"] == []


@pytest.mark.django_db
def test_restricted_user_can_still_save_everything_else(client):
    user = completed_user()
    _assign(user, BRANCH_MANAGER, ScopeType.OFFICE, assignable_office())
    client.force_login(user)
    post = valid_self_profile_post()
    post.pop("office")
    response = client.post(reverse("profile_submit"), post)
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.preferred_name == "Bobby"
    assert user.office == assignable_office()


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_completeness_reports_missing_optional_fields_without_blocking(client):
    user = completed_user()
    client.force_login(user)
    page = props(client.get(reverse("profile"), HTTP_X_INERTIA="true"))
    missing = {item["key"] for item in page["completeness"]["missing"]}
    assert "bio" in missing
    assert "languages" in missing
    assert "office" not in missing
    assert all(item["required"] is False for item in page["completeness"]["missing"])
    assert page["completeness"]["percent"] < 100


@pytest.mark.django_db
def test_completeness_rises_as_fields_are_filled_in(client):
    user = completed_user()
    client.force_login(user)
    before = props(client.get(reverse("profile"), HTTP_X_INERTIA="true"))
    client.post(reverse("profile_submit"), valid_self_profile_post())
    after = props(client.get(reverse("profile"), HTTP_X_INERTIA="true"))
    assert after["completeness"]["percent"] > before["completeness"]["percent"]


# ---------------------------------------------------------------------------
# Headshot
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_headshot_can_be_replaced_from_the_profile_page(client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    user = completed_user()
    client.force_login(user)
    response = client.post(
        reverse("headshot_upload"),
        {"headshot": make_image("PNG", (400, 400))},
        format="multipart",
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert bool(user.headshot) is True


@pytest.mark.django_db
def test_headshot_can_be_removed(client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    user = completed_user()
    client.force_login(user)
    client.post(
        reverse("headshot_upload"),
        {"headshot": make_image("JPEG", (300, 300))},
        format="multipart",
    )
    response = client.post(reverse("headshot_upload"), {"remove": "1"})
    assert response.status_code == 200
    assert json.loads(response.content) == {"url": None}
    user.refresh_from_db()
    assert bool(user.headshot) is False


@pytest.mark.django_db
def test_headshot_removal_is_idempotent(client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    user = completed_user()
    client.force_login(user)
    assert client.post(reverse("headshot_upload"), {"remove": "1"}).status_code == 200


@pytest.mark.django_db
def test_headshot_change_is_audited_without_the_image(client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    user = completed_user()
    client.force_login(user)
    client.post(
        reverse("headshot_upload"),
        {"headshot": make_image("JPEG", (300, 300))},
        format="multipart",
    )
    event = AuditEvent.objects.filter(action="user.headshot.updated").latest(
        "occurred_at"
    )
    assert event.after == {"has_photo": True}
    assert "headshots/" not in json.dumps(event.after)


@pytest.mark.django_db
def test_headshot_upload_rejects_invalid_image_with_a_readable_message(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = str(tmp_path)
    user = completed_user()
    client.force_login(user)
    response = client.post(
        reverse("headshot_upload"),
        {"headshot": make_image("JPEG", (50, 50))},
        format="multipart",
    )
    assert response.status_code == 422
    assert "200" in json.loads(response.content)["error"]
    user.refresh_from_db()
    assert bool(user.headshot) is False


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_profile_update_is_audited_with_before_and_after(client):
    user = completed_user()
    client.force_login(user)
    client.post(reverse("profile_submit"), valid_self_profile_post())

    event = AuditEvent.objects.filter(action="user.profile.updated").latest(
        "occurred_at"
    )
    assert event.actor_id == str(user.pk)
    assert event.changes["preferred_name"] == {"before": "", "after": "Bobby"}
    assert event.changes["license_number"]["after"] == "VA-9911"


@pytest.mark.django_db
def test_profile_audit_does_not_carry_the_home_address(client):
    user = completed_user()
    client.force_login(user)
    client.post(
        reverse("profile_submit"), valid_self_profile_post(street_address="9 Secret Ln")
    )
    event = AuditEvent.objects.filter(action="user.profile.updated").latest(
        "occurred_at"
    )
    serialized = json.dumps([event.before, event.after, event.changes])
    assert "9 Secret Ln" not in serialized


# ---------------------------------------------------------------------------
# Existing users keep their data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_pre_existing_onboarded_user_keeps_data_and_completion():
    """The new columns default to empty and leave earlier records untouched."""
    user = completed_user(mls_number="MLS-1", nrds_number="123456789")
    user.refresh_from_db()
    assert user.profile_completed is True
    assert user.mls_number == "MLS-1"
    assert user.preferred_name == ""
    assert user.languages == []
    assert user.license_expires_on is None
    assert user.bio == ""


@pytest.mark.django_db
def test_saving_the_profile_leaves_onboarding_state_alone(client):
    user = completed_user()
    original_version = user.onboarding_version
    completed_at = user.profile_completed_at
    client.force_login(user)
    client.post(reverse("profile_submit"), valid_self_profile_post())
    user.refresh_from_db()
    assert user.profile_completed is True
    assert user.profile_completed_at == completed_at
    assert user.onboarding_version == original_version


@pytest.mark.django_db
def test_onboarding_ignores_professional_fields(client):
    """Onboarding keeps its own, smaller contract; extras are simply not read."""
    user = User.objects.create_user(email="new@example.com")
    client.force_login(user)
    response = client.post(reverse("onboarding_submit"), valid_self_profile_post())
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.profile_completed is True
    assert user.preferred_name == ""
    assert user.bio == ""


@pytest.mark.django_db
def test_headshot_is_stored_under_a_generated_name(client, settings, tmp_path):
    """The browser-supplied filename must never reach storage."""
    settings.MEDIA_ROOT = str(tmp_path)
    user = completed_user()
    client.force_login(user)
    upload = make_image("PNG", (300, 300))
    upload.name = "../../etc/passwd.png"
    client.post(reverse("headshot_upload"), {"headshot": upload}, format="multipart")

    user.refresh_from_db()
    assert user.headshot.name.startswith("headshots/")
    assert "passwd" not in user.headshot.name
    assert user.headshot.name.endswith(".png")
