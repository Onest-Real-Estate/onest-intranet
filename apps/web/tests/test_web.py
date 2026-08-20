import json
import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from apps.user.models import User
from apps.user.roles import AGENT, role_group_name
from apps.user.services.role_assignments import get_effective_access


def inertia_page_script(response):
    match = re.search(
        rb'<script data-page="app" type="application/json">(.*?)</script>',
        response.content,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


@pytest.mark.django_db
def test_root_is_login_page(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    data = inertia_page_script(response)
    assert data["component"] == "Login"


@pytest.mark.django_db
def test_root_inertia_request_returns_json(client):
    response = client.get(reverse("login"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    data = json.loads(response.content)
    assert data["component"] == "Login"
    assert data["props"]["user"] is None
    assert "csrfToken" in data["props"]


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next=/dashboard"


@pytest.mark.django_db
def test_inertia_session_expiry_redirect_is_identifiable(client):
    response = client.get(
        reverse("dashboard"),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.url).query)
    assert query == {"next": ["/dashboard"], "reason": ["session-expired"]}


@pytest.mark.django_db
def test_login_exposes_session_expiry_without_echoing_next_path(client):
    response = client.get(
        reverse("login"),
        {"reason": "session-expired", "next": "/operations/users/42"},
        HTTP_X_INERTIA="true",
    )
    props = json.loads(response.content)["props"]
    assert props["sessionExpired"] is True
    assert "/operations/users/42" not in json.dumps(props)


@pytest.mark.django_db
def test_dashboard_shares_user(client):
    user = User.objects.create_user(
        email="alice@example.com",
        first_name="Alice",
        last_name="Smith",
        profile_completed=True,
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
        "roles": [],
        "roleLabel": "Realtor",
        "isStaff": False,
        "isSuperuser": False,
        "headshotUrl": None,
    }
    assert data["props"]["shell"]["session"] == {"authenticated": True}
    assert data["props"]["shell"]["help"] == {"url": None}
    assert len(data["props"]["shell"]["authorizationVersion"]) == 16


@pytest.mark.django_db
def test_shell_computes_effective_access_once_per_request(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)

    with patch(
        "apps.web.middleware.get_effective_access",
        wraps=get_effective_access,
    ) as effective_access:
        response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")

    assert response.status_code == 200
    assert effective_access.call_count == 1


@pytest.mark.django_db
def test_dashboard_shares_user_permissions(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    user.user_permissions.add(Permission.objects.get(codename="view_user"))
    client.force_login(user)
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    data = json.loads(response.content)
    assert data["props"]["user"]["permissions"] == ["user.view_user"]


@pytest.mark.django_db
def test_dashboard_shares_group_roles_and_permissions(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    group = Group.objects.create(name="Editors")
    group.permissions.add(Permission.objects.get(codename="view_user"))
    user.groups.add(group)
    client.force_login(user)
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    data = json.loads(response.content)
    assert data["props"]["user"]["roles"] == ["Editors"]
    assert data["props"]["user"]["roleLabel"] == "Realtor"
    assert data["props"]["user"]["permissions"] == ["user.view_user"]


@pytest.mark.django_db
def test_dashboard_defers_widget_payloads_on_first_load(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    data = json.loads(response.content)
    assert "metrics" not in data["props"]
    assert "transactions" not in data["props"]
    assert data["deferredProps"]["metrics"] == ["metrics"]
    assert "quickApps" in data["deferredProps"]["pipeline"]
    assert "schedule" in data["deferredProps"]["widgets"]


@pytest.mark.django_db
def test_dashboard_partial_reload_returns_deferred_metrics(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    user.groups.add(Group.objects.get(name=role_group_name(AGENT)))
    client.force_login(user)
    response = client.get(
        reverse("dashboard"),
        HTTP_X_INERTIA="true",
        HTTP_X_INERTIA_PARTIAL_DATA="metrics",
        HTTP_X_INERTIA_PARTIAL_COMPONENT="Dashboard",
    )
    data = json.loads(response.content)
    widget = data["props"]["metrics"]
    assert widget["status"] == "ready"
    assert widget["version"] == 1
    groups = widget["data"]["groups"]
    assert [group["key"] for group in groups] == ["myPipeline", "myWork"]
    assert widget["data"]["scope"]["level"] == "self"


@pytest.mark.django_db
def test_dashboard_partial_reload_returns_transactions(client):
    """The transaction module is not built, so the widget says so plainly."""
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(
        reverse("dashboard"),
        HTTP_X_INERTIA="true",
        HTTP_X_INERTIA_PARTIAL_DATA="transactions",
        HTTP_X_INERTIA_PARTIAL_COMPONENT="Dashboard",
    )
    data = json.loads(response.content)
    widget = data["props"]["transactions"]
    assert widget["status"] == "unavailable"
    assert widget["data"] is None
    assert widget["unavailable"]["retryable"] is False


@pytest.mark.django_db
def test_coming_soon_renders_named_section(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(
        reverse("coming_soon", kwargs={"section": "my-contract"}),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["component"] == "ComingSoon"
    assert data["props"]["title"] == "My contract"


@pytest.mark.django_db
def test_coming_soon_unknown_section_is_404(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(reverse("coming_soon", kwargs={"section": "not-a-section"}))
    assert response.status_code == 404
