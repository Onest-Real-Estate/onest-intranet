"""Canonical, source-owned onboarding state for every product surface.

The list, workspace, dashboard metric, user detail, and future assistants must
call this module instead of reconstructing milestone rules.  Operational rows
live in ``UserOnboardingCase``; profile, Microsoft SSO, contracts, and training
remain derived from their source domains and are never writable here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from importlib import import_module
from typing import Any

from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from apps.user.models import (
    OnboardingTask,
    OnboardingToolSetup,
    User,
    UserOnboardingCase,
)
from apps.user.roles import AGENT
from apps.user.services.agent_administration import administered_user_queryset
from apps.user.services.role_assignments import (
    EffectiveAccess,
    get_effective_access,
    has_effective_permission,
)

VIEW_PERMISSION = "web.view_new_agents"
MANAGE_PERMISSION = "web.manage_new_agent_onboarding"
NEW_AGENT_WINDOW_DAYS = 90


def journey_applies_to(user: User, *, access: EffectiveAccess | None = None) -> bool:
    """Only ordinary users with an effective Agent role enter this journey."""
    if user.is_staff or user.is_superuser:
        return False
    effective = access or get_effective_access(user)
    return AGENT in effective.role_keys


class MilestoneStatus(StrEnum):
    COMPLETE = "complete"
    PENDING = "pending"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class OverallStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    READY = "ready"


class ProfileJourneyStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class OfficeJourneyStatus(StrEnum):
    NOT_SELECTED = "not_selected"
    SELECTED = "selected"
    CONFIRMED = "confirmed"


class ContractJourneyStatus(StrEnum):
    GENERATED = "generated"
    SENT = "sent"
    SIGNED = "signed"
    ACTIVE = "active"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class ToolInvitationStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    SENT = "sent"
    UNAVAILABLE = "unavailable"


class JourneyStep(StrEnum):
    PROFILE = "profile"
    OFFICE = "office"
    ACTIVATION = "activation"
    COMPLETE = "complete"


class JourneyAction(StrEnum):
    COMPLETE_PROFILE = "complete_profile"
    CONFIRM_OFFICE = "confirm_office"
    SET_UP_TOOL = "set_up_tool"
    WAIT_FOR_OFFICE = "wait_for_office"
    WAIT_FOR_ACTIVATION = "wait_for_activation"
    NONE = "none"


class ToolSourceStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SourceMilestone:
    key: str
    label: str
    status: str
    source: str
    detail: str
    updated_at: datetime | None = None

    def payload(self, *, correction: dict[str, str] | None = None) -> dict[str, Any]:
        presentation = milestone_status_payload(self.status)
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "statusLabel": presentation["label"],
            "tone": presentation["tone"],
            "source": self.source,
            "detail": self.detail,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "correction": correction,
        }


@dataclass(frozen=True)
class ContractOnboardingState:
    status: str
    journey_status: ContractJourneyStatus
    generated: SourceMilestone
    signed: SourceMilestone
    active: SourceMilestone
    eligible_notices: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class TrainingOnboardingState:
    status: str
    required_count: int | None
    completed_count: int | None
    milestone: SourceMilestone
    eligible_notices: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class JourneyToolState:
    key: str
    label: str
    description: str
    provisioning: str
    provisioning_label: str
    self_service: bool
    required: bool
    state: str
    state_label: str
    status: MilestoneStatus
    invitation_status: ToolInvitationStatus
    invitation_label: str
    complete: bool
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ToolOnboardingState:
    source_status: ToolSourceStatus
    items: tuple[JourneyToolState, ...]


@dataclass(frozen=True)
class AgentOnboardingJourney:
    profile_status: ProfileJourneyStatus
    profile_updated_at: datetime | None
    office_status: OfficeJourneyStatus
    office_updated_at: datetime | None
    office_handoff_status: UserOnboardingCase.OfficeHandoffState
    office_handoff_updated_at: datetime | None
    contract_status: ContractJourneyStatus
    contract_updated_at: datetime | None
    tools: ToolOnboardingState
    required_setup_complete: bool
    activation_complete: bool
    current_step: JourneyStep
    next_action: JourneyAction
    blockers: tuple[dict[str, str], ...]
    version: str
    updated_at: datetime


@dataclass(frozen=True)
class OnboardingState:
    user: User
    case: UserOnboardingCase | None
    milestones: tuple[SourceMilestone, ...]
    contract: ContractOnboardingState
    training: TrainingOnboardingState
    overall_status: str
    blockers: tuple[dict[str, str], ...]
    open_tasks: tuple[OnboardingTask, ...]
    tool_setups: tuple[dict[str, Any], ...]
    journey: AgentOnboardingJourney

    @property
    def completion(self) -> tuple[int, int]:
        total = len(self.milestones) + len(self.tool_setups)
        complete = sum(
            item.status == MilestoneStatus.COMPLETE for item in self.milestones
        ) + sum(item["status"] == MilestoneStatus.COMPLETE for item in self.tool_setups)
        return complete, total


def new_agent_queryset(
    actor: User,
    *,
    at: datetime | None = None,
    access: EffectiveAccess | None = None,
) -> QuerySet[User]:
    """Potential onboarding records, scoped before any search or aggregation.

    A record remains in the workspace while its profile is incomplete or it has
    open operational work, even after the 90-day new-agent window ends.
    ``access`` is accepted for dashboard callers that already resolved it; the
    administration scope service remains the one database boundary.
    """
    del access  # administered_user_queryset resolves the same effective grant.
    moment = at or timezone.now()
    cutoff_date = timezone.localdate(moment) - timedelta(days=NEW_AGENT_WINDOW_DAYS)
    cutoff_datetime = moment - timedelta(days=NEW_AGENT_WINDOW_DAYS)
    return (
        administered_user_queryset(actor)
        .filter(
            Q(start_date__gte=cutoff_date)
            | Q(date_joined__gte=cutoff_datetime)
            | Q(profile_completed=False)
            | Q(onboarding_case__tasks__status=OnboardingTask.Status.OPEN)
            | Q(
                onboarding_case__tool_setups__state__in=[
                    OnboardingToolSetup.State.NOT_STARTED,
                    OnboardingToolSetup.State.IN_PROGRESS,
                    OnboardingToolSetup.State.BLOCKED,
                ]
            )
        )
        .distinct()
    )


def dashboard_new_agent_queryset(
    actor: User,
    *,
    at: datetime,
    days: int,
    access: EffectiveAccess,
) -> QuerySet[User]:
    """Dashboard's reviewed trailing-window population through this service."""
    from apps.web.authorization import scope_queryset_for_user_office

    return scope_queryset_for_user_office(
        actor,
        User.objects.filter(
            is_active=True,
            date_joined__gte=at - timedelta(days=days),
        ),
        field_name="office",
        access=access,
    )


