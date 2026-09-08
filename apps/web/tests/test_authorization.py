import json

import pytest
from django.test import override_settings
from django.urls import get_resolver, reverse

from apps.user.models import User
from apps.web.authorization import (
    NON_ROUTE_SURFACES,
    get_authorization_policy,
    inventory_rows,
)


def _iter_patterns(patterns):
    for pattern in patterns:
        nested = getattr(pattern, "url_patterns", None)
        if nested is not None:
            yield from _iter_patterns(nested)
            continue
        yield pattern


def test_authorization_inventory_includes_non_route_surfaces():
    rows = inventory_rows()
    keys = {row["key"] for row in rows}
    assert "admin_prefix" in keys
    assert "allauth_accounts_prefix" in keys
    assert "audit_task_replay_event" in keys
    assert any(item.surface_type == "admin_action" for item in NON_ROUTE_SURFACES)


def test_local_routes_have_explicit_authorization_policy():
    for pattern in _iter_patterns(get_resolver().url_patterns):
        callback = pattern.callback
        module = getattr(callback, "__module__", "")
        if not module.startswith(("apps.notifications.", "apps.user.", "apps.web.")):
            continue
        assert get_authorization_policy(callback) is not None, (
            f"{module}.{callback.__name__} is missing an authorization policy"
        )


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="apps.web.tests.unclassified_urlconf")
def test_unclassified_route_is_denied(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get("/unclassified", HTTP_X_INERTIA="true")
    assert response.status_code == 403


@pytest.mark.django_db
def test_permission_denied_page_includes_request_id(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(
        reverse("dashboard"),
        HTTP_X_INERTIA="true",
        HTTP_X_REQUEST_ID="req-123",
    )
    assert response.status_code == 200
    assert response["X-Request-ID"] == "req-123"
    payload = json.loads(response.content)
    assert payload["props"]["requestId"] == "req-123"


@pytest.mark.django_db
def test_not_found_handler_renders_inertia_page(client):
    user = User.objects.create_user(email="alice@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get("/missing-route", HTTP_X_INERTIA="true")
    assert response.status_code == 404
    payload = json.loads(response.content)
    assert payload["component"] == "NotFound"


@pytest.mark.django_db
def test_office_scope_helper_returns_everything_for_company_wide_access():
    """Company-wide access builds an empty ``Q``, which is falsy.

    Reading that as "no scope" handed a brokerage-wide admin an empty queryset;
    only ``is_superuser`` escaped it.
    """
    from apps.user.models import Office
    from apps.user.roles import ADMIN, ScopeType
    from apps.user.services.role_assignments import create_role_assignment
    from apps.web.authorization import scope_queryset_for_user_office

    root = User.objects.create_superuser(email="root@example.com")
    admin = User.objects.create_user(email="brokerage@example.com")
    create_role_assignment(
        actor=root,
        target_user=admin,
        role=ADMIN,
        scope_type=ScopeType.COMPANY,
    )
    office = Office.assignable_queryset().filter(kind=Office.Kind.BRANCH).first()
    assert office is not None
    User.objects.create_user(email="somebody@example.com", office=office)

    scoped = scope_queryset_for_user_office(
        admin, User.objects.all(), field_name="office"
    )
    assert scoped.count() == User.objects.count()
