from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.onboarding_tools.models import (
    AgentToolStatus,
    OnboardingTool,
    OnboardingToolOfficeAudience,
    ToolState,
)
from apps.user.models import Office, OnboardingTask, User, UserOnboardingCase
from apps.user.services import onboarding_state
from apps.user.services.onboarding_operations import (
    StaleJourneyVersion,
    complete_required_setup,
    reset_required_setup,
    transition_office_handoff,
)
from apps.user.services.onboarding_state import (
    ContractJourneyStatus,
    ContractOnboardingState,
    JourneyAction,
    JourneyStep,
    JourneyToolState,
    MilestoneStatus,
    SourceMilestone,
    ToolInvitationStatus,
    ToolOnboardingState,
    ToolSourceStatus,
    TrainingOnboardingState,
    agent_journey_payload,
    journey_for_user,
)


def office():
    return Office.objects.get(slug="charlottesville-va")


def milestone(key, status=MilestoneStatus.PENDING, *, updated_at=None):
    return SourceMilestone(
        key=key,
        label=key.replace("_", " ").title(),
        status=status,
        source=key.split("_")[0],
        detail="Source-owned status.",
        updated_at=updated_at,
    )


def configure_sources(
    monkeypatch,
    *,
    contract_status=ContractJourneyStatus.UNAVAILABLE,
    training_status=MilestoneStatus.UNAVAILABLE,
    tool_status=MilestoneStatus.PENDING,
):
    def contracts(users):
        result = {}
        for user in users:
            generated_status = (
                MilestoneStatus.COMPLETE
                if contract_status
                in {
                    ContractJourneyStatus.GENERATED,
                    ContractJourneyStatus.SENT,
                    ContractJourneyStatus.SIGNED,
                    ContractJourneyStatus.ACTIVE,
                }
                else MilestoneStatus.PENDING
            )
            signed_status = (
                MilestoneStatus.COMPLETE
                if contract_status
                in {ContractJourneyStatus.SIGNED, ContractJourneyStatus.ACTIVE}
                else MilestoneStatus.PENDING
            )
            active_status = (
                MilestoneStatus.COMPLETE
                if contract_status == ContractJourneyStatus.ACTIVE
                else MilestoneStatus.PENDING
            )
            result[user.pk] = ContractOnboardingState(
                status=active_status,
                journey_status=contract_status,
                generated=milestone("contract_generated", generated_status),
                signed=milestone("contract_signed", signed_status),
                active=milestone("contract_active", active_status),
            )
        return result

    def training(users):
        return {
            user.pk: TrainingOnboardingState(
                status=training_status,
                required_count=1,
                completed_count=(
                    1 if training_status == MilestoneStatus.COMPLETE else 0
                ),
                milestone=milestone("required_training", training_status),
            )
            for user in users
        }

    def tools(users):
        item = JourneyToolState(
            key="lofty",
            label="Lofty",
            description="Customer relationship management",
            provisioning="onest",
            provisioning_label="oNEST sets this up for you",
            self_service=False,
            required=True,
            state=(
                "ready" if tool_status == MilestoneStatus.COMPLETE else "not_started"
            ),
            state_label=(
                "Ready" if tool_status == MilestoneStatus.COMPLETE else "Not started"
            ),
            status=tool_status,
            invitation_status=ToolInvitationStatus.UNAVAILABLE,
            invitation_label="Not available",
            complete=tool_status == MilestoneStatus.COMPLETE,
        )
        return {
            user.pk: ToolOnboardingState(
                source_status=ToolSourceStatus.AVAILABLE,
                items=(item,),
            )
            for user in users
        }

    monkeypatch.setattr(onboarding_state, "contract_states", contracts)
    monkeypatch.setattr(onboarding_state, "training_states", training)
    monkeypatch.setattr(onboarding_state, "tool_states", tools)
    monkeypatch.setattr(onboarding_state, "microsoft_user_ids", lambda users: set())