def _unavailable_contract_state() -> ContractOnboardingState:
    detail = "The agent-contract source is not connected to the hub yet."
    milestones = tuple(
        SourceMilestone(
            key=f"contract_{key}",
            label=label,
            status=MilestoneStatus.UNAVAILABLE,
            source="contract",
            detail=detail,
        )
        for key, label in (
            ("generated", "Contract generated"),
            ("signed", "Contract signed"),
            ("active", "Contract active"),
        )
    )
    return ContractOnboardingState(
        status=MilestoneStatus.UNAVAILABLE,
        journey_status=ContractJourneyStatus.UNAVAILABLE,
        generated=milestones[0],
        signed=milestones[1],
        active=milestones[2],
    )


def _unavailable_training_state() -> TrainingOnboardingState:
    return TrainingOnboardingState(
        status=MilestoneStatus.UNAVAILABLE,
        required_count=None,
        completed_count=None,
        milestone=SourceMilestone(
            key="required_training",
            label="Required training",
            status=MilestoneStatus.UNAVAILABLE,
            source="training",
            detail="The training source is not connected to the hub yet.",
        ),
    )


def contract_states(users: list[User]) -> dict[int, ContractOnboardingState]:
    """Bulk adapter contract for ``apps.contract.services``.

    The future source implements ``bulk_agent_onboarding_states(users)`` and
    returns these typed values.  No per-user fallback is allowed because that
    would hide an N+1 query behind the service boundary.
    """
    try:
        module = import_module("apps.contract.services")
    except ModuleNotFoundError as exc:
        if exc.name not in {"apps.contract", "apps.contract.services"}:
            raise
        return {user.pk: _unavailable_contract_state() for user in users}
    return module.bulk_agent_onboarding_states(users)


