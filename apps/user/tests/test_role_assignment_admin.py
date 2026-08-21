"""Role-assignment administration surface and assigned-record scope."""

import json

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.user.models import User, UserRoleAssignment
from apps.user.roles import (
    ADMIN,
    AGENT,
    BROKER_ADMIN,
    TRANSACTION_COORDINATOR,
    ScopeType,
)
from apps.user.services.role_assignment_admin import (
    StaleRoleAssignmentVersion,
    admin_grant_assignment,
    admin_revoke_assignment,
    assignment_version,
    grant_version,
    preview_grant,
    preview_revoke,
    workspace_payload,
)
from apps.user.services.role_assignments import (
    create_role_assignment,
    get_effective_access,
)
from apps.user.tests.test_onboarding import assignable_office
from apps.web.shell import authorization_version


def inertia_props(response) -> dict:
    return json.loads(response.content)["props"]


def _admin_actor(*, email: str = "broker-admin@example.com") -> User:
    actor = User.objects.create_superuser(email="system@example.com")
    admin = User.objects.create_user(
        email=email,
        profile_completed=True,
    )
    create_role_assignment(
        actor=actor,
        target_user=admin,
        role=ADMIN,
        scope_type=ScopeType.COMPANY,
    )
    return admin


def _target(*, email: str = "agent@example.com") -> User:
    return User.objects.create_user(
        email=email,
        office=assignable_office(),
        agent_status="active",
        profile_completed=True,
    )


@pytest.mark.django_db
def test_assigned_record_grant_does_not_widen_org_reach():
    actor = User.objects.create_superuser(email="admin@example.com")
    target = _target()
    assignment = create_role_assignment(
        actor=actor,
        target_user=target,
        role=AGENT,
        scope_type=ScopeType.ASSIGNED_RECORD,
        business_reason="File-only access",
    )
    assert assignment.scope_office is None
    assert assignment.scope_label() == "Assigned records"
    access = get_effective_access(target)
    assert access.assigned_record is True
    assert access.company_wide is False
    assert access.office_keys == frozenset()
    assert AGENT in access.role_keys


@pytest.mark.django_db
def test_assigned_record_rejected_for_roles_that_forbid_it():
    actor = User.objects.create_superuser(email="admin@example.com")
    target = _target()
    with pytest.raises(ValidationError):
        create_role_assignment(
            actor=actor,
            target_user=target,
            role=BROKER_ADMIN,
            scope_type=ScopeType.ASSIGNED_RECORD,
            business_reason="Should fail",
        )


@pytest.mark.django_db
def test_preview_grant_matches_post_save_access():
    actor = _admin_actor()
    target = _target()
    preview = preview_grant(
        actor=actor,
        target=target,
        role=TRANSACTION_COORDINATOR,
        scope_type=ScopeType.OFFICE,
        scope_office=target.office,
    )
    before_version = authorization_version(get_effective_access(target))
    assignment = admin_grant_assignment(
        actor=actor,
        target=target,
        role=TRANSACTION_COORDINATOR,
        scope_type=ScopeType.OFFICE,
        scope_office=target.office,
        business_reason="Need a coordinator",
        expected_version=grant_version(target),
        confirmed=True,
    )
    after = get_effective_access(target)
    assert preview["after"]["roleKeys"] == list(after.role_keys)
    assert set(preview["after"]["permissions"]) == set(after.permissions)
    assert authorization_version(after) != before_version
    assert assignment.status == UserRoleAssignment.Status.ACTIVE


@pytest.mark.django_db
def test_self_assignment_is_refused():
    actor = _admin_actor()
    with pytest.raises(PermissionDenied):
        admin_grant_assignment(
            actor=actor,
            target=actor,
            role=AGENT,
            scope_type=ScopeType.ASSIGNED_RECORD,
            scope_office=None,
            business_reason="Self grant",
            expected_version=grant_version(actor),
            confirmed=True,
        )


@pytest.mark.django_db
def test_stale_grant_version_is_rejected():
    actor = _admin_actor()
    target = _target()
    with pytest.raises(StaleRoleAssignmentVersion):
        admin_grant_assignment(
            actor=actor,
            target=target,
            role=AGENT,
            scope_type=ScopeType.OFFICE,
            scope_office=target.office,
            business_reason="Stale",
            expected_version="stale-token",
            confirmed=True,
        )


@pytest.mark.django_db
def test_high_impact_grant_requires_confirmation():
    actor = _admin_actor()
    target = _target()
    with pytest.raises(ValidationError, match="high-impact"):
        admin_grant_assignment(
            actor=actor,
            target=target,
            role=BROKER_ADMIN,
            scope_type=ScopeType.COMPANY,
            scope_office=None,
            business_reason="Promote",
            expected_version=grant_version(target),
            confirmed=False,
        )


@pytest.mark.django_db
def test_last_live_assignment_cannot_be_revoked_for_engaged_agent():
    actor = _admin_actor()
    target = _target()
    assignment = create_role_assignment(
        actor=User.objects.get(email="system@example.com"),
        target_user=target,
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office=target.office,
        business_reason="Only role",
    )
    preview = preview_revoke(actor=actor, target=target, assignment=assignment)
    assert preview["warnings"]
    with pytest.raises(ValidationError, match="only live role"):
        admin_revoke_assignment(
            actor=actor,
            target=target,
            assignment=assignment,
            business_reason="Strip",
            expected_version=assignment_version(assignment),
            confirmed=True,
        )


@pytest.mark.django_db
def test_index_and_workspace_http_surface(client):
    actor = _admin_actor(email="ops-admin@example.com")
    target = _target(email="workspace-agent@example.com")
    create_role_assignment(
        actor=User.objects.get(email="system@example.com"),
        target_user=target,
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office=target.office,
        business_reason="Seed",
    )
    client.force_login(actor)

    index = client.get(reverse("admin_assign_roles"), HTTP_X_INERTIA="true")
    assert index.status_code == 200
    props = inertia_props(index)
    assert "users" in props
    assert "filterOptions" in props

    workspace = client.get(
        reverse("admin_assign_roles_user", args=[target.pk]),
        HTTP_X_INERTIA="true",
    )
    assert workspace.status_code == 200
    props = inertia_props(workspace)
    assert props["workspace"]["subject"]["id"] == target.pk
    assert props["workspace"]["grantVersion"]

    denied = User.objects.create_user(
        email="no-assign@example.com",
        profile_completed=True,
    )
    client.force_login(denied)
    assert client.get(reverse("admin_assign_roles")).status_code == 403


@pytest.mark.django_db
def test_workspace_payload_lists_all_statuses():
    actor = _admin_actor()
    target = _target()
    system = User.objects.get(email="system@example.com")
    live = create_role_assignment(
        actor=system,
        target_user=target,
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office=target.office,
        business_reason="Live",
    )
    payload = workspace_payload(actor, target)
    ids = {row["id"] for row in payload["assignments"]}
    assert live.pk in ids
    assert payload["editable"] is True
