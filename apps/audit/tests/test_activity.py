"""Activity timeline projection: mapping, redaction, scope, cursor, dedup."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from apps.audit.activity.access import (
    TIMELINE_PERMISSION,
    assert_can_view_record_activity,
)
from apps.audit.activity.cursor import decode_cursor, encode_cursor
from apps.audit.activity.projection import (
    ActivityProjectionError,
    project_record_activity,
)
from apps.audit.activity.redaction import summarize_changes
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event, system_actor
from apps.user.models import User
from apps.user.tests.test_agent_administration import agent_in, company_admin
from apps.user.tests.test_profile import completed_user


def _grant(user: User, *full_codenames: str) -> None:
    for full in full_codenames:
        app_label, codename = full.split(".", 1)
        permission = Permission.objects.get(
            content_type__app_label=app_label, codename=codename
        )
        user.user_permissions.add(permission)


def _office_keys(user: User) -> tuple[str, str]:
    office = user.office
    if office is None:
        return "", ""
    region = office.region
    return office.stable_key, (region.stable_key if region is not None else "")


def _event(
    *,
    action: str,
    target: User,
    actor: User | None = None,
    changes: dict | None = None,
    occurred_at=None,
    metadata: dict | None = None,
) -> AuditEvent:
    before: dict = {}
    after: dict = {}
    if changes:
        for key, value in changes.items():
            if isinstance(value, dict) and "before" in value and "after" in value:
                before[key] = value["before"]
                after[key] = value["after"]
            else:
                after[key] = value
    return log_event(
        action,
        actor=actor_from_user(actor) if actor else system_actor(),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(target.pk),
            target_label=str(target),
        ),
        before=before,
        after=after,
        office_id=_office_keys(target)[0],
        region_id=_office_keys(target)[1],
        metadata=metadata or {},
        occurred_at=occurred_at,
    )


@pytest.mark.django_db
def test_maps_user_events_chronologically_without_duplicates():
    viewer = company_admin()
    _grant(viewer, TIMELINE_PERMISSION)
    target = agent_in("fairfax-va")
    first = _event(
        action="user.administration.updated",
        target=target,
        actor=viewer,
        occurred_at=timezone.now() - timedelta(hours=2),
    )
    second = _event(
        action="user.account.disabled",
        target=target,
        actor=viewer,
        occurred_at=timezone.now() - timedelta(hours=1),
    )
    page = project_record_activity(viewer, "user", str(target.pk), limit=10)
    ids = [entry.id for entry in page.entries]
    assert ids == [str(second.id), str(first.id)]
    assert len(ids) == len(set(ids))


@pytest.mark.django_db
def test_redaction_hides_sensitive_values_without_field_permission():
    viewer = completed_user(email="limited@example.com")
    labels, safe, visibility = summarize_changes(
        {
            "agent_status": {"before": "active", "after": "leave"},
            "ssn": {"before": "111", "after": "222"},
            "internal_notes": {"before": "a", "after": "b"},
        },
        viewer=viewer,
    )
    assert "ssn" in labels
    assert "internal_notes" in labels
    assert "ssn" not in safe
    assert visibility in {"summary", "redacted"}


@pytest.mark.django_db
def test_direct_api_cannot_reveal_another_records_events(client):
    viewer = company_admin()
    _grant(viewer, TIMELINE_PERMISSION)
    target = agent_in("fairfax-va", email="target@example.com")
    other = agent_in("fairfax-va", email="other@example.com")
    _event(action="user.administration.updated", target=other, actor=viewer)
    client.force_login(viewer)
    response = client.get(
        reverse(
            "activity_timeline",
            kwargs={"record_type": "user", "record_id": target.pk},
        )
    )
    assert response.status_code == 200
    assert response.json()["entries"] == []


@pytest.mark.django_db
def test_out_of_scope_user_is_not_found():
    from apps.user.tests.test_agent_administration import branch_manager

    viewer = branch_manager("fairfax-va")
    _grant(viewer, TIMELINE_PERMISSION)
    stranger = agent_in("charlottesville-va", email="stranger@example.com")
    with pytest.raises(Http404):
        assert_can_view_record_activity(viewer, "user", str(stranger.pk))


@pytest.mark.django_db
def test_timeline_permission_distinct_from_audit_permission():
    from django.contrib.auth.models import Group

    from apps.user.roles import SYSTEM_ADMIN, get_role_definition
    from apps.user.services.role_assignments import has_effective_permission

    viewer = company_admin(email="no-timeline@example.com")
    # Effective permissions resolve through the role's Django group by name,
    # not only through viewer.groups M2M — strip the timeline grant there.
    viewer.user_permissions.filter(codename="can_view_activity_timeline").delete()
    admin_group = Group.objects.get(name=get_role_definition(SYSTEM_ADMIN).group_name)
    admin_group.permissions.filter(codename="can_view_activity_timeline").delete()
    assert not has_effective_permission(viewer, TIMELINE_PERMISSION)
    target = agent_in("fairfax-va")
    with pytest.raises(PermissionDenied):
        project_record_activity(viewer, "user", str(target.pk))


@pytest.mark.django_db
def test_cursor_orders_deterministically_with_tie_break():
    viewer = company_admin()
    _grant(viewer, TIMELINE_PERMISSION)
    target = agent_in("fairfax-va")
    stamp = timezone.now()
    older = _event(
        action="user.administration.updated",
        target=target,
        actor=viewer,
        occurred_at=stamp - timedelta(minutes=5),
    )
    a = _event(
        action="user.license_verification.reset",
        target=target,
        actor=viewer,
        occurred_at=stamp,
    )
    b = _event(
        action="user.account.reactivated",
        target=target,
        actor=viewer,
        occurred_at=stamp,
    )
    first_page = project_record_activity(viewer, "user", str(target.pk), limit=2)
    assert len(first_page.entries) == 2
    assert first_page.has_more is True
    assert first_page.next_cursor
    second_page = project_record_activity(
        viewer,
        "user",
        str(target.pk),
        cursor=first_page.next_cursor,
        limit=2,
    )
    seen = {entry.id for entry in first_page.entries} | {
        entry.id for entry in second_page.entries
    }
    assert seen == {str(older.id), str(a.id), str(b.id)}
    assert {entry.id for entry in first_page.entries}.isdisjoint(
        {entry.id for entry in second_page.entries}
    )


@pytest.mark.django_db
def test_invalid_cursor_raises():
    viewer = company_admin()
    _grant(viewer, TIMELINE_PERMISSION)
    target = agent_in("fairfax-va")
    with pytest.raises(ActivityProjectionError):
        project_record_activity(viewer, "user", str(target.pk), cursor="not-a-cursor")


@pytest.mark.django_db
def test_system_and_deleted_actor_labels():
    viewer = company_admin()
    _grant(viewer, TIMELINE_PERMISSION)
    target = agent_in("fairfax-va")
    event = log_event(
        "user.administration.updated",
        actor=system_actor("nightly"),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(target.pk),
            target_label="",
        ),
        office_id=_office_keys(target)[0],
    )
    page = project_record_activity(viewer, "user", str(target.pk))
    entry = page.entries[0]
    assert entry.id == str(event.id)
    assert entry.actor_kind == "system"
    assert entry.actor_label
    assert entry.target.label == "Deleted record"


@pytest.mark.django_db
def test_timezone_display_uses_application_timezone(settings):
    settings.TIME_ZONE = "America/New_York"
    viewer = company_admin()
    _grant(viewer, TIMELINE_PERMISSION)
    target = agent_in("fairfax-va")
    _event(
        action="user.administration.updated",
        target=target,
        actor=viewer,
        occurred_at=timezone.now(),
    )
    page = project_record_activity(viewer, "user", str(target.pk))
    assert page.timezone == "America/New_York"
    assert page.entries[0].occurred_at_display


@pytest.mark.django_db
def test_query_count_is_bounded(django_assert_max_num_queries):
    viewer = company_admin()
    _grant(viewer, TIMELINE_PERMISSION)
    target = agent_in("fairfax-va")
    for i in range(5):
        _event(
            action="user.administration.updated",
            target=target,
            actor=viewer,
            occurred_at=timezone.now() - timedelta(minutes=i),
        )
    with django_assert_max_num_queries(25):
        project_record_activity(viewer, "user", str(target.pk), limit=5)


def test_cursor_round_trip():
    stamp = timezone.now()
    event_id = "11111111-1111-1111-1111-111111111111"
    cursor = encode_cursor(occurred_at=stamp, event_id=event_id)
    decoded_stamp, decoded_id = decode_cursor(cursor)
    assert decoded_id == event_id
    assert decoded_stamp == stamp