def training_states(users: list[User]) -> dict[int, TrainingOnboardingState]:
    """Bulk adapter contract for ``apps.training.services``."""
    try:
        module = import_module("apps.training.services")
    except ModuleNotFoundError as exc:
        if exc.name not in {"apps.training", "apps.training.services"}:
            raise
        return {user.pk: _unavailable_training_state() for user in users}
    return module.bulk_agent_onboarding_states(users)


def tool_states(users: list[User]) -> dict[int, ToolOnboardingState]:
    """Bulk adapter contract for the dynamic onboarding-tool catalog."""
    try:
        module = import_module("apps.onboarding_tools.services")
    except ModuleNotFoundError as exc:
        if exc.name not in {
            "apps.onboarding_tools",
            "apps.onboarding_tools.services",
        }:
            raise
        unavailable = ToolOnboardingState(
            source_status=ToolSourceStatus.UNAVAILABLE,
            items=(),
        )
        return {user.pk: unavailable for user in users}
    return module.bulk_agent_onboarding_states(users)


def microsoft_user_ids(users: list[User]) -> set[int]:
    from allauth.socialaccount.models import SocialAccount

    user_ids = [user.pk for user in users]
    return set(
        SocialAccount.objects.filter(user_id__in=user_ids, provider="microsoft")
        .values_list("user_id", flat=True)
        .distinct()
    )


def _case_for(user: User) -> UserOnboardingCase | None:
    try:
        return user.onboarding_case  # ty: ignore[unresolved-attribute]
    except UserOnboardingCase.DoesNotExist:
        return None


def _related_rows(case: UserOnboardingCase | None, relation: str) -> list[Any]:
    if case is None:
        return []
    cache = getattr(case, "_prefetched_objects_cache", {})
    if relation in cache:
        return list(cache[relation])
    return list(getattr(case, relation).all())


def _tool_payloads(case: UserOnboardingCase | None) -> tuple[dict[str, Any], ...]:
    stored = {item.tool: item for item in _related_rows(case, "tool_setups")}
    payloads = []
    for value, label in OnboardingToolSetup.Tool.choices:
        item = stored.get(value)
        state = item.state if item else OnboardingToolSetup.State.NOT_STARTED
        if state in {
            OnboardingToolSetup.State.READY,
            OnboardingToolSetup.State.NOT_REQUIRED,
        }:
            status = MilestoneStatus.COMPLETE
        elif state == OnboardingToolSetup.State.BLOCKED:
            status = MilestoneStatus.BLOCKED
        else:
            status = MilestoneStatus.PENDING
        payloads.append(
            {
                "key": value,
                "label": label,
                "state": state,
                "status": status,
                "statusLabel": milestone_status_payload(status)["label"],
                "tone": milestone_status_payload(status)["tone"],
                "updatedAt": item.updated_at.isoformat() if item else None,
                "updatedBy": str(item.updated_by) if item else None,
            }
        )
    return tuple(payloads)