@pytest.mark.django_db
def test_journey_derives_required_profile_and_office_states(monkeypatch):
    configure_sources(monkeypatch)
    user = User.objects.create_user(email="agent@example.com")

    journey = journey_for_user(user)
    assert journey.profile_status == onboarding_state.ProfileJourneyStatus.NOT_STARTED
    assert journey.office_status == onboarding_state.OfficeJourneyStatus.NOT_SELECTED
    assert journey.current_step == JourneyStep.PROFILE
    assert journey.next_action == JourneyAction.COMPLETE_PROFILE

    user.phone_number = "2025550100"
    user.office = office()
    user.save(update_fields=["phone_number", "office"])
    journey = journey_for_user(user)
    assert journey.profile_status == onboarding_state.ProfileJourneyStatus.IN_PROGRESS
    assert journey.office_status == onboarding_state.OfficeJourneyStatus.SELECTED


@pytest.mark.django_db
def test_activation_is_derived_only_when_every_required_source_is_ready(monkeypatch):
    configure_sources(
        monkeypatch,
        contract_status=ContractJourneyStatus.ACTIVE,
        training_status=MilestoneStatus.COMPLETE,
        tool_status=MilestoneStatus.COMPLETE,
    )
    user = User.objects.create_user(
        email="ready@example.com",
        profile_completed=True,
        profile_completed_at=timezone.now(),
        office=office(),
    )
    now = timezone.now()
    UserOnboardingCase.objects.create(
        user=user,
        office_confirmed_at=now,
        office_confirmed_for=user.office,
        office_confirmation_version=user.onboarding_version,
        required_setup_completed_at=now,
        office_handoff_state=UserOnboardingCase.OfficeHandoffState.NOTIFIED,
        office_handoff_updated_at=now,
        office_handoff_office=user.office,
        office_handoff_onboarding_version=user.onboarding_version,
    )

    journey = journey_for_user(user)
    assert journey.required_setup_complete is True
    assert journey.activation_complete is True
    assert journey.current_step == JourneyStep.COMPLETE
    assert journey.next_action == JourneyAction.NONE


@pytest.mark.django_db
def test_unavailable_source_is_honest_but_does_not_reopen_required_gate(monkeypatch):
    configure_sources(monkeypatch)
    user = User.objects.create_user(
        email="waiting@example.com",
        profile_completed=True,
        profile_completed_at=timezone.now(),
        office=office(),
    )

    payload = agent_journey_payload(journey_for_user(user))
    assert payload["requiredSetupComplete"] is True
    assert payload["strictGateActive"] is False
    assert payload["activationComplete"] is False
    assert payload["contract"]["state"] == "unavailable"
    assert any(item["key"] == "contract_unavailable" for item in payload["blockers"])


