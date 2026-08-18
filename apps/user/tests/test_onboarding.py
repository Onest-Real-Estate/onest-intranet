import json
import re

import pytest
from django.urls import reverse

from apps.user.models import Office, User


def inertia_page_script(response):
    match = re.search(
        rb'<script data-page="app" type="application/json">(.*?)</script>',
        response.content,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def assignable_office():
    return Office.objects.get(slug="charlottesville-va")


def valid_profile_post(**overrides):
    data = {
        "first_name": "Bob",
        "last_name": "Lee",
        "phone_number": "2025550100",
        "street_address": "1 Main St",
        "city": "Fairfax",
        "state": "VA",
        "zip_code": "22030",
        "office": str(assignable_office().pk),
        "mls_number": "",
        "nrds_number": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_onboarding_requires_login(client):
    response = client.get(reverse("onboarding"))
    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next=/onboarding"


@pytest.mark.django_db
def test_onboarding_renders_page_with_initial_values(client):
    user = User.objects.create_user(
        email="bob@example.com",
        first_name="Bob",
        last_name="Lee",
        phone_number="(202) 555-0100",
    )
    client.force_login(user)
    response = client.get(reverse("onboarding"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["component"] == "Onboarding"
    assert data["props"]["initial"]["firstName"] == "Bob"
    assert data["props"]["initial"]["lastName"] == "Lee"
    assert data["props"]["initial"]["phoneNumber"] == "(202) 555-0100"
    assert data["props"]["errors"] == {}
    group_labels = [group["label"] for group in data["props"]["offices"]]
    assert "Mid-Atlantic" in group_labels
    assert any(state["code"] == "VA" for state in data["props"]["states"])


@pytest.mark.django_db
def test_completed_profile_redirects_from_onboarding(client):
    user = User.objects.create_user(email="bob@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(reverse("onboarding"))
    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_onboarding_submit_saves_details_and_completes(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(reverse("onboarding_submit"), valid_profile_post())
    assert response.status_code == 302
    assert response.url == reverse("dashboard")
    user.refresh_from_db()
    assert user.first_name == "Bob"
    assert user.last_name == "Lee"
    assert user.display_name == "Bob Lee"
    assert user.phone_number == "(202) 555-0100"
    assert user.street_address == "1 Main St"
    assert user.city == "Fairfax"
    assert user.state == "VA"
    assert user.zip_code == "22030"
    assert user.office == assignable_office()
    assert user.mls_number == ""
    assert user.nrds_number == ""
    assert user.profile_completed is True


@pytest.mark.django_db
def test_onboarding_accepts_optional_mls_and_nrds(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    client.post(
        reverse("onboarding_submit"),
        valid_profile_post(mls_number="ABC123", nrds_number="123456789"),
    )
    user.refresh_from_db()
    assert user.mls_number == "ABC123"
    assert user.nrds_number == "123456789"


@pytest.mark.django_db
def test_onboarding_submit_rerenders_with_errors(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(reverse("onboarding_submit"), {"first_name": ""})
    assert response.status_code == 422
    data = inertia_page_script(response)
    assert data["component"] == "Onboarding"
    assert "first_name" in data["props"]["errors"]
    user.refresh_from_db()
    assert user.profile_completed is False


@pytest.mark.django_db
def test_onboarding_submit_rerenders_with_errors_for_inertia(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(
        reverse("onboarding_submit"),
        {"first_name": ""},
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "first_name" in data["props"]["errors"]
    assert data["props"]["initial"]["firstName"] == ""


@pytest.mark.django_db
def test_onboarding_rejects_invalid_us_phone(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(
        reverse("onboarding_submit"),
        valid_profile_post(phone_number="123"),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "phone_number" in data["props"]["errors"]


@pytest.mark.django_db
def test_onboarding_rejects_region_as_office(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    region = Office.objects.get(slug="region-mid-atlantic")
    response = client.post(
        reverse("onboarding_submit"),
        valid_profile_post(office=str(region.pk)),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "office" in data["props"]["errors"]


# --- ProfileCompletionMiddleware gate ---------------------------------------


@pytest.mark.django_db
def test_incomplete_profile_redirected_to_onboarding(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert response.url == reverse("onboarding")


@pytest.mark.django_db
def test_incomplete_profile_cannot_open_profile_page(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.get(reverse("profile"))
    assert response.status_code == 302
    assert response.url == reverse("onboarding")


@pytest.mark.django_db
def test_complete_profile_not_redirected(client):
    user = User.objects.create_user(email="bob@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_anonymous_not_redirected_to_onboarding(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next=/dashboard"


@pytest.mark.django_db
def test_staff_not_redirected_to_onboarding(client):
    user = User.objects.create_user(email="admin@example.com", is_staff=True)
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_logout_not_blocked_by_middleware(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert response.url == reverse("login")
