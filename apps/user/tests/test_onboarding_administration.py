from __future__ import annotations

import json
import sys
from datetime import timedelta
from types import ModuleType
from uuid import uuid4

import pytest
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.audit.models import AuditEvent, DomainEvent
from apps.contract.models import AgentContract
from apps.notifications.actions import resolve_action_href
from apps.notifications.consumers import deliver_for_event
from apps.notifications.models import Notification, NotificationEmail
from apps.notifications.sources import resolve_sources
from apps.onboarding_tools.models import (
    AgentToolStatus,
    OnboardingTool,
    Provisioning,
    ToolGroup,
    ToolState,
)
from apps.user.models import (
    Office,
    OnboardingTask,
    User,
    UserOnboardingCase,
    UserRoleAssignment,
)
from apps.user.roles import ADMIN, AGENT, BRANCH_MANAGER, ScopeType
from apps.user.services.onboarding_operations import resend_notice, resolve_task
from apps.user.services.onboarding_state import (
    OverallStatus,
    build_onboarding_states,
    journey_version,
)
from apps.user.views.onboarding_administration_views import (
    _detail_props,
    _prefetched_queryset,
)


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


def action_version(user: User) -> str:
    case = UserOnboardingCase.objects.filter(user=user).first()
    current = User.objects.select_related("office").get(pk=user.pk)
    return journey_version(current, case)


def confirm_required_setup(user: User) -> UserOnboardingCase:
    now = timezone.now()
    return UserOnboardingCase.objects.create(
        user=user,
        office_confirmed_at=now,
        office_confirmed_for=user.office,
        office_confirmation_version=user.onboarding_version,
        required_setup_completed_at=now,
    )


def event_envelope(event: DomainEvent) -> EventEnvelope:
    return EventEnvelope(
        id=event.id,
        name=event.name,
        version=event.version,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        subject=event.subject,
        organization_id=event.organization_id,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        payload=event.payload,
    )


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
        {"owner": str(actor.pk), "expected_version": action_version(target)},
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
            "expected_version": action_version(target),
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
            "expected_version": action_version(target),
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
            expected_version=action_version(target),
        )
        is False
    )


@pytest.mark.django_db
def test_stale_tool_update_is_rejected_without_overwrite(client):
    target = account("target@example.com", "fairfax-va")
    confirm_required_setup(target)
    actor = company_admin()
    client.force_login(actor)
    first = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "action": "mark_ready",
            "expected_version": action_version(target),
        },
    )
    assert first.status_code == 302

    stale = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "action": "mark_blocked",
            "reason": "Vendor account is unavailable.",
            "expected_version": "stale",
        },
        HTTP_X_INERTIA="true",
    )
    assert stale.status_code == 409
    assert b"Somebody else changed" in stale.content
    assert (
        AgentToolStatus.objects.get(agent=target, tool__slug="lofty").state == "ready"
    )


@pytest.mark.django_db
def test_the_workspace_records_an_invitation_against_the_catalog_row(client):
    target = account("target@example.com", "fairfax-va")
    confirm_required_setup(target)
    actor = company_admin()
    client.force_login(actor)

    response = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "skyslope",
            "action": "mark_invitation_sent",
            "expected_version": action_version(target),
        },
    )

    assert response.status_code == 302
    row = AgentToolStatus.objects.get(agent=target, tool__slug="skyslope")
    assert row.state == "invitation_sent"
    assert row.invitation_sent_at is not None
    assert row.invitation_sent_by == actor


@pytest.mark.django_db
def test_correcting_a_tool_backwards_needs_a_reason(client):
    target = account("target@example.com", "fairfax-va")
    confirm_required_setup(target)
    actor = company_admin()
    client.force_login(actor)
    first = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "action": "mark_ready",
            "expected_version": action_version(target),
        },
    )
    assert first.status_code == 302
    refused = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "action": "revoke_invitation",
            "expected_version": action_version(target),
        },
        HTTP_X_INERTIA="true",
    )

    assert refused.status_code == 422
    assert "reason" in json.loads(refused.content)["props"]["validation"]["fields"]
    assert (
        AgentToolStatus.objects.get(agent=target, tool__slug="lofty").state == "ready"
    )