@pytest.mark.django_db
def test_required_setup_is_stale_safe_idempotent_and_audited():
    user = User.objects.create_user(
        email="setup@example.com",
        profile_completed=True,
        profile_completed_at=timezone.now(),
        office=office(),
    )

    with pytest.raises(StaleJourneyVersion):
        complete_required_setup(user=user, expected_version="stale")
    assert not UserOnboardingCase.objects.filter(user=user).exists()

    UserOnboardingCase.objects.create(
        user=user,
        office_confirmed_at=timezone.now(),
        office_confirmed_for=user.office,
        office_confirmation_version=user.onboarding_version,
    )
    assert complete_required_setup(user=user) is True
    assert complete_required_setup(user=user) is False
    assert (
        AuditEvent.objects.filter(
            action="user.onboarding.required_setup_completed"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_handoff_transitions_are_closed_versioned_and_idempotent():
    actor = User.objects.create_superuser(email="admin@example.com", password="x")
    user = User.objects.create_user(email="agent@example.com", office=office())
    case = UserOnboardingCase.objects.create(user=user)
    version = onboarding_state.journey_version(user, case)

    assert (
        transition_office_handoff(
            actor=actor,
            user=user,
            state=UserOnboardingCase.OfficeHandoffState.NOTIFIED,
            expected_version=version,
        )
        is True
    )
    case.refresh_from_db()
    assert case.office_handoff_state == UserOnboardingCase.OfficeHandoffState.NOTIFIED
    assert (
        transition_office_handoff(
            actor=actor,
            user=user,
            state=UserOnboardingCase.OfficeHandoffState.NOTIFIED,
            expected_version="stale-but-idempotent",
        )
        is False
    )
    with pytest.raises(ValidationError):
        transition_office_handoff(
            actor=actor,
            user=user,
            state=UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED,
            expected_version=onboarding_state.journey_version(user, case),
        )


@pytest.mark.django_db
def test_reset_increments_version_and_preserves_downstream_history():
    actor = User.objects.create_superuser(email="admin@example.com", password="x")
    user = User.objects.create_user(
        email="agent@example.com",
        profile_completed=True,
        profile_completed_at=timezone.now(),
        office=office(),
        onboarding_version=4,
    )
    case = UserOnboardingCase.objects.create(
        user=user,
        office_confirmed_at=timezone.now(),
        required_setup_completed_at=timezone.now(),
        office_handoff_state=UserOnboardingCase.OfficeHandoffState.NOTIFIED,
    )
    task = OnboardingTask.objects.create(
        case=case,
        title="Historic activation task",
        created_by=actor,
    )

    reset_required_setup(actor=actor, user=user)
    user.refresh_from_db()
    case.refresh_from_db()
    assert user.profile_completed is False
    assert user.onboarding_version == 5
    assert case.office_confirmed_at is None
    assert case.required_setup_completed_at is None
    assert case.office_handoff_state == UserOnboardingCase.OfficeHandoffState.NOTIFIED
    assert OnboardingTask.objects.filter(pk=task.pk).exists()


@pytest.mark.django_db
def test_completed_user_backfill_is_explicit_and_idempotent():
    user = User.objects.create_user(
        email="legacy@example.com",
        profile_completed=True,
        profile_completed_at=timezone.now(),
    )
    migration = import_module("apps.user.migrations.0031_onboarding_journey_state")

    migration.backfill_completed_onboarding_cases(django_apps, None)
    migration.backfill_completed_onboarding_cases(django_apps, None)

    case = UserOnboardingCase.objects.get(user=user)
    assert case.office_confirmed_at == user.profile_completed_at
    assert case.required_setup_completed_at == user.profile_completed_at


def add_tool(slug, *, audience_office=None):
    tool = OnboardingTool.objects.create(
        slug=slug,
        name=slug.title(),
        description="Query budget fixture.",
        group="company",
        contact_label="IT support",
        company_wide=audience_office is None,
    )
    if audience_office is not None:
        OnboardingToolOfficeAudience.objects.create(tool=tool, office=audience_office)
    return tool


@pytest.mark.django_db
def test_journey_query_count_does_not_grow_with_tools_or_tasks():
    user = User.objects.create_user(email="budget@example.com", office=office())
    creator = User.objects.create_superuser(email="admin@example.com", password="x")
    case = UserOnboardingCase.objects.create(user=user)
    add_tool("budget-base")
    OnboardingTask.objects.create(
        case=case, title="Baseline activation task", created_by=creator
    )

    def journey_query_count():
        with CaptureQueriesContext(connection) as queries:
            agent_journey_payload(journey_for_user(user))
        return len(queries)

    journey_query_count()  # warm per-process caches before measuring
    baseline = journey_query_count()

    for index in range(4):
        tool = add_tool(f"budget-{index}", audience_office=office())
        AgentToolStatus.objects.create(
            agent=user, tool=tool, state=ToolState.IN_PROGRESS
        )
        OnboardingTask.objects.create(
            case=case, title=f"Activation task {index}", created_by=creator
        )

    payload = agent_journey_payload(journey_for_user(user))
    assert {f"budget-{index}" for index in range(4)} <= {
        item["key"] for item in payload["tools"]
    }
    assert journey_query_count() == baseline
