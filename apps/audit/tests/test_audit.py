from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test import RequestFactory

from apps.audit.models import AuditEvent
from apps.audit.query import export_audit_events, query_audit_events
from apps.audit.service import (
    AuditActor,
    AuditTarget,
    actor_from_user,
    diff_changes,
    log_event,
    redact,
    target_from_instance,
)
from apps.user.admin import UserAdmin
from apps.user.models import Office, User
from apps.user.roles import BRANCH_MANAGER, role_group_name
from apps.user.tests.test_onboarding import assignable_office
from apps.web.permissions import permission_required


def ok_view(request):
    from django.http import HttpResponse

    return HttpResponse("ok")


@pytest.mark.django_db
def test_redact_hides_sensitive_fields():
    payload = redact(
        {
            "password": "secret",
            "email": "a@example.com",
            "profile": {"phone_number": "2025550100"},
        }
    )
    assert payload["password"] == "[REDACTED]"
    assert payload["email"] == "[REDACTED]"
    assert payload["profile"]["phone_number"] == "[REDACTED]"


@pytest.mark.django_db
def test_diff_changes_only_includes_modified_fields():
    changes = diff_changes({"a": 1, "b": 2}, {"a": 1, "b": 3})
    assert "a" not in changes
    assert changes["b"]["before"] == 2
    assert changes["b"]["after"] == 3


@pytest.mark.django_db
def test_log_event_persists_required_fields():
    office = assignable_office()
    user = User.objects.create_user(email="agent@example.com", office=office)
    event = log_event(
        "user.profile.updated",
        actor=actor_from_user(user),
        target=target_from_instance(user),
        before={"email": user.email},
        after={"email": user.email, "city": "Fairfax"},
        office_id=office.stable_key,
        region_id=office.region.stable_key if office.region else "",
        source="request",
        channel="POST",
    )
    assert event.action == "user.profile.updated"
    assert event.actor_id == str(user.pk)
    assert event.target_type == "user.user"
    assert event.office_id == office.stable_key
    assert event.changes["city"]["after"] == "Fairfax"


@pytest.mark.django_db(transaction=True)
def test_audit_event_rolls_back_with_transaction():
    before = AuditEvent.objects.count()
    user = User.objects.create_user(email="agent@example.com")
    try:
        with transaction.atomic():
            log_event(
                "test.rollback",
                actor=actor_from_user(user),
                target=target_from_instance(user),
            )
            raise RuntimeError("rollback")
    except RuntimeError:
        pass
    assert AuditEvent.objects.count() == before


@pytest.mark.django_db
def test_actor_and_target_history_survive_deletion():
    office = Office.objects.create(
        name="Temporary Office",
        stable_key="temporary-office",
        slug="temporary-office",
        kind=Office.Kind.BRANCH,
        parent=Office.objects.get(slug="ro-pennsylvania"),
    )
    user = User.objects.create_user(email="agent@example.com")
    event = log_event(
        "office.deleted",
        actor=actor_from_user(user),
        target=target_from_instance(office),
        before={"name": office.name},
        after={},
    )
    office.delete()
    stored = AuditEvent.objects.get(pk=event.pk)
    assert stored.target_id == str(event.target_id)
    assert stored.target_snapshot["name"] == "Temporary Office"


@pytest.mark.django_db
def test_query_audit_events_scopes_branch_manager_to_office():
    office = assignable_office()
    other_office = Office.objects.get(slug="fairfax-va")
    manager = User.objects.create_user(email="manager@example.com", office=office)
    manager.groups.add(
        Group.objects.get_or_create(name=role_group_name(BRANCH_MANAGER))[0]
    )
    manager.user_permissions.add(
        Permission.objects.get(codename="can_view_audit_events")
    )
    own = log_event(
        "office.local",
        actor=actor_from_user(manager),
        target=AuditTarget(target_type="office", target_id=office.stable_key),
        office_id=office.stable_key,
    )
    log_event(
        "office.other",
        actor=actor_from_user(manager),
        target=AuditTarget(target_type="office", target_id=other_office.stable_key),
        office_id=other_office.stable_key,
    )
    events = list(query_audit_events(manager))
    assert [event.id for event in events] == [own.id]


@pytest.mark.django_db
def test_export_audit_events_requires_permission():
    user = User.objects.create_user(email="agent@example.com")
    with pytest.raises(PermissionDenied):
        export_audit_events(user)


@pytest.mark.django_db
def test_permission_denial_writes_audit_event(rf):
    user = User.objects.create_user(email="agent@example.com", profile_completed=True)
    request = rf.get("/protected")
    request.user = user
    wrapped = permission_required(all_permissions=["user.view_user"])(ok_view)

    with pytest.raises(PermissionDenied):
        wrapped(request)
    event = AuditEvent.objects.get(action="security.permission.denied")
    assert event.outcome == AuditEvent.Outcome.DENIED
    assert event.target_label == "/protected"


@pytest.mark.django_db
def test_onboarding_completion_writes_audit_event(client, settings, tmp_path):
    from apps.user.tests.test_onboarding import make_agent
    from apps.user.tests.test_onboarding_profile import complete_profile

    settings.MEDIA_ROOT = str(tmp_path)
    # Onboarding is the Agent journey; only Agents are given the setup dialog.
    user = make_agent(User.objects.create_user(email="bob@example.com"))
    client.force_login(user)
    complete_profile(client)
    event = AuditEvent.objects.get(action="user.onboarding.completed")
    assert event.actor_id == str(user.pk)
    assert event.outcome == AuditEvent.Outcome.SUCCESS


@pytest.mark.django_db
def test_admin_reset_onboarding_writes_audit_event():
    user = User.objects.create_user(
        email="bob@example.com",
        profile_completed=True,
        office=assignable_office(),
    )
    admin_user = User.objects.create_superuser(email="admin@example.com", password="x")
    request = RequestFactory().get("/")
    request.user = admin_user
    from django.contrib.messages.storage.cookie import CookieStorage

    request._messages = CookieStorage(request)  # ty: ignore[unresolved-attribute]
    admin_instance = UserAdmin(User, None)
    admin_instance.reset_onboarding(request, User.objects.filter(pk=user.pk))
    event = AuditEvent.objects.get(action="user.onboarding.reset")
    assert event.actor_id == str(admin_user.pk)
    assert event.target_id == str(user.pk)


@pytest.mark.django_db
def test_large_strings_are_truncated():
    actor = AuditActor(actor_type=AuditEvent.ActorType.SYSTEM, actor_label="system")
    target = AuditTarget(target_type="test", target_label="target")
    event = log_event(
        "test.large",
        actor=actor,
        target=target,
        metadata={"note": "x" * 2000},
    )
    assert len(event.metadata["note"]) <= 500