@pytest.mark.django_db
def test_tool_actions_refuse_crafted_prerequisite_completion_fields(client):
    target = account("target@example.com", "fairfax-va", complete=False)
    actor = company_admin()
    client.force_login(actor)

    response = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "action": "mark_ready",
            "expected_version": action_version(target),
            "profile_completed": "1",
            "contract_active": "1",
            "training_complete": "1",
        },
    )
    assert response.status_code == 422
    target.refresh_from_db()
    assert target.profile_completed is False
    assert not AgentToolStatus.objects.filter(agent=target, tool__slug="lofty").exists()
    state = build_onboarding_states([target])[0]
    assert {item.key: item.status for item in state.milestones}[
        "contract_active"
    ] == "pending"


@pytest.mark.django_db
def test_workspace_limits_profile_fields_and_exposes_confirmed_office(client):
    target = account("target@example.com", "fairfax-va")
    target.phone_number = "+12025550100"
    target.street_address = "Private home"
    target.license_number = "PRIVATE-LICENSE"
    target.save(update_fields=["phone_number", "street_address", "license_number"])
    confirm_required_setup(target)
    viewer = account("viewer@example.com", "fairfax-va")
    viewer.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web",
            codename="view_new_agents",
        )
    )
    client.force_login(viewer)

    response = client.get(
        reverse("new_agent_onboarding", args=[target.pk]),
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 200
    payload = props(response)
    assert payload["profileSummary"]["sensitiveFieldsIncluded"] is False
    keys = {field["key"] for field in payload["profileSummary"]["fields"]}
    assert (
        not {"phoneNumber", "homeAddress", "license", "mlsNumber", "nrdsNumber"} & keys
    )
    serialized = json.dumps(payload["profileSummary"])
    assert "Private home" not in serialized
    assert "PRIVATE-LICENSE" not in serialized
    assert target.office is not None
    assert payload["confirmedOffice"]["office"]["id"] == target.office.pk
    assert payload["onboarding"]["recommendedAction"]["source"] in {
        "tool",
        "contract",
        "onboarding",
    }


@pytest.mark.django_db
def test_tool_action_revalidates_office_and_active_catalog_at_submit(client):
    target = account("target@example.com", "fairfax-va")
    confirm_required_setup(target)
    actor = company_admin()
    client.force_login(actor)
    stale_version = action_version(target)
    target.office = office("charlottesville-va")
    target.save(update_fields=["office"])

    changed_office = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        data=json.dumps(
            {
                "tool": "lofty",
                "action": "mark_invitation_sent",
                "expected_version": stale_version,
            }
        ),
        content_type="application/json",
        HTTP_X_INERTIA="true",
    )
    assert changed_office.status_code == 409
    assert not AgentToolStatus.objects.filter(agent=target).exists()

    target.refresh_from_db()
    case = UserOnboardingCase.objects.get(user=target)
    case.office_confirmed_at = timezone.now()
    case.office_confirmed_for = target.office
    case.office_confirmation_version = target.onboarding_version
    case.required_setup_completed_at = timezone.now()
    case.save()
    tool = OnboardingTool.objects.get(slug="lofty")
    tool.is_active = False
    tool.save(update_fields=["is_active"])
    inactive = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "lofty",
            "action": "mark_ready",
            "expected_version": action_version(target),
        },
        HTTP_X_INERTIA="true",
    )
    assert inactive.status_code == 422
    assert "inactive or no longer applies" in inactive.content.decode()
    assert not AgentToolStatus.objects.filter(agent=target).exists()


