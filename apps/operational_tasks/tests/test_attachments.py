"""Attachments: who may add one, and who may read one back.

The rule under test is that an attachment's authorization is the *parent
task's*. There is no public URL and no signed link — the download view resolves
the task inside the reader's scope and the file inside
``visible_attachments``, so an internal file is a 404 rather than a 403 for
somebody without the management grant. A 403 would confirm the file exists,
which is the disclosure the internal channel exists to prevent.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.operational_tasks import services
from apps.operational_tasks.models import TaskAttachment
from apps.operational_tasks.services import ActorContext
from apps.operational_tasks.taxonomy import TaskPermission, TaskStatus
from apps.operational_tasks.tests.test_scope import (
    admin_actor,
    assign_role,
    make,
    person,
)


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def upload(name: str = "server.log", body: bytes = b"boom", content_type="text/plain"):
    return SimpleUploadedFile(name, body, content_type=content_type)


def commenter(user) -> ActorContext:
    """Holds the comment grant and nothing wider."""
    return ActorContext(
        user=user, permissions=frozenset({TaskPermission.VIEW, TaskPermission.COMMENT})
    )


def grant(user, *codenames: str) -> None:
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )


@pytest.mark.django_db
def test_an_ordinary_attachment_needs_only_the_comment_grant(seeded):
    admin = person("admin@example.com", "onest-head-office")
    task = make(admin, "onest-head-office", "Laptop will not enrol")

    attachment = services.attach_file(
        actor=commenter(admin), task=task, uploaded=upload()
    )

    assert attachment.internal is False
    assert attachment.byte_size == 4
    # Derived from the name the server accepted, never the header the client
    # claimed: a Content-Type is the uploader's assertion, not a fact.
    assert attachment.media_type == "text/plain"


@pytest.mark.django_db
def test_an_internal_attachment_needs_the_management_grant(seeded):
    admin = person("admin@example.com", "onest-head-office")
    task = make(admin, "onest-head-office", "Laptop will not enrol")

    with pytest.raises(PermissionDenied):
        services.attach_file(
            actor=commenter(admin), task=task, uploaded=upload(), internal=True
        )


@pytest.mark.django_db
def test_a_refused_extension_never_reaches_storage(seeded):
    admin = person("admin@example.com", "onest-head-office")
    task = make(admin, "onest-head-office", "Laptop will not enrol")

    with pytest.raises(ValidationError) as caught:
        services.attach_file(
            actor=admin_actor(admin),
            task=task,
            uploaded=upload("payload.sh", b"#!/bin/sh"),
        )

    assert "file" in caught.value.message_dict
    assert TaskAttachment.objects.filter(task=task).count() == 0


@pytest.mark.django_db
def test_an_oversized_file_is_refused_by_size_not_by_storage(seeded):
    admin = person("admin@example.com", "onest-head-office")
    task = make(admin, "onest-head-office", "Laptop will not enrol")
    oversized = upload("big.txt", b"x" * (services.MAX_ATTACHMENT_BYTES + 1))

    with pytest.raises(ValidationError):
        services.attach_file(actor=admin_actor(admin), task=task, uploaded=oversized)

    assert TaskAttachment.objects.filter(task=task).count() == 0


@pytest.mark.django_db
def test_a_closed_task_takes_no_more_files(seeded):
    admin = person("admin@example.com", "onest-head-office")
    task = make(admin, "onest-head-office", "Laptop will not enrol")
    actor = admin_actor(admin)
    services.transition(actor=actor, task=task, to_status=TaskStatus.IN_PROGRESS)
    services.transition(actor=actor, task=task, to_status=TaskStatus.RESOLVED)
    closed = services.transition(actor=actor, task=task, to_status=TaskStatus.CLOSED)

    with pytest.raises(ValidationError):
        services.attach_file(actor=actor, task=closed, uploaded=upload())


@pytest.mark.django_db
def test_the_per_task_ceiling_holds(seeded):
    admin = person("admin@example.com", "onest-head-office")
    task = make(admin, "onest-head-office", "Laptop will not enrol")
    actor = admin_actor(admin)
    for index in range(services.MAX_ATTACHMENTS_PER_TASK):
        services.attach_file(
            actor=actor, task=task, uploaded=upload(f"log-{index}.log")
        )

    with pytest.raises(ValidationError):
        services.attach_file(
            actor=actor, task=task, uploaded=upload("one-too-many.log")
        )


@pytest.mark.django_db
def test_an_internal_file_is_not_resolvable_without_the_management_grant(seeded):
    admin = person("admin@example.com", "onest-head-office")
    task = make(admin, "onest-head-office", "Laptop will not enrol")
    secret = services.attach_file(
        actor=admin_actor(admin), task=task, uploaded=upload(), internal=True
    )

    # Not "raises 403": the lookup runs inside the visible set, so the file is
    # indistinguishable from one that never existed.
    assert (
        services.load_attachment(
            task=task, actor=commenter(admin), public_id=secret.public_id
        )
        is None
    )
    assert (
        services.load_attachment(
            task=task, actor=admin_actor(admin), public_id=secret.public_id
        )
        == secret
    )


@pytest.mark.django_db
def test_the_download_view_streams_a_visible_file(seeded, client):
    admin = person("admin@example.com", "onest-head-office")
    assign_role(admin, "system_admin", "company")
    grant(
        admin,
        "view_operational_tasks",
        "manage_operational_tasks",
        "comment_operational_tasks",
    )
    task = make(admin, "onest-head-office", "Laptop will not enrol")
    attachment = services.attach_file(
        actor=admin_actor(admin), task=task, uploaded=upload("server.log", b"boom")
    )
    client.force_login(admin)

    response = client.get(
        reverse(
            "operational_task_attachment",
            args=[str(task.public_id), str(attachment.public_id)],
        )
    )

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"boom"
    # Private and never held by a shared cache: the same URL means different
    # things to different readers.
    assert response["Cache-Control"] == "private, max-age=0, no-store"
    assert 'filename="server.log"' in response["Content-Disposition"]


@pytest.mark.django_db
def test_the_download_view_404s_across_a_scope_boundary(seeded, client):
    admin = person("admin@example.com", "onest-head-office")
    assign_role(admin, "system_admin", "company")
    grant(admin, "view_operational_tasks", "manage_operational_tasks")
    task = make(admin, "fairfax-va", "Printer offline")
    attachment = services.attach_file(
        actor=admin_actor(admin), task=task, uploaded=upload()
    )

    outsider = person("outsider@example.com", "onest-head-office")
    grant(outsider, "view_operational_tasks")
    client.force_login(outsider)

    response = client.get(
        reverse(
            "operational_task_attachment",
            args=[str(task.public_id), str(attachment.public_id)],
        )
    )

    # 404 rather than 403: confirming the id exists is itself the disclosure.
    assert response.status_code == 404


@pytest.mark.django_db
def test_an_internal_file_404s_for_a_reader_without_the_grant(seeded, client):
    admin = person("admin@example.com", "onest-head-office")
    assign_role(admin, "system_admin", "company")
    grant(admin, "view_operational_tasks", "manage_operational_tasks")
    task = make(admin, "onest-head-office", "Laptop will not enrol")
    secret = services.attach_file(
        actor=admin_actor(admin), task=task, uploaded=upload(), internal=True
    )

    reporter = person("reporter@example.com", "onest-head-office")
    grant(reporter, "view_operational_tasks")
    services.assign(actor=admin_actor(admin), task=task, assignee=reporter)
    client.force_login(reporter)

    response = client.get(
        reverse(
            "operational_task_attachment",
            args=[str(task.public_id), str(secret.public_id)],
        )
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_the_payload_never_carries_a_url(seeded):
    from apps.operational_tasks.payloads import attachment_payload

    admin = person("admin@example.com", "onest-head-office")
    task = make(admin, "onest-head-office", "Laptop will not enrol")
    attachment = services.attach_file(
        actor=admin_actor(admin), task=task, uploaded=upload()
    )

    payload = attachment_payload(attachment)

    # A serialized storage path would be the permanent link that private
    # storage exists to prevent.
    assert not any(
        isinstance(value, str) and ("http" in value or "/media/" in value)
        for value in payload.values()
    )
    assert "url" not in payload
