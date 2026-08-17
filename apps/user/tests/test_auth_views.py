import json

import pytest
from django.urls import reverse

from apps.user.models import User


@pytest.mark.django_db
def test_login_redirects_when_authenticated(client):
    user = User.objects.create_user(email="alice@example.com")
    client.force_login(user)
    response = client.get(reverse("login"))
    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_logout_clears_session_and_history(client):
    user = User.objects.create_user(email="alice@example.com")
    client.force_login(user)
    response = client.post(reverse("logout"), HTTP_X_INERTIA="true")
    assert response.status_code == 302
    assert response.url == reverse("home")
    # The next Inertia page tells the client to clear browser history.
    # (Don't follow the redirect - that would consume the one-shot
    # clearHistory flag first.)
    response = client.get(reverse("home"), HTTP_X_INERTIA="true")
    data = json.loads(response.content)
    assert data["clearHistory"] is True
    assert data["props"]["user"] is None
