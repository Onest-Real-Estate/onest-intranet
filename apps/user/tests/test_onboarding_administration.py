from __future__ import annotations

import json
import sys
from datetime import timedelta
from types import ModuleType

import pytest
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent, DomainEvent
from apps.user.models import (
    Office,
    OnboardingTask,
    OnboardingToolSetup,
    User,
    UserOnboardingCase,
    UserRoleAssignment,
)
from apps.user.roles import ADMIN, AGENT, BRANCH_MANAGER, ScopeType
from apps.user.services.onboarding_operations import resend_notice, resolve_task
from apps.user.services.onboarding_state import (
    OverallStatus,
    build_onboarding_states,
)
from apps.user.views.onboarding_administration_views import _prefetched_queryset


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def account(email: str, slug: str, *, complete: bool = True) -> User:
    user = User.objects.create_user(
        email=email,
        first_name=email.split("@")[0].title(),
        office=office(slug),
        profile_completed=complete,
        profile_completed_at=timezone.now() if complete else None,
        start_date=timezone.localdate(),
    )
    assign(user, AGENT, ScopeType.OFFICE, user.office)
    return user


def company_admin(email: str = "admin@example.com") -> User:
    user = account(email, "fairfax-va")
    assign(user, ADMIN, ScopeType.COMPANY)
    return user


def branch_manager(slug: str, email: str) -> User:
    user = account(email, slug)
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, user.office)
    return user


def props(response) -> dict:
    return json.loads(response.content)["props"]


@pytest.mark.django_db
def test_state_is_derived_from_profile_sso_and_source_domains():
    user = account("new@example.com", "fairfax-va", complete=False)
    state = build_onboarding_states([user])[0]
    by_key = {milestone.key: milestone for milestone in state.milestones}

    assert by_key["profile"].status == "pending"
    assert by_key["microsoft_login"].status == "pending"
    assert by_key["contract_generated"].status == "pending"
    assert by_key["required_training"].status == "complete"
    assert state.overall_status == OverallStatus.IN_PROGRESS

    user.profile_completed = True
    user.profile_completed_at = timezone.now()
    user.save(update_fields=["profile_completed", "profile_completed_at"])
    SocialAccount.objects.create(user=user, provider="microsoft", uid="entra-1")
    refreshed = build_onboarding_states([User.objects.get(pk=user.pk)])[0]
    refreshed_by_key = {item.key: item for item in refreshed.milestones}
    assert refreshed_by_key["profile"].status == "complete"
    assert refreshed_by_key["microsoft_login"].status == "complete"


@pytest.mark.django_db
def test_branch_list_and_direct_id_never_enumerate_a_sibling_office(client):
    fairfax = account("fairfax@example.com", "fairfax-va")
    sibling = account("charlottesville@example.com", "charlottesville-va")
    actor = branch_manager("fairfax-va", "manager@example.com")
    client.force_login(actor)

    listing = client.get(reverse("admin_new_agents"), HTTP_X_INERTIA="true")
    payload = props(listing)
    ids = {row["user"]["id"] for row in payload["agents"]["items"]}
    assert fairfax.pk in ids
    assert sibling.pk not in ids
    assert payload["agents"]["pagination"]["totalItems"] == len(ids)

    denied = client.get(
        reverse("new_agent_onboarding", args=[sibling.pk]),
        HTTP_X_INERTIA="true",
    )
    assert denied.status_code == 404


