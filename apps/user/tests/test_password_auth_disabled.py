"""Deployed auth is Microsoft-only: allauth password views must stay closed."""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import NoReverseMatch, reverse

from apps.user.models import User

SIGNUP_PATH = "/accounts/signup/"


@pytest.mark.django_db
def test_signup_is_not_reachable(client):
    with pytest.raises(NoReverseMatch):
        reverse("account_signup")

    get_response = client.get(SIGNUP_PATH)
    assert get_response.status_code == 404

    before = User.objects.count()
    post_response = client.post(
        SIGNUP_PATH,
        {
            "email": "intruder@example.com",
            "password1": "not-a-real-password",
            "password2": "not-a-real-password",
        },
    )
    assert post_response.status_code == 404
    assert User.objects.count() == before
    assert not User.objects.filter(email="intruder@example.com").exists()


@pytest.mark.django_db
def test_password_login_does_not_authenticate(client):
    User.objects.create_user(
        email="alice@example.com",
        password="not-a-real-password",
        profile_completed=True,
    )

    response = client.post(
        reverse("account_login"),
        {"login": "alice@example.com", "password": "not-a-real-password"},
    )
    assert response.status_code == 302
    assert urlsplit(response.url).path == reverse("login")
    assert "_auth_user_id" not in client.session


def test_microsoft_login_still_resolves():
    assert reverse("microsoft_login") == "/accounts/microsoft/login/"


def test_accounts_login_get_redirects_to_hub_login(client):
    response = client.get(reverse("account_login"), {"next": "/dashboard"})
    assert response.status_code == 302
    parsed = urlsplit(response.url)
    assert parsed.path == reverse("login")
    assert parse_qs(parsed.query) == {"next": ["/dashboard"]}