def _overall(
    user: User,
    milestones: tuple[SourceMilestone, ...],
    tools: tuple[dict[str, Any], ...],
    tasks: tuple[OnboardingTask, ...],
) -> tuple[str, tuple[dict[str, str], ...]]:
    blockers: list[dict[str, str]] = []
    if not user.is_active:
        blockers.append({"key": "account_inactive", "label": "Account is disabled"})
    if user.office is None:
        blockers.append({"key": "office_missing", "label": "Office is not assigned"})
    if user.start_date is None:
        blockers.append({"key": "start_date_missing", "label": "Start date is missing"})
    source_blocker_keys: set[str] = set()
    for item in milestones:
        if item.status not in {MilestoneStatus.BLOCKED, MilestoneStatus.UNAVAILABLE}:
            continue
        key = (
            f"{item.source}_source_unavailable"
            if item.status == MilestoneStatus.UNAVAILABLE
            else item.key
        )
        if key in source_blocker_keys:
            continue
        source_blocker_keys.add(key)
        blockers.append({"key": key, "label": item.detail})
    blockers.extend(
        {"key": f"tool_{item['key']}", "label": f"{item['label']} is blocked"}
        for item in tools
        if item["status"] == MilestoneStatus.BLOCKED
    )
    blockers.extend(
        {"key": f"task_{task.pk}", "label": task.title}
        for task in tasks
        if task.is_blocking
    )
    if blockers:
        return OverallStatus.BLOCKED, tuple(blockers)
    every_complete = all(
        item.status == MilestoneStatus.COMPLETE for item in milestones
    ) and all(item["status"] == MilestoneStatus.COMPLETE for item in tools)
    if every_complete and not tasks:
        return OverallStatus.READY, ()
    any_complete = any(
        item.status == MilestoneStatus.COMPLETE for item in milestones
    ) or any(item["status"] == MilestoneStatus.COMPLETE for item in tools)
    return (
        OverallStatus.IN_PROGRESS if any_complete else OverallStatus.NOT_STARTED
    ), ()


def _profile_journey_status(user: User) -> ProfileJourneyStatus:
    if user.profile_completed:
        return ProfileJourneyStatus.COMPLETE
    partial_fields = (
        user.phone_number,
        user.street_address,
        user.city,
        user.state,
        user.zip_code,
        user.headshot,
    )
    if any(bool(value) for value in partial_fields):
        return ProfileJourneyStatus.IN_PROGRESS
    return ProfileJourneyStatus.NOT_STARTED


def _office_journey_status(
    user: User,
    case: UserOnboardingCase | None,
) -> OfficeJourneyStatus:
    if case and (case.office_confirmed_at or case.required_setup_completed_at):
        return OfficeJourneyStatus.CONFIRMED
    if user.office_id:  # ty: ignore[unresolved-attribute]
        return OfficeJourneyStatus.SELECTED
    return OfficeJourneyStatus.NOT_SELECTED


def _journey_blockers(
    *,
    user: User,
    profile_status: ProfileJourneyStatus,
    office_status: OfficeJourneyStatus,
    case: UserOnboardingCase | None,
    contract: ContractOnboardingState,
    training: TrainingOnboardingState,
    tools: ToolOnboardingState,
    tasks: tuple[OnboardingTask, ...],
) -> tuple[dict[str, str], ...]:
    blockers: list[dict[str, str]] = []
    if profile_status != ProfileJourneyStatus.COMPLETE:
        blockers.append(
            {
                "key": "profile_incomplete",
                "message": "Finish the required profile details to continue.",
            }
        )
    if office_status == OfficeJourneyStatus.NOT_SELECTED:
        blockers.append(
            {
                "key": "office_not_selected",
                "message": "Choose the oNEST office you will work from.",
            }
        )
    elif office_status == OfficeJourneyStatus.SELECTED:
        blockers.append(
            {
                "key": "office_not_confirmed",
                "message": "Review and confirm your selected office.",
            }
        )
    if (
        case
        and case.office_handoff_state
        == UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED
    ):
        blockers.append(
            {
                "key": "office_handoff_failed",
                "message": "Your office handoff needs administrator attention.",
            }
        )
    if contract.journey_status == ContractJourneyStatus.BLOCKED:
        blockers.append(
            {
                "key": "contract_blocked",
                "message": "Your contract needs administrator attention.",
            }
        )
    elif contract.journey_status == ContractJourneyStatus.UNAVAILABLE:
        blockers.append(
            {
                "key": "contract_unavailable",
                "message": "Contract progress is not available yet.",
            }
        )
    if training.status == MilestoneStatus.BLOCKED:
        blockers.append(
            {
                "key": "training_blocked",
                "message": "Required training needs administrator attention.",
            }
        )
    elif training.status == MilestoneStatus.UNAVAILABLE:
        blockers.append(
            {
                "key": "training_unavailable",
                "message": "Training progress is temporarily unavailable.",
            }
        )
    if tools.source_status == ToolSourceStatus.UNAVAILABLE:
        blockers.append(
            {
                "key": "tools_unavailable",
                "message": "Tool setup progress is temporarily unavailable.",
            }
        )
    blockers.extend(
        {
            "key": f"tool_{item.key}_blocked",
            "message": f"{item.label} setup needs administrator attention.",
        }
        for item in tools.items
        if item.required and item.status == MilestoneStatus.BLOCKED
    )
    if any(task.is_blocking for task in tasks):
        blockers.append(
            {
                "key": "activation_task_blocked",
                "message": "An onboarding task needs administrator attention.",
            }
        )
    if not user.is_active:
        blockers.append(
            {
                "key": "account_inactive",
                "message": "Your Hub account needs administrator attention.",
            }
        )
    return tuple(blockers)


