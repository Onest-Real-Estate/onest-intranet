"""Explicit, audited mutations for operational onboarding coordination."""

from __future__ import annotations

from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.events import publish
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import (
    OnboardingTask,
    User,
    UserOnboardingCase,
    UserRoleAssignment,
)
from apps.user.roles import ADMIN, BRANCH_MANAGER, REGION_MANAGER, ScopeType
from apps.user.services.agent_administration import administered_user_queryset
from apps.user.services.onboarding_state import MANAGE_PERMISSION
from apps.user.services.onboarding_state import journey_version as journey_version_token
from apps.user.services.role_assignments import has_effective_permission


class StaleOnboardingVersion(Exception):
    message = (
        "Somebody else changed this onboarding record. Reload it to review "
        "their change before trying again."
    )


class SourceActionUnavailable(ValidationError):
    pass


class StaleJourneyVersion(Exception):
    message = "Your onboarding changed in another session. Reload before continuing."


HANDOFF_TRANSITIONS = {
    UserOnboardingCase.OfficeHandoffState.PENDING: frozenset(
        {
            UserOnboardingCase.OfficeHandoffState.NOTIFIED,
            UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED,
        }
    ),
    UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED: frozenset(
        {UserOnboardingCase.OfficeHandoffState.NOTIFIED}
    ),
    UserOnboardingCase.OfficeHandoffState.NOTIFIED: frozenset(),
}


def _target(actor: User, user: User) -> AuditTarget:
    return AuditTarget(
        target_type=UserOnboardingCase._meta.label_lower,
        target_id=str(user.pk),
        target_label=f"User {user.pk}",
    )


def ensure_manage_authority(actor: User, user: User) -> None:
    if actor.pk == user.pk:
        raise PermissionDenied("You cannot manage your own onboarding case.")
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        raise PermissionDenied("You do not have permission to manage onboarding.")
    if not administered_user_queryset(actor).filter(pk=user.pk).exists():
        raise PermissionDenied("That user is outside your onboarding scope.")


def owner_queryset(actor: User, target: User):
    """Managers whose effective assignment reaches the target's office."""
    base = (
        administered_user_queryset(actor).filter(is_active=True).exclude(pk=target.pk)
    )
    if target.office is None:
        return base.filter(is_superuser=True)
    region = target.office.region
    reach = Q(is_superuser=True) | Q(
        role_assignments__role=ADMIN,
        role_assignments__scope_type=ScopeType.COMPANY,
        role_assignments__status=UserRoleAssignment.Status.ACTIVE,
    )
    reach |= Q(
        role_assignments__role=BRANCH_MANAGER,
        role_assignments__scope_type=ScopeType.OFFICE,
        role_assignments__scope_office=target.office,
        role_assignments__status=UserRoleAssignment.Status.ACTIVE,
    )
    if region is not None:
        reach |= Q(
            role_assignments__role=REGION_MANAGER,
            role_assignments__scope_type=ScopeType.REGION,
            role_assignments__scope_office=region,
            role_assignments__status=UserRoleAssignment.Status.ACTIVE,
        )
    return base.filter(reach).distinct().order_by("first_name", "last_name", "email")


def locked_case_queryset():
    """The onboarding case row, locked for update, with its people loaded.

    ``of=("self",)`` is load-bearing: ``owner`` and ``updated_by`` are
    nullable, so ``select_related`` reaches them through LEFT OUTER JOINs, and
    PostgreSQL refuses a bare ``FOR UPDATE`` that spans the nullable side of an
    outer join. SQLite drops row locking altogether, so nothing on a developer
    machine reproduces it — ``test_onboarding_administration`` compiles this
    queryset against the PostgreSQL backend to keep the guarantee testable.
    """
    return UserOnboardingCase.objects.select_for_update(of=("self",)).select_related(
        "user",
        "user__office",
        "user__office__region",
        "owner",
        "updated_by",
    )


def _lock_case(user: User, expected_version: str) -> UserOnboardingCase:
    locked_user = (
        User.objects.select_for_update()
        .select_related("office", "office__region")
        .get(pk=user.pk)
    )
    case = locked_case_queryset().filter(user=locked_user).first()
    if expected_version != journey_version_token(locked_user, case):
        raise StaleOnboardingVersion()
    if case is None:
        case = UserOnboardingCase.objects.create(user=locked_user)
    return case


def _touch(case: UserOnboardingCase, actor: User) -> None:
    case.updated_by = actor
    case.updated_at = timezone.now()
    case.save(update_fields=["updated_by", "updated_at"])