@pytest.mark.django_db
def test_self_scope_and_missing_source_permission_refuse_contract_actions(client):
    target = account("target@example.com", "fairfax-va")
    confirm_required_setup(target)
    self_actor = company_admin("self@example.com")
    confirm_required_setup(self_actor)
    client.force_login(self_actor)
    self_response = client.post(
        reverse("new_agent_onboarding_contract", args=[self_actor.pk]),
        {"expected_version": action_version(self_actor)},
    )
    assert self_response.status_code in {403, 404}

    limited = account("limited@example.com", "fairfax-va")
    limited.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="web",
            codename__in=("view_new_agents", "manage_new_agent_onboarding"),
        )
    )
    client.force_login(limited)
    denied = client.post(
        reverse("new_agent_onboarding_contract", args=[target.pk]),
        {"expected_version": action_version(target)},
    )
    assert denied.status_code == 403
    assert not AgentContract.objects.filter(recipient=target).exists()


@pytest.mark.django_db
def test_contract_initiation_delegates_and_reuses_existing_contract(client):
    target = account("target@example.com", "fairfax-va")
    confirm_required_setup(target)
    actor = company_admin()
    client.force_login(actor)

    first = client.post(
        reverse("new_agent_onboarding_contract", args=[target.pk]),
        data=json.dumps({"expected_version": action_version(target)}),
        content_type="application/json",
    )
    assert first.status_code == 302
    contract = AgentContract.objects.get(recipient=target)
    assert contract.status == "draft"

    repeated = client.post(
        reverse("new_agent_onboarding_contract", args=[target.pk]),
        {"expected_version": action_version(target)},
    )
    assert repeated.status_code == 302
    assert AgentContract.objects.filter(recipient=target).count() == 1
    assert (
        AuditEvent.objects.filter(
            action="user.onboarding.contract_initiated",
            target_id=str(target.pk),
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_contract_prerequisite_failure_rolls_back_case_changes(client):
    target = account("target@example.com", "fairfax-va", complete=False)
    case = UserOnboardingCase.objects.create(user=target)
    original_updated_at = case.updated_at
    actor = company_admin()
    client.force_login(actor)

    response = client.post(
        reverse("new_agent_onboarding_contract", args=[target.pk]),
        {"expected_version": action_version(target)},
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    case.refresh_from_db()
    assert case.updated_at == original_updated_at
    assert not AgentContract.objects.filter(recipient=target).exists()


@pytest.mark.django_db
def test_invitation_notice_is_agent_only_redacted_and_deduplicated(client):
    target = account("target@example.com", "fairfax-va")
    target.phone_number = "+12025550100"
    target.street_address = "Private home"
    target.mls_number = "PRIVATE-MLS"
    target.save(update_fields=["phone_number", "street_address", "mls_number"])
    confirm_required_setup(target)
    actor = company_admin()
    client.force_login(actor)

    response = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        data=json.dumps(
            {
                "tool": "lofty",
                "action": "mark_invitation_sent",
                "expected_version": action_version(target),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 302
    event = DomainEvent.objects.filter(
        name="onboarding_tool.state_changed", subject=f"user:{target.pk}"
    ).latest("occurred_at")
    serialized_event = json.dumps(event.payload)
    for secret in ("Private home", "PRIVATE-MLS", "+12025550100"):
        assert secret not in serialized_event

    envelope = event_envelope(event)
    deliver_for_event(envelope)
    deliver_for_event(
        EventEnvelope(
            id=uuid4(),
            name=envelope.name,
            version=envelope.version,
            occurred_at=envelope.occurred_at,
            actor_id=envelope.actor_id,
            subject=envelope.subject,
            organization_id=envelope.organization_id,
            correlation_id=None,
            causation_id=None,
            payload=envelope.payload,
        )
    )

    notice = Notification.objects.get(recipient=target)
    assert Notification.objects.count() == 1
    assert notice.title == "Your Lofty invitation was sent"
    assert notice.action_key == "open_onboarding_status"
    assert resolve_action_href(notice.action_key, notice.action_args) == reverse(
        "dashboard"
    )
    resolution = resolve_sources(target, [notice])[notice.public_id]
    assert resolution.detail == (
        "Look for the Lofty activation email in Microsoft Outlook."
    )
    serialized_notice = json.dumps(
        {
            "title": notice.title,
            "source": notice.source_record_id,
            "action": notice.action_args,
            "detail": resolution.detail,
        }
    )
    assert "http" not in serialized_notice
    assert actor.pk != notice.recipient_id


@pytest.mark.django_db
def test_failed_agent_notice_is_visible_and_retryable(client):
    target = account("target@example.com", "fairfax-va")
    confirm_required_setup(target)
    actor = company_admin()
    client.force_login(actor)
    client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "skyslope",
            "action": "mark_invitation_sent",
            "expected_version": action_version(target),
        },
    )
    event = DomainEvent.objects.filter(
        name="onboarding_tool.state_changed", subject=f"user:{target.pk}"
    ).latest("occurred_at")
    deliver_for_event(event_envelope(event))
    notice = Notification.objects.get(recipient=target)
    delivery = NotificationEmail.objects.filter(notification=notice).first()
    if delivery is None:
        delivery = NotificationEmail.objects.create(
            notification=notice,
            recipient=target,
            delivery_key=notice.dedupe_key,
            status=NotificationEmail.Status.DEAD,
        )
    else:
        delivery.status = NotificationEmail.Status.DEAD
        delivery.save(update_fields=["status"])

    workspace = client.get(
        reverse("new_agent_onboarding", args=[target.pk]),
        HTTP_X_INERTIA="true",
    )
    tool = next(
        item
        for item in props(workspace)["onboarding"]["tools"]
        if item["key"] == "skyslope"
    )
    assert tool["delivery"]["retryable"] is True
    assert tool["actions"][0]["code"] == "retry_notification"

    retried = client.post(
        reverse("new_agent_onboarding_tools", args=[target.pk]),
        {
            "tool": "skyslope",
            "action": "retry_notification",
            "expected_version": action_version(target),
        },
    )
    assert retried.status_code == 302
    delivery.refresh_from_db()
    assert delivery.status == NotificationEmail.Status.PENDING
    assert AgentToolStatus.objects.get(agent=target, tool__slug="skyslope").state == (
        ToolState.INVITATION_SENT
    )


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
        expected_version=journey_version(target, None),
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

    # One bulk call per source domain — contract, training, tools, Microsoft
    # identity, and the office-handoff delivery state — never one per agent.
    assert len(queries) <= 14

    for index in range(5, 15):
        account(f"agent-{index}@example.com", "fairfax-va")

    with CaptureQueriesContext(connection) as larger:
        build_onboarding_states(list(_prefetched_queryset(actor)))

    with CaptureQueriesContext(connection) as smaller:
        build_onboarding_states(list(_prefetched_queryset(actor))[:5])

    # Tripling the batch must not cost a single extra query.
    assert len(larger) == len(smaller)


@pytest.mark.django_db
def test_workspace_detail_query_cost_does_not_grow_per_tool():
    target = account("target@example.com", "fairfax-va")
    confirm_required_setup(target)
    actor = company_admin()
    baseline_target = _prefetched_queryset(actor).get(pk=target.pk)
    with CaptureQueriesContext(connection) as baseline:
        _detail_props(actor, baseline_target)

    OnboardingTool.objects.bulk_create(
        [
            OnboardingTool(
                slug=f"bounded-{index}",
                name=f"Bounded {index}",
                description="Query-budget fixture",
                group=ToolGroup.COMPANY,
                provisioning=Provisioning.ONEST,
                contact_label="Operations",
                company_wide=True,
                sort_order=100 + index,
            )
            for index in range(12)
        ]
    )
    # Fresh actor instance ≈ fresh request: effective access is memoized on the
    # user instance, so baseline's resolution must not leak into this capture.
    actor = User.objects.get(pk=actor.pk)
    expanded_target = _prefetched_queryset(actor).get(pk=target.pk)
    with CaptureQueriesContext(connection) as expanded:
        _detail_props(actor, expanded_target)

    assert len(expanded) == len(baseline)


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