def _compose_journey(
    *,
    user: User,
    case: UserOnboardingCase | None,
    contract: ContractOnboardingState,
    training: TrainingOnboardingState,
    tools: ToolOnboardingState,
    tasks: tuple[OnboardingTask, ...],
) -> AgentOnboardingJourney:
    profile_status = _profile_journey_status(user)
    office_status = _office_journey_status(user, case)
    required_setup_complete = bool(
        (case and case.required_setup_completed_at) or user.profile_completed
    )
    handoff_status = (
        UserOnboardingCase.OfficeHandoffState(case.office_handoff_state)
        if case
        else UserOnboardingCase.OfficeHandoffState.PENDING
    )
    required_tools_complete = all(
        item.complete for item in tools.items if item.required
    )
    activation_complete = bool(
        required_setup_complete
        and handoff_status == UserOnboardingCase.OfficeHandoffState.NOTIFIED
        and contract.journey_status == ContractJourneyStatus.ACTIVE
        and training.status == MilestoneStatus.COMPLETE
        and tools.source_status == ToolSourceStatus.AVAILABLE
        and required_tools_complete
        and not any(task.is_blocking for task in tasks)
        and user.is_active
    )
    if profile_status != ProfileJourneyStatus.COMPLETE:
        current_step = JourneyStep.PROFILE
        next_action = JourneyAction.COMPLETE_PROFILE
    elif office_status != OfficeJourneyStatus.CONFIRMED:
        current_step = JourneyStep.OFFICE
        next_action = JourneyAction.CONFIRM_OFFICE
    elif activation_complete:
        current_step = JourneyStep.COMPLETE
        next_action = JourneyAction.NONE
    else:
        current_step = JourneyStep.ACTIVATION
        if handoff_status != UserOnboardingCase.OfficeHandoffState.NOTIFIED:
            next_action = JourneyAction.WAIT_FOR_OFFICE
        elif any(
            item.required and not item.complete and item.self_service
            for item in tools.items
        ):
            next_action = JourneyAction.SET_UP_TOOL
        else:
            next_action = JourneyAction.WAIT_FOR_ACTIVATION

    updated_candidates = [
        user.profile_completed_at,
        user.last_login,
        user.date_joined,
        case.updated_at if case else None,
        case.office_handoff_updated_at if case else None,
        contract.generated.updated_at,
        contract.signed.updated_at,
        contract.active.updated_at,
        training.milestone.updated_at,
        *(item.updated_at for item in tools.items),
    ]
    updated_at = max(item for item in updated_candidates if item is not None)
    return AgentOnboardingJourney(
        profile_status=profile_status,
        profile_updated_at=user.profile_completed_at,
        office_status=office_status,
        office_updated_at=case.office_confirmed_at if case else None,
        office_handoff_status=handoff_status,
        office_handoff_updated_at=(case.office_handoff_updated_at if case else None),
        contract_status=contract.journey_status,
        contract_updated_at=contract.active.updated_at,
        tools=tools,
        required_setup_complete=required_setup_complete,
        activation_complete=activation_complete,
        current_step=current_step,
        next_action=next_action,
        blockers=_journey_blockers(
            user=user,
            profile_status=profile_status,
            office_status=office_status,
            case=case,
            contract=contract,
            training=training,
            tools=tools,
            tasks=tasks,
        ),
        version=journey_version(user, case),
        updated_at=updated_at,
    )