def _publish(name: str, actor: User, user: User, payload: dict) -> None:
    publish(
        name,
        actor_id=str(actor.pk),
        subject=f"user:{user.pk}",
        payload={"user_id": user.pk, **payload},
    )


@transaction.atomic
def complete_required_setup(
    *,
    user: User,
    expected_version: str | None = None,
) -> bool:
    """Release the strict gate once profile and office are durably complete."""
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    case = (
        UserOnboardingCase.objects.select_for_update(of=("self",))
        .filter(user=locked_user)
        .first()
    )
    confirmation_is_current = bool(
        case
        and case.office_confirmed_at
        and getattr(case, "office_confirmed_for_id", None)
        == getattr(locked_user, "office_id", None)
        and case.office_confirmation_version == locked_user.onboarding_version
    )
    if (
        locked_user.profile_completed
        and confirmation_is_current
        and case.required_setup_completed_at
    ):
        return False
    if expected_version is not None and expected_version != journey_version_token(
        locked_user, case
    ):
        raise StaleJourneyVersion()
    if not locked_user.profile_completed:
        raise ValidationError({"profile": "Complete the required profile details."})
    if locked_user.office_id is None:
        raise ValidationError({"office": "Choose an office before continuing."})
    if not confirmation_is_current:
        raise ValidationError(
            {"office": "Review and explicitly confirm your selected office."}
        )

    now = timezone.now()
    assert case is not None
    case.required_setup_completed_at = case.required_setup_completed_at or now
    case.updated_by = locked_user
    case.save()
    log_event(
        "user.onboarding.required_setup_completed",
        actor=actor_from_user(locked_user),
        target=_target(locked_user, locked_user),
        after={
            "onboarding_version": locked_user.onboarding_version,
            "office_id": locked_user.office_id,
        },
        office_id=locked_user.office.stable_key if locked_user.office else "",
        channel="onboarding",
    )
    transaction.on_commit(
        lambda: _publish(
            "user.onboarding.required_setup_completed",
            locked_user,
            locked_user,
            {"onboarding_version": locked_user.onboarding_version},
        )
    )
    return True


@transaction.atomic
def transition_office_handoff(
    *,
    actor: User,
    user: User,
    state: str,
    expected_version: str,
) -> bool:
    """Move the office handoff through its closed, audited transition table."""
    ensure_manage_authority(actor, user)
    try:
        next_state = UserOnboardingCase.OfficeHandoffState(state)
    except ValueError as exc:
        raise ValidationError({"state": "Choose an approved handoff state."}) from exc
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    case = (
        UserOnboardingCase.objects.select_for_update(of=("self",))
        .filter(user=locked_user)
        .first()
    )
    handoff_is_current = bool(
        case
        and getattr(case, "office_handoff_office_id", None)
        == getattr(locked_user, "office_id", None)
        and case.office_handoff_onboarding_version == locked_user.onboarding_version
    )
    current = UserOnboardingCase.OfficeHandoffState(
        case.office_handoff_state
        if case and handoff_is_current
        else UserOnboardingCase.OfficeHandoffState.PENDING
    )
    if current == next_state:
        return False
    if expected_version != journey_version_token(locked_user, case):
        raise StaleJourneyVersion()
    if next_state not in HANDOFF_TRANSITIONS[current]:
        raise ValidationError(
            {"state": "That office handoff transition is not allowed."}
        )
    now = timezone.now()
    if case is None:
        case = UserOnboardingCase(user=locked_user)
    case.office_handoff_state = next_state
    case.office_handoff_updated_at = now
    case.office_handoff_office = locked_user.office
    case.office_handoff_onboarding_version = locked_user.onboarding_version
    case.updated_by = actor
    case.save()
    log_event(
        "user.onboarding.office_handoff_changed",
        actor=actor_from_user(actor),
        target=_target(actor, locked_user),
        before={"state": str(current)},
        after={"state": str(next_state)},
        office_id=locked_user.office.stable_key if locked_user.office else "",
        channel="onboarding_workspace",
    )
    transaction.on_commit(
        lambda: _publish(
            "user.onboarding.office_handoff_changed",
            actor,
            locked_user,
            {"from": str(current), "to": str(next_state)},
        )
    )
    return True


