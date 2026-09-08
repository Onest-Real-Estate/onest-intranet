"""The HTTP surface: that the route serves this module rather than a stub."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission
from django.urls import resolve, reverse
from django.utils import timezone

from apps.operational_tasks import views
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


def _writer(email: str = "writer@example.com"):
    """A reader who also holds every write grant in the family."""
    staff = person(email, "onest-head-office")
    assign_role(staff, "system_admin", "company")
    for codename in (
        "view_operational_tasks",
        "manage_operational_tasks",
        "assign_operational_tasks",
        "comment_operational_tasks",
    ):
        staff.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return staff


def test_the_create_form_only_offers_offices_the_actor_may_file_against(seeded, client):
    from apps.user.models import Office

    manager = person("branch@example.com", "fairfax-va")
    assign_role(
        manager, "branch_manager", "office", Office.objects.get(slug="fairfax-va")
    )
    manager.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web", codename="view_operational_tasks"
        )
    )
    manager.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web", codename="manage_operational_tasks"
        )
    )
    client.force_login(manager)

    props = json.loads(
        client.get(reverse("operational_tasks"), HTTP_X_INERTIA="true").content
    )["props"]

    # Scoped before serialization: the picker is not a back door into the org
    # chart for somebody whose reach is one branch.
    assert [office["name"] for office in props["offices"]] == ["Fairfax VA"]


def test_a_reader_without_the_manage_grant_is_offered_no_offices(seeded, client):
    client.force_login(_reader())

    props = json.loads(
        client.get(reverse("operational_tasks"), HTTP_X_INERTIA="true").content
    )["props"]

    assert props["can"]["manage"] is False
    assert props["offices"] == []


def test_creating_a_task_records_the_due_date_and_tags(seeded, client):
    from apps.operational_tasks.models import OperationalTask
    from apps.user.models import Office

    writer = _writer()
    client.force_login(writer)

    response = client.post(
        reverse("operational_task_create"),
        {
            "office": Office.objects.get(slug="fairfax-va").pk,
            "category": "tool_setup",
            "title": "Set up the new CRM seat",
            "priority": "high",
            "dueAt": "2026-09-30",
            "tags": "crm, licence, crm",
        },
    )

    assert response.status_code == 302
    task = OperationalTask.objects.get(title="Set up the new CRM seat")
    assert task.due_at is not None
    local = timezone.localtime(task.due_at)
    assert local.date().isoformat() == "2026-09-30"
    # End of the working day, not midnight: a bare date parsed to 00:00 would
    # make a task due today overdue from the moment it was created.
    assert local.hour == views.END_OF_DAY_HOUR
    # Deduplicated, order preserved. Tags are free text and authorize nothing.
    assert task.tags == ["crm", "licence"]


def test_an_unparseable_due_date_is_a_field_error_not_a_silent_drop(seeded, client):
    from apps.user.models import Office

    client.force_login(_writer())

    response = client.post(
        reverse("operational_task_create"),
        {
            "office": Office.objects.get(slug="fairfax-va").pk,
            "category": "tool_setup",
            "title": "Set up the new CRM seat",
            "priority": "normal",
            "dueAt": "next tuesday",
        },
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    assert "dueAt" in json.loads(response.content)["props"]["errors"]["fields"]


def test_assigning_to_somebody_outside_the_picker_is_refused(seeded, client):
    from apps.operational_tasks.tests.test_scope import make

    writer = _writer()
    task = make(writer, "onest-head-office", "Needs an owner")
    # Holds no task grant at all, so they are not in the scoped candidate set.
    outsider = person("outsider@example.com", "fairfax-va")
    client.force_login(writer)

    response = client.post(
        reverse("operational_task_assign", args=[str(task.public_id)]),
        {"assignee": str(outsider.pk)},
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    task.refresh_from_db()
    assert task.assignee_id is None


def test_a_stale_assignment_loses_the_race_rather_than_overwriting(seeded, client):
    from apps.operational_tasks import services
    from apps.operational_tasks.tests.test_scope import admin_actor, make

    writer = _writer()
    other = _writer("other@example.com")
    task = make(writer, "onest-head-office", "Contested")
    services.assign(actor=admin_actor(writer), task=task, assignee=other)
    client.force_login(writer)

    # The caller still believes it is unassigned.
    response = client.post(
        reverse("operational_task_assign", args=[str(task.public_id)]),
        {"assignee": str(writer.pk), "expectedAssignee": ""},
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 409
    task.refresh_from_db()
    assert task.assignee_id == other.pk


def test_uploading_an_attachment_lands_on_the_task(seeded, client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.operational_tasks.models import TaskAttachment
    from apps.operational_tasks.tests.test_scope import make

    writer = _writer()
    task = make(writer, "onest-head-office", "Has evidence")
    client.force_login(writer)

    response = client.post(
        reverse("operational_task_attach", args=[str(task.public_id)]),
        {"file": SimpleUploadedFile("server.log", b"boom", content_type="text/plain")},
    )

    assert response.status_code == 302
    assert TaskAttachment.objects.filter(task=task, display_name="server.log").exists()


def test_a_refused_upload_re_renders_the_detail_page_with_the_error(seeded, client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.operational_tasks.tests.test_scope import make

    writer = _writer()
    task = make(writer, "onest-head-office", "Has evidence")
    client.force_login(writer)

    response = client.post(
        reverse("operational_task_attach", args=[str(task.public_id)]),
        {"file": SimpleUploadedFile("payload.sh", b"#!/bin/sh")},
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    body = json.loads(response.content)
    assert body["component"] == "OperationalTaskDetail"
    assert "file" in body["props"]["errors"]["fields"]


def test_every_write_works_when_posted_the_way_the_browser_posts_it(seeded, client):
    """The regression this module's whole write surface depends on.

    Inertia sends `application/json`, not a form encoding. Django parses
    `request.POST` only for form and multipart bodies, so before
    `InertiaJsonPostMiddleware` every one of these returned 422 with an empty
    field — and the rest of this file passed anyway, because the test client
    posts form-encoded by default. Posting JSON here is the point.
    """
    from apps.operational_tasks.models import OperationalTask, TaskComment
    from apps.operational_tasks.tests.test_scope import make

    writer = _writer()
    task = make(writer, "onest-head-office", "Browser-shaped writes")
    client.force_login(writer)

    def post_json(route_name, payload):
        return client.post(
            reverse(route_name, args=[str(task.public_id)]),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_INERTIA="true",
        )

    assert (
        post_json(
            "operational_task_transition",
            {"status": "in_progress", "expectedStatus": "open", "note": ""},
        ).status_code
        == 302
    )
    task.refresh_from_db()
    assert task.status == "in_progress"

    assert (
        post_json("operational_task_assign", {"assignee": str(writer.pk)}).status_code
        == 302
    )
    task.refresh_from_db()
    assert task.assignee_id == writer.pk

    # `internal` rides as a JSON boolean, and the view tests it against "1".
    assert (
        post_json(
            "operational_task_comment", {"body": "Posted as JSON", "internal": True}
        ).status_code
        == 302
    )
    comment = TaskComment.objects.get(task=task)
    assert comment.body == "Posted as JSON"
    assert comment.internal is True

    assert OperationalTask.objects.filter(pk=task.pk).exists()


def test_a_stale_json_transition_still_loses_the_race(seeded, client):
    """Concurrency must not depend on the encoding either."""
    from apps.operational_tasks import services
    from apps.operational_tasks.tests.test_scope import admin_actor, make

    writer = _writer()
    task = make(writer, "onest-head-office", "Contested")
    services.transition(actor=admin_actor(writer), task=task, to_status="in_progress")
    client.force_login(writer)

    response = client.post(
        reverse("operational_task_transition", args=[str(task.public_id)]),
        data=json.dumps({"status": "resolved", "expectedStatus": "open"}),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 409
