"""Canonical, source-owned onboarding state for every product surface.

The list, workspace, dashboard metric, user detail, and future assistants must
call this module instead of reconstructing milestone rules.  Operational rows
live in ``UserOnboardingCase``; profile, Microsoft SSO, contracts, and training
remain derived from their source domains and are never writable here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
from apps.user.services.agent_administration import administered_user_queryset
from apps.user.services.role_assignments import (
    EffectiveAccess,
    has_effective_permission,
)

VIEW_PERMISSION = "web.view_new_agents"
MANAGE_PERMISSION = "web.manage_new_agent_onboarding"
NEW_AGENT_WINDOW_DAYS = 90


class MilestoneStatus:
    COMPLETE = "complete"
    PENDING = "pending"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class OverallStatus:
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    READY = "ready"


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


def build_onboarding_states(
    users: list[User],
) -> list[OnboardingState]:
    """Build every state with a fixed number of bulk source queries."""
    contracts = contract_states(users)
    training = training_states(users)
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
    label, tone = presentations[value]
    return {"value": value, "label": label, "tone": tone}


def milestone_status_payload(value: str) -> dict[str, str]:
    presentations = {
        MilestoneStatus.COMPLETE: ("Complete", "success"),
        MilestoneStatus.PENDING: ("Pending", "warning"),
        MilestoneStatus.BLOCKED: ("Blocked", "destructive"),
        MilestoneStatus.UNAVAILABLE: ("Source unavailable", "neutral"),
    }
    label, tone = presentations[value]
    return {"value": value, "label": label, "tone": tone}