@transaction.atomic
def reset_required_setup(*, actor: User, user: User) -> None:
    """Start a new required-setup cycle without erasing downstream history."""
    if not actor.is_staff and not actor.is_superuser:
        raise PermissionDenied("Only authorized staff may reset onboarding.")
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    previous_version = locked_user.onboarding_version
    locked_user.profile_completed = False
    locked_user.profile_completed_at = None
    locked_user.onboarding_version = previous_version + 1
    locked_user.save(
        update_fields=[
            "profile_completed",
            "profile_completed_at",
            "onboarding_version",
        ]
    )
    case = (
        UserOnboardingCase.objects.select_for_update(of=("self",))
        .filter(user=locked_user)
        .first()
    )
    if case:
        case.office_confirmed_at = None
        case.office_confirmed_for = None
        case.office_confirmation_version = None
        case.required_setup_completed_at = None
        case.updated_by = actor
        case.save(
            update_fields=[
                "office_confirmed_at",
                "office_confirmed_for",
                "office_confirmation_version",
                "required_setup_completed_at",
                "updated_by",
                "updated_at",
            ]
        )
    log_event(
        "user.onboarding.reset",
        actor=actor_from_user(actor),
        target=_target(actor, locked_user),
        before={"onboarding_version": previous_version},
        after={"onboarding_version": locked_user.onboarding_version},
        office_id=locked_user.office.stable_key if locked_user.office else "",
        channel="admin",
    )


@transaction.atomic
def assign_owner(
    *, actor: User, user: User, owner: User | None, expected_version: str
) -> bool:
    ensure_manage_authority(actor, user)
    if (
        owner is not None
        and not owner_queryset(actor, user).filter(pk=owner.pk).exists()
    ):
        raise ValidationError({"owner": "That owner cannot reach this user."})
    case = _lock_case(user, expected_version)
    before_id = case.owner.pk if case.owner else None
    if before_id == (owner.pk if owner else None):
        return False
    case.owner = owner
    case.save(update_fields=["owner"])
    _touch(case, actor)
    after_id = owner.pk if owner else None
    log_event(
        "user.onboarding.owner_assigned",
        actor=actor_from_user(actor),
        target=_target(actor, user),
        before={"owner_id": before_id},
        after={"owner_id": after_id},
        office_id=user.office.stable_key if user.office else "",
        channel="onboarding_workspace",
    )
    _publish(
        "user.onboarding.owner_assigned",
        actor,
        user,
        {"owner_id": after_id},
    )
    return True


@transaction.atomic
def create_task(
    *,
    actor: User,
    user: User,
    title: str,
    due_on: date | None,
    is_blocking: bool,
    expected_version: str,
) -> OnboardingTask:
    ensure_manage_authority(actor, user)
    normalized = " ".join(title.split())
    if not normalized:
        raise ValidationError({"title": "Enter a task."})
    if len(normalized) > 200:
        raise ValidationError({"title": "Keep the task under 200 characters."})
    case = _lock_case(user, expected_version)
    task = OnboardingTask.objects.create(
        case=case,
        title=normalized,
        due_on=due_on,
        is_blocking=is_blocking,
        created_by=actor,
    )
    _touch(case, actor)
    log_event(
        "user.onboarding.task_created",
        actor=actor_from_user(actor),
        target=_target(actor, user),
        after={
            "task_id": task.pk,
            "due_on": due_on,
            "is_blocking": is_blocking,
        },
        office_id=user.office.stable_key if user.office else "",
        channel="onboarding_workspace",
    )
    _publish(
        "user.onboarding.task_changed",
        actor,
        user,
        {"task_id": task.pk, "status": task.status},
    )
    return task


@transaction.atomic
def resolve_task(
    *,
    actor: User,
    user: User,
    task_id: int,
    expected_version: str,
) -> bool:
    ensure_manage_authority(actor, user)
    case = _lock_case(user, expected_version)
    task = (
        OnboardingTask.objects.select_for_update().filter(pk=task_id, case=case).first()
    )
    if task is None:
        raise ValidationError({"task": "That task is not part of this case."})
    if task.status == OnboardingTask.Status.RESOLVED:
        return False
    task.status = OnboardingTask.Status.RESOLVED
    task.resolved_by = actor
    task.resolved_at = timezone.now()
    task.save(update_fields=["status", "resolved_by", "resolved_at", "updated_at"])
    _touch(case, actor)
    log_event(
        "user.onboarding.task_resolved",
        actor=actor_from_user(actor),
        target=_target(actor, user),
        before={"task_id": task.pk, "status": OnboardingTask.Status.OPEN},
        after={"task_id": task.pk, "status": task.status},
        office_id=user.office.stable_key if user.office else "",
        channel="onboarding_workspace",
    )
    _publish(
        "user.onboarding.task_changed",
        actor,
        user,
        {"task_id": task.pk, "status": task.status},
    )
    return True