@pytest.mark.django_db
def test_crafted_office_filter_cannot_broaden_scope(client):
    target = account("target@example.com", "fairfax-va")
    actor = branch_manager("fairfax-va", "manager@example.com")
    client.force_login(actor)

    response = client.get(
        reverse("admin_new_agents"),
        {"office": str(office("charlottesville-va").pk)},
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 200
    assert props(response)["agents"]["items"] == []
    assert target.pk not in {
        row["user"]["id"] for row in props(response)["agents"]["items"]
    }


@pytest.mark.django_db
def test_view_permission_does_not_grant_mutation(client):
    target = account("target@example.com", "fairfax-va")
    actor = account("viewer@example.com", "fairfax-va")
    actor.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web",
            codename="view_new_agents",
        )
    )
    client.force_login(actor)

    assert (
        client.get(reverse("new_agent_onboarding", args=[target.pk])).status_code == 200
    )
    denied = client.post(
        reverse("new_agent_onboarding_tasks", args=[target.pk]),
        {"action": "create", "title": "Should not exist", "expected_version": ""},
    )
    assert denied.status_code == 403
    assert not OnboardingTask.objects.filter(case__user=target).exists()


@pytest.mark.django_db
def test_filters_run_on_derived_state_and_preserve_scoped_count(client):
    blocked = account("blocked@example.com", "fairfax-va")
    case = UserOnboardingCase.objects.create(user=blocked)
    OnboardingTask.objects.create(
        case=case,
        title="Blocking operational item",
        is_blocking=True,
        status=OnboardingTask.Status.OPEN,
        created_by=blocked,
    )
    actor = branch_manager("fairfax-va", "manager@example.com")
    client.force_login(actor)

    response = client.get(
        reverse("admin_new_agents"),
        {"overallStatus": "blocked", "contractStatus": "pending"},
        HTTP_X_INERTIA="true",
    )
    rows = props(response)["agents"]["items"]
    assert rows
    assert all(row["overallStatus"] == "blocked" for row in rows)
    assert all(row["contractStatus"] == "pending" for row in rows)


@pytest.mark.django_db
def test_owner_assignment_is_scoped_audited_and_emits_domain_event(client):
    target = account("target@example.com", "fairfax-va")
    actor = company_admin()
    client.force_login(actor)

    response = client.post(
        reverse("new_agent_onboarding_owner", args=[target.pk]),
        {"owner": str(actor.pk), "expected_version": ""},
    )
    assert response.status_code == 302
    case = UserOnboardingCase.objects.get(user=target)
    assert case.owner == actor
    assert case.updated_by == actor
    assert AuditEvent.objects.filter(
        action="user.onboarding.owner_assigned", target_id=str(target.pk)
    ).exists()
    assert DomainEvent.objects.filter(
        name="user.onboarding.owner_assigned", subject=f"user:{target.pk}"
    ).exists()


@pytest.mark.django_db
def test_task_create_resolve_and_repeat_resolution_are_safe(client):
    target = account("target@example.com", "fairfax-va")
    actor = company_admin()
    client.force_login(actor)

    created = client.post(
        reverse("new_agent_onboarding_tasks", args=[target.pk]),
        {
            "action": "create",
            "title": "  Confirm key pickup  ",
            "is_blocking": "1",
            "expected_version": "",
        },
    )
    assert created.status_code == 302
    task = OnboardingTask.objects.get(case__user=target)
    assert task.title == "Confirm key pickup"
    assert task.is_blocking is True

    case = UserOnboardingCase.objects.get(user=target)
    resolved = client.post(
        reverse("new_agent_onboarding_tasks", args=[target.pk]),
        {
            "action": "resolve",
            "task": str(task.pk),
            "expected_version": case.updated_at.isoformat(),
        },
    )
    assert resolved.status_code == 302
    task.refresh_from_db()
    assert task.status == OnboardingTask.Status.RESOLVED

    case.refresh_from_db()
    assert (
        resolve_task(
            actor=actor,
            user=target,
            task_id=task.pk,
            expected_version=case.updated_at.isoformat(),
        )
        is False
    )


@pytest.mark.django_db
def test_stale_tool_update_is_rejected_without_overwrite(client):
    target = account("target@example.com", "fairfax-va")
    actor = company_admin()
    client.force_login(actor)
    first = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "state": "ready",
            "expected_version": "",
        },
    )
    assert first.status_code == 302

    stale = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "state": "blocked",
            "expected_version": "",
        },
        HTTP_X_INERTIA="true",
    )
    assert stale.status_code == 409
    assert b"Somebody else changed" in stale.content
    assert (
        OnboardingToolSetup.objects.get(case__user=target, tool="lofty").state
        == "ready"
    )


