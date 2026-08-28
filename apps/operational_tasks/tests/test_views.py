"""The HTTP surface: that the route serves this module rather than a stub."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission
from django.urls import resolve, reverse

from apps.operational_tasks.tests.test_scope import assign_role, person


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def _reader(email: str = "staff@example.com"):
    staff = person(email, "onest-head-office")
    assign_role(staff, "system_admin", "company")
    staff.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web", codename="view_operational_tasks"
        )
    )
    return staff


def test_the_queue_renders_its_own_component(seeded, client):
    """Not just a 200.

    ``apps.web.urls`` builds a Coming Soon route for every operations
    destination and that placeholder answers 200 too, so a status-only
    assertion would pass while the reader saw "not enabled yet".
    """
    client.force_login(_reader())

    response = client.get(reverse("operational_tasks"), HTTP_X_INERTIA="true")

    assert response.status_code == 200
    assert json.loads(response.content)["component"] == "OperationalTasks"


def test_the_route_is_not_shadowed_by_the_registry_placeholder(seeded):
    from apps.web.views import coming_soon

    assert resolve(reverse("operational_tasks")).func is not coming_soon


def test_the_board_layout_is_grouped_by_the_server(seeded, client):
    client.force_login(_reader())

    response = client.get(
        f"{reverse('operational_tasks')}?view=board", HTTP_X_INERTIA="true"
    )
    props = json.loads(response.content)["props"]

    assert props["view"] == "board"
    # Fixed lifecycle columns, including the empty ones: the board's shape is
    # the lifecycle's, never the data's.
    assert [column["status"]["code"] for column in props["board"]] == [
        "open",
        "in_progress",
        "blocked",
        "waiting",
        "resolved",
    ]


def test_the_queue_refuses_a_reader_without_the_grant(seeded, client):
    client.force_login(person("agent@example.com", "fairfax-va"))
    response = client.get(reverse("operational_tasks"))
    assert response.status_code in {302, 403}