def _locked_tool_context(*, user: User, tool: str, expected_version: str):
    from apps.onboarding_tools.models import OnboardingTool

    case = _lock_case(user, expected_version)
    locked_user = case.user
    if not (
        locked_user.profile_completed
        and case.required_setup_completed_at
        and case.office_confirmed_at
        and getattr(case, "office_confirmed_for_id", None)
        == getattr(locked_user, "office_id", None)
        and case.office_confirmation_version == locked_user.onboarding_version
    ):
        raise ValidationError(
            {
                "tool": (
                    "Tool actions unlock after the agent completes their profile "
                    "and confirms their current office."
                )
            }
        )
    catalog_tool = (
        OnboardingTool.objects.for_office(locked_user.office).filter(slug=tool).first()
    )
    if catalog_tool is None:
        raise ValidationError(
            {"tool": "That tool is inactive or no longer applies to this office."}
        )
    return case, locked_user, catalog_tool


@transaction.atomic
def perform_tool_action(
    *,
    actor: User,
    user: User,
    tool: str,
    action: str,
    expected_version: str,
    reason: str = "",
) -> bool:
    """Run a source-owned catalog action under onboarding scope and versioning.

    The onboarding layer neither owns nor accepts a free-form tool state. It
    locks the case, revalidates the agent's current office, and delegates the
    stable action code to the catalog lifecycle.
    """
    from apps.onboarding_tools.models import AgentToolStatus, ToolState
    from apps.onboarding_tools.services import (
        ToolWorkspaceAction,
        perform_workspace_action,
    )

    ensure_manage_authority(actor, user)
    case, locked_user, catalog_tool = _locked_tool_context(
        user=user,
        tool=tool,
        expected_version=expected_version,
    )
    before = (
        AgentToolStatus.objects.filter(agent=locked_user, tool=catalog_tool)
        .values_list("state", flat=True)
        .first()
        or ToolState.NOT_STARTED
    )
    result = perform_workspace_action(
        actor=actor,
        agent=locked_user,
        tool=catalog_tool,
        action=action,
        reason=reason,
    )
    command = ToolWorkspaceAction(action)
    if command == ToolWorkspaceAction.RETRY_NOTIFICATION:
        _touch(case, actor)
        log_event(
            "user.onboarding.tool_notice_retried",
            actor=actor_from_user(actor),
            target=_target(actor, locked_user),
            after={"tool": catalog_tool.slug, "deliveries": int(result)},
            office_id=(locked_user.office.stable_key if locked_user.office else ""),
            channel="onboarding_workspace",
        )
        return True
    if result.state == before:
        return False
    _touch(case, actor)
    return True


@transaction.atomic
def initiate_contract(*, actor: User, user: User, expected_version: str):
    """Delegate contract creation while keeping the case token consistent."""
    from apps.contract.services import initiate_onboarding_contract

    ensure_manage_authority(actor, user)
    case = _lock_case(user, expected_version)
    locked_user = case.user
    contract, created = initiate_onboarding_contract(actor, recipient=locked_user)
    if not created:
        return contract, False
    _touch(case, actor)
    log_event(
        "user.onboarding.contract_initiated",
        actor=actor_from_user(actor),
        target=_target(actor, locked_user),
        after={"contract_id": str(contract.public_id)},
        office_id=locked_user.office.stable_key if locked_user.office else "",
        channel="onboarding_workspace",
    )
    return contract, True


@transaction.atomic
def resend_notice(
    *,
    actor: User,
    user: User,
    source: str,
    notice: str,
    idempotency_key: str,
    expected_version: str,
) -> None:
    """Delegate to the owning source, which re-checks permission and dedupes."""
    ensure_manage_authority(actor, user)
    case = _lock_case(user, expected_version)
    locked_user = case.user
    module_name = {
        "contract": "apps.contract.services",
        "training": "apps.training.services",
    }.get(source)
    if module_name is None:
        raise ValidationError({"source": "That source cannot send notices."})
    try:
        module = __import__(module_name, fromlist=["resend_onboarding_notice"])
    except ModuleNotFoundError as exc:
        if exc.name not in {module_name, module_name.rpartition(".")[0]}:
            raise
        raise SourceActionUnavailable(
            f"The {source} source is not connected, so no notice was sent."
        ) from exc
    module.resend_onboarding_notice(
        actor=actor,
        user=locked_user,
        notice=notice,
        idempotency_key=idempotency_key,
    )
    log_event(
        "user.onboarding.notice_resent",
        actor=actor_from_user(actor),
        target=_target(actor, locked_user),
        after={"source": source, "notice": notice},
        office_id=locked_user.office.stable_key if locked_user.office else "",
        channel="onboarding_workspace",
        metadata={"idempotency_key": idempotency_key},
    )
    _publish(
        "user.onboarding.notice_resent",
        actor,
        locked_user,
        {"source": source, "notice": notice},
    )
    _touch(case, actor)
