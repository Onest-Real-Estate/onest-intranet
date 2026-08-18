import json
import re

import pytest
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import override_settings
from django.urls import reverse

from apps.user.models import User
from apps.web.permissions import PermissionRequiredAuth, permission_required
from apps.web.views import permission_denied


def inertia_page_script(response):
    match = re.search(
        rb'<script data-page="app" type="application/json">(.*?)</script>',
        response.content,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def ok_view(request):
    return HttpResponse("ok")


@pytest.mark.django_db
def test_permission_required_allows_user_with_permission(rf):
    user = User.objects.create_user(email="alice@example.com")
    user.user_permissions.add(Permission.objects.get(codename="view_user"))
    request = rf.get("/")
    request.user = user

    wrapped = permission_required(all_permissions=["user.view_user"])(ok_view)
    assert wrapped(request).status_code == 200


@pytest.mark.django_db
def test_permission_required_denies_user_without_permission(rf):
    user = User.objects.create_user(email="alice@example.com")
    request = rf.get("/")
    request.user = user

    wrapped = permission_required(all_permissions=["user.view_user"])(ok_view)
    with pytest.raises(PermissionDenied):
        wrapped(request)


@pytest.mark.django_db
def test_permission_required_any_grants_with_one_match(rf):
    user = User.objects.create_user(email="alice@example.com")
    user.user_permissions.add(Permission.objects.get(codename="change_user"))
    request = rf.get("/")
    request.user = user

    wrapped = permission_required(
        any_permissions=["user.view_user", "user.change_user"]
    )(ok_view)
    assert wrapped(request).status_code == 200


def test_permission_required_redirects_anonymous_users(rf):
    request = rf.get("/")
    request.user = AnonymousUser()

    wrapped = permission_required(all_permissions=["user.view_user"])(ok_view)
    response = wrapped(request)
    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next=/"


@pytest.mark.django_db
def test_permission_required_auth_allows_user_with_permission(rf):
    user = User.objects.create_user(email="alice@example.com")
    user.user_permissions.add(Permission.objects.get(codename="view_user"))
    request = rf.get("/")
    request.user = user

    auth = PermissionRequiredAuth(all_permissions=["user.view_user"])
    assert auth.authenticate(request, None) == user


@pytest.mark.django_db
def test_permission_required_auth_denies_user_without_permission(rf):
    user = User.objects.create_user(email="alice@example.com")
    request = rf.get("/")
    request.user = user

    auth = PermissionRequiredAuth(all_permissions=["user.view_user"])
    assert auth.authenticate(request, None) is None


def test_permission_required_auth_denies_anonymous(rf):
    request = rf.get("/")
    request.user = AnonymousUser()

    auth = PermissionRequiredAuth(all_permissions=["user.view_user"])
    assert auth.authenticate(request, None) is None


def add_session(request):
    """Attach a session to a RequestFactory request (Inertia reads it)."""
    from django.contrib.sessions.middleware import SessionMiddleware

    middleware = SessionMiddleware(lambda request: HttpResponse())
    middleware.process_request(request)
    request.session.save()
    return request


@pytest.mark.django_db
def test_permission_denied_handler_returns_403_json_for_inertia(rf):
    request = add_session(rf.get("/dashboard", HTTP_X_INERTIA="true"))
    request.user = AnonymousUser()

    response = permission_denied(request)
    assert response.status_code == 403
    data = json.loads(response.content)
    assert data["component"] == "PermissionDenied"


@pytest.mark.django_db
def test_permission_denied_handler_returns_403_html_for_full_load(rf):
    request = add_session(rf.get("/dashboard"))
    request.user = AnonymousUser()

    response = permission_denied(request)
    assert response.status_code == 403
    data = inertia_page_script(response)
    assert data["component"] == "PermissionDenied"


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="apps.web.tests.urlconf")
def test_permission_required_denial_renders_403_page(client):
    # profile_completed=True so ProfileCompletionMiddleware doesn't redirect
    # to /onboarding before the permission check runs.
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)

    response = client.get("/protected", HTTP_X_INERTIA="true")
    assert response.status_code == 403
    data = json.loads(response.content)
    assert data["component"] == "PermissionDenied"