def journey_version(user: User, case: UserOnboardingCase | None) -> str:
    changed_at = case.updated_at if case else user.date_joined
    return f"{user.onboarding_version}:{changed_at.isoformat()}"


def build_onboarding_states(
    users: list[User],
) -> list[OnboardingState]:
    """Build every state with a fixed number of bulk source queries."""
    contracts = contract_states(users)
    training = training_states(users)
    tool_sources = tool_states(users)
    microsoft_ids = microsoft_user_ids(users)
    states = []
    for user in users:
        case = _case_for(user)
        contract = contracts[user.pk]
        training_state = training[user.pk]
        profile = SourceMilestone(
            key="profile",
            label="Profile complete",
            status=(
                MilestoneStatus.COMPLETE
                if user.profile_completed
                else MilestoneStatus.PENDING
            ),
            source="profile",
            detail=(
                "Required profile details are complete."
                if user.profile_completed
                else "Required profile details are still missing."
            ),
            updated_at=user.profile_completed_at,
        )
        sso = SourceMilestone(
            key="microsoft_login",
            label="Microsoft login",
            status=(
                MilestoneStatus.COMPLETE
                if user.pk in microsoft_ids
                else MilestoneStatus.PENDING
            ),
            source="microsoft",
            detail=(
                "Microsoft SSO is connected."
                if user.pk in microsoft_ids
                else "The user has not completed Microsoft SSO."
            ),
            updated_at=user.last_login,
        )
        milestones = (
            profile,
            sso,
            contract.generated,
            contract.signed,
            contract.active,
            training_state.milestone,
        )
        tasks = tuple(
            task
            for task in _related_rows(case, "tasks")
            if task.status == OnboardingTask.Status.OPEN
        )
        tools = _tool_payloads(case)
        overall, blockers = _overall(user, milestones, tools, tasks)
        journey = _compose_journey(
            user=user,
            case=case,
            contract=contract,
            training=training_state,
            tools=tool_sources[user.pk],
            tasks=tasks,
        )
        states.append(
            OnboardingState(
                user=user,
                case=case,
                milestones=milestones,
                contract=contract,
                training=training_state,
                overall_status=overall,
                blockers=blockers,
                open_tasks=tasks,
                tool_setups=tools,
                journey=journey,
            )
        )
    return states


def _correction(actor: User, user: User, source: str) -> dict[str, str] | None:
    destinations = {
        "profile": ("user.view_user_administration", "user_administration", (user.pk,)),
        "contract": ("web.view_agent_contracts", "admin_agent_contracts", ()),
        "training": ("web.manage_training", "admin_training", ()),
        "microsoft": ("web.view_it_support", "admin_it_support", ()),
    }
    permission, route_name, args = destinations[source]
    if not has_effective_permission(actor, permission):
        return None
    return {"label": "Open correction workflow", "href": reverse(route_name, args=args)}


