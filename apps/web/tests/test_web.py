import json
import re

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.user.models import User


def inertia_page_script(response):
    match = re.search(
        rb'<script data-page="app" type="application/json">(.*?)</script>',
        response.content,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


@pytest.mark.django_db
def test_home_renders_inertia_page(client):
    response = client.get(reverse("home"))
    assert response.status_code == 200
    data = inertia_page_script(response)
    assert data["component"] == "Home"


@pytest.mark.django_db
def test_home_inertia_request_returns_json(client):
    response = client.get(reverse("home"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    data = json.loads(response.content)
    assert data["component"] == "Home"
    assert data["props"]["user"] is None
    assert "csrfToken" in data["props"]


@pytest.mark.django_db
def test_login_redirects_when_authenticated(client):
    user = User.objects.create_user(email="alice@example.com")
    client.force_login(user)
    response = client.get(reverse("login"))
    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next=/dashboard"


@pytest.mark.django_db
def test_dashboard_shares_user(client):
    user = User.objects.create_user(
        email="alice@example.com", first_name="Alice", last_name="Smith"
    )
    client.force_login(user)
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    data = json.loads(response.content)
    assert data["component"] == "Dashboard"
    assert data["props"]["user"] == {
        "id": user.pk,
        "email": "alice@example.com",
        "name": "Alice Smith",
        "permissions": [],
    }


@pytest.mark.django_db
def test_dashboard_shares_user_permissions(client):
    user = User.objects.create_user(email="alice@example.com")
    user.user_permissions.add(Permission.objects.get(codename="view_user"))
    client.force_login(user)
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    data = json.loads(response.content)
    assert data["props"]["user"]["permissions"] == ["user.view_user"]


@pytest.mark.django_db
def test_logout_clears_session_and_history(client):
    user = User.objects.create_user(email="alice@example.com")
    client.force_login(user)
    response = client.post(reverse("logout"), HTTP_X_INERTIA="true")
    assert response.status_code == 302
    assert response.url == reverse("home")
    # The next Inertia page tells the client to clear browser history.
    # (Don't follow the redirect — that would consume the one-shot
    # clearHistory flag first.)
    response = client.get(reverse("home"), HTTP_X_INERTIA="true")
    data = json.loads(response.content)
    assert data["clearHistory"] is True
    assert data["props"]["user"] is None