@pytest.mark.django_db
def test_derived_milestones_ignore_crafted_manual_completion_fields(client):
    target = account("target@example.com", "fairfax-va", complete=False)
    actor = company_admin()
    client.force_login(actor)

    response = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "state": "ready",
            "expected_version": "",
            "profile_completed": "1",
            "contract_active": "1",
            "training_complete": "1",
        },
    )
    assert response.status_code == 302
    target.refresh_from_db()
    assert target.profile_completed is False
    state = build_onboarding_states([target])[0]
    assert {item.key: item.status for item in state.milestones}[
        "contract_active"
    ] == "pending"


@pytest.mark.django_db
def test_notice_resend_delegates_to_source_with_idempotency_key(monkeypatch):
    target = account("target@example.com", "fairfax-va")
    actor = company_admin()
    calls = []
    package = ModuleType("apps.contract")
    service = ModuleType("apps.contract.services")

    def fake_resend(**kwargs):
        calls.append(kwargs)

    service.__dict__["resend_onboarding_notice"] = fake_resend
    package.__dict__["services"] = service
    monkeypatch.setitem(sys.modules, "apps.contract", package)
    monkeypatch.setitem(sys.modules, "apps.contract.services", service)

    resend_notice(
        actor=actor,
        user=target,
        source="contract",
        notice="signature_reminder",
        idempotency_key="00000000-0000-4000-8000-000000000001",
    )

    assert calls == [
        {
            "actor": actor,
            "user": target,
            "notice": "signature_reminder",
            "idempotency_key": "00000000-0000-4000-8000-000000000001",
        }
    ]
    assert AuditEvent.objects.filter(action="user.onboarding.notice_resent").exists()


@pytest.mark.django_db
def test_list_state_build_has_a_fixed_query_budget():
    actor = company_admin()
    for index in range(5):
        account(f"agent-{index}@example.com", "fairfax-va")

    with CaptureQueriesContext(connection) as queries:
        users = list(_prefetched_queryset(actor))
        build_onboarding_states(users)

    assert len(queries) <= 12


@pytest.mark.django_db
def test_resolved_task_retention_is_dry_run_by_default_and_audited_on_commit():
    target = account("target@example.com", "fairfax-va")
    actor = company_admin()
    case = UserOnboardingCase.objects.create(user=target)
    task = OnboardingTask.objects.create(
        case=case,
        title="Old operational task",
        status=OnboardingTask.Status.RESOLVED,
        created_by=actor,
        resolved_by=actor,
        resolved_at=timezone.now() - timedelta(days=731),
    )

    call_command("purge_onboarding_tasks")
    assert OnboardingTask.objects.filter(pk=task.pk).exists()

    call_command("purge_onboarding_tasks", commit=True)
    assert not OnboardingTask.objects.filter(pk=task.pk).exists()
    assert AuditEvent.objects.filter(
        action="user.onboarding.tasks_retention_purged"
    ).exists()


def test_case_lock_compiles_to_valid_postgresql(monkeypatch):
    """PostgreSQL rejects ``FOR UPDATE`` over the nullable side of an outer join."""
    from apps.user.services.onboarding_operations import locked_case_queryset
    from apps.user.tests.pg_compile import compile_for_postgresql

    sql = compile_for_postgresql(locked_case_queryset().filter(user_id=1), monkeypatch)

    # The outer joins onto the nullable owner/updated_by are what make an
    # unqualified FOR UPDATE illegal here.
    assert "LEFT OUTER JOIN" in sql
    assert 'FOR UPDATE OF "user_useronboardingcase"' in sql
    assert not sql.rstrip().endswith("FOR UPDATE")