def state_payload(
    actor: User, state: OnboardingState, *, detail: bool
) -> dict[str, Any]:
    complete, total = state.completion
    user = state.user
    case = state.case
    journey_payload = agent_journey_payload(state.journey)
    if actor.pk != user.pk and not has_effective_permission(
        actor, "web.view_agent_contracts"
    ):
        journey_payload["contract"] = {
            "state": str(ContractJourneyStatus.UNAVAILABLE),
            "label": "Unavailable",
            "updatedAt": None,
        }
    payload: dict[str, Any] = {
        "user": {
            "id": user.pk,
            "name": str(user),
            "email": user.email,
            "office": user.office.name if user.office else None,
            "region": user.office.region_name() if user.office else None,
            "startDate": user.start_date.isoformat() if user.start_date else None,
            "isActive": user.is_active,
        },
        "owner": (
            {"id": case.owner.pk, "name": str(case.owner)}
            if case and case.owner
            else None
        ),
        "overallStatus": state.overall_status,
        "overall": overall_status_payload(state.overall_status),
        "blockers": list(state.blockers),
        "progress": {"complete": complete, "total": total},
        "contractStatus": state.contract.status,
        "contract": milestone_status_payload(state.contract.status),
        "trainingStatus": state.training.status,
        "training": milestone_status_payload(state.training.status),
        "openTaskCount": len(state.open_tasks),
        "version": case.updated_at.isoformat() if case else "",
        "lastChangedAt": case.updated_at.isoformat() if case else None,
        "lastChangedBy": str(case.updated_by) if case and case.updated_by else None,
        "requiredSetupComplete": state.journey.required_setup_complete,
        "activationComplete": state.journey.activation_complete,
        "currentStep": str(state.journey.current_step),
        "journeyVersion": state.journey.version,
        "journeyUpdatedAt": state.journey.updated_at.isoformat(),
        "journey": journey_payload,
    }
    if not detail:
        return payload
    payload.update(
        {
            "milestones": [
                milestone.payload(
                    correction=_correction(actor, user, milestone.source)
                    if milestone.source
                    in {"profile", "contract", "training", "microsoft"}
                    else None
                )
                for milestone in state.milestones
            ],
            "tools": list(state.tool_setups),
            "tasks": [
                {
                    "id": task.pk,
                    "title": task.title,
                    "dueOn": task.due_on.isoformat() if task.due_on else None,
                    "isBlocking": task.is_blocking,
                    "createdAt": task.created_at.isoformat(),
                    "createdBy": str(task.created_by),
                }
                for task in state.open_tasks
            ],
            "eligibleNotices": [
                *state.contract.eligible_notices,
                *state.training.eligible_notices,
            ],
            "editable": has_effective_permission(actor, MANAGE_PERMISSION)
            and actor.pk != user.pk,
        }
    )
    return payload


def _journey_status_payload(value: StrEnum, labels: dict[Any, str]) -> dict[str, str]:
    return {"state": str(value), "label": labels[value]}


