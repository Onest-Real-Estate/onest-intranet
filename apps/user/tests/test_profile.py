import json

import pytest
from django.urls import reverse

from apps.user.models import User
from apps.user.tests.test_onboarding import assignable_office, valid_profile_post


@pytest.mark.django_db
def test_profile_requires_login(client):
    response = client.get(reverse("profile"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_profile_renders_for_completed_user(client):
    user = User.objects.create_user(
        email="bob@example.com",
        first_name="Bob",
        last_name="Lee",
        profile_completed=True,
        office=assignable_office(),
    )
    client.force_login(user)
    response = client.get(reverse("profile"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["component"] == "Profile"
    assert data["props"]["initial"]["firstName"] == "Bob"
    assert data["props"]["initial"]["officeId"] == str(assignable_office().pk)


@pytest.mark.django_db
def test_profile_submit_updates_optional_licenses(client):
    user = User.objects.create_user(
        email="bob@example.com",
        profile_completed=True,
        first_name="Bob",
        last_name="Lee",
        office=assignable_office(),
    )
    client.force_login(user)
    response = client.post(
        reverse("profile_submit"),
        valid_profile_post(mls_number="MLS-99", nrds_number="987654321"),
    )
    assert response.status_code == 302
    assert response.url == reverse("profile")
    user.refresh_from_db()
    assert user.mls_number == "MLS-99"
    assert user.nrds_number == "987654321"
    assert user.profile_completed is True


@pytest.mark.django_db
def test_profile_submit_rerenders_errors(client):
    user = User.objects.create_user(email="bob@example.com", profile_completed=True)
    client.force_login(user)
    response = client.post(
        reverse("profile_submit"),
        valid_profile_post(zip_code="nope"),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert data["component"] == "Profile"
    assert "zip_code" in data["props"]["validation"]["fields"]