def agent_journey_payload(journey: AgentOnboardingJourney) -> dict[str, Any]:
    """Versioned, camelCase, self-safe journey contract for agent surfaces."""
    profile = _journey_status_payload(
        journey.profile_status,
        {
            ProfileJourneyStatus.NOT_STARTED: "Not started",
            ProfileJourneyStatus.IN_PROGRESS: "In progress",
            ProfileJourneyStatus.COMPLETE: "Complete",
        },
    )
    office = _journey_status_payload(
        journey.office_status,
        {
            OfficeJourneyStatus.NOT_SELECTED: "Not selected",
            OfficeJourneyStatus.SELECTED: "Selected",
            OfficeJourneyStatus.CONFIRMED: "Confirmed",
        },
    )
    handoff = {
        "state": str(journey.office_handoff_status),
        "label": str(journey.office_handoff_status.label),
    }
    return {
        "schemaVersion": 1,
        "profile": {
            **profile,
            "updatedAt": (
                journey.profile_updated_at.isoformat()
                if journey.profile_updated_at
                else None
            ),
        },
        "office": {
            **office,
            "updatedAt": (
                journey.office_updated_at.isoformat()
                if journey.office_updated_at
                else None
            ),
        },
        "officeHandoff": {
            **handoff,
            "updatedAt": (
                journey.office_handoff_updated_at.isoformat()
                if journey.office_handoff_updated_at
                else None
            ),
        },
        "contract": {
            **_journey_status_payload(
                journey.contract_status,
                {
                    ContractJourneyStatus.GENERATED: "Generated",
                    ContractJourneyStatus.SENT: "Sent",
                    ContractJourneyStatus.SIGNED: "Signed",
                    ContractJourneyStatus.ACTIVE: "Active",
                    ContractJourneyStatus.BLOCKED: "Blocked",
                    ContractJourneyStatus.UNAVAILABLE: "Unavailable",
                },
            ),
            "updatedAt": (
                journey.contract_updated_at.isoformat()
                if journey.contract_updated_at
                else None
            ),
        },
        "toolsSource": str(journey.tools.source_status),
        "tools": [
            {
                "key": item.key,
                "label": item.label,
                "description": item.description,
                "provisioning": item.provisioning,
                "provisioningLabel": item.provisioning_label,
                "selfService": item.self_service,
                "required": item.required,
                "state": item.state,
                "stateLabel": item.state_label,
                "status": str(item.status),
                "statusLabel": milestone_status_payload(item.status)["label"],
                "invitationState": str(item.invitation_status),
                "invitationLabel": item.invitation_label,
                "complete": item.complete,
                "updatedAt": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in journey.tools.items
        ],
        "requiredSetupComplete": journey.required_setup_complete,
        "activationComplete": journey.activation_complete,
        "strictGateActive": not journey.required_setup_complete,
        "currentStep": _current_step_payload(journey.current_step),
        "nextAction": _next_action_payload(journey.next_action),
        "version": journey.version,
        "updatedAt": journey.updated_at.isoformat(),
        "blockers": list(journey.blockers),
    }


def _current_step_payload(step: JourneyStep) -> dict[str, str]:
    labels = {
        JourneyStep.PROFILE: "Profile",
        JourneyStep.OFFICE: "Office",
        JourneyStep.ACTIVATION: "Activation",
        JourneyStep.COMPLETE: "Complete",
    }
    return {"code": str(step), "label": labels[step]}


def _next_action_payload(action: JourneyAction) -> dict[str, Any]:
    definitions: dict[JourneyAction, tuple[str, str | None]] = {
        JourneyAction.COMPLETE_PROFILE: ("Continue profile setup", "onboarding"),
        JourneyAction.CONFIRM_OFFICE: ("Review your office", "onboarding"),
        JourneyAction.SET_UP_TOOL: ("Continue tool setup", "my_tools"),
        JourneyAction.WAIT_FOR_OFFICE: (
            "Your office administrator is handling the next steps",
            None,
        ),
        JourneyAction.WAIT_FOR_ACTIVATION: (
            "Your activation is still in progress",
            None,
        ),
        JourneyAction.NONE: ("Onboarding complete", None),
    }
    label, route_name = definitions[action]
    return {
        "code": str(action),
        "label": label,
        "href": reverse(route_name) if route_name else None,
        "method": "get" if route_name else None,
    }


def journey_for_user(user: User) -> AgentOnboardingJourney:
    """Load and compose one agent journey with a bounded query budget."""
    prepared = (
        User.objects.select_related(
            "office",
            "office__region",
            "onboarding_case",
            "onboarding_case__owner",
            "onboarding_case__updated_by",
        )
        .prefetch_related("onboarding_case__tasks", "onboarding_case__tool_setups")
        .get(pk=user.pk)
    )
    return build_onboarding_states([prepared])[0].journey


def overall_status_options() -> list[dict[str, str]]:
    return [
        {"value": OverallStatus.NOT_STARTED, "label": "Not started"},
        {"value": OverallStatus.IN_PROGRESS, "label": "In progress"},
        {"value": OverallStatus.BLOCKED, "label": "Blocked"},
        {"value": OverallStatus.READY, "label": "Ready"},
    ]


def overall_status_payload(value: str) -> dict[str, str]:
    presentations = {
        OverallStatus.NOT_STARTED: ("Not started", "neutral"),
        OverallStatus.IN_PROGRESS: ("In progress", "info"),
        OverallStatus.BLOCKED: ("Blocked", "destructive"),
        OverallStatus.READY: ("Ready", "success"),
    }
    label, tone = presentations[OverallStatus(value)]
    return {"value": value, "label": label, "tone": tone}


def milestone_status_payload(value: str) -> dict[str, str]:
    presentations = {
        MilestoneStatus.COMPLETE: ("Complete", "success"),
        MilestoneStatus.PENDING: ("Pending", "warning"),
        MilestoneStatus.BLOCKED: ("Blocked", "destructive"),
        MilestoneStatus.UNAVAILABLE: ("Source unavailable", "neutral"),
    }
    label, tone = presentations[MilestoneStatus(value)]
    return {"value": value, "label": label, "tone": tone}
