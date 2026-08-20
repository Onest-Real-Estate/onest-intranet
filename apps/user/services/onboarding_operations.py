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
    OnboardingToolSetup,
    User,
    UserOnboardingCase,
    UserRoleAssignment,
)
from apps.user.roles import ADMIN, BRANCH_MANAGER, REGION_MANAGER, ScopeType
from apps.user.services.agent_administration import administered_user_queryset
from apps.user.services.onboarding_state import MANAGE_PERMISSION
from apps.user.services.role_assignments import has_effective_permission


class StaleOnboardingVersion(Exception):
    message = (
        "Somebody else changed this onboarding record. Reload it to review "
        "their change before trying again."
    )


class SourceActionUnavailable(ValidationError):
    pass


def _target(actor: User, user: User) -> AuditTarget:
    return AuditTarget(
        target_type=UserOnboardingCase._meta.label_lower,
        target_id=str(user.pk),
        target_label=user.email,
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
        "owner", "updated_by"
    )


def _lock_case(user: User, expected_version: str) -> UserOnboardingCase:
    case = locked_case_queryset().filter(user=user).first()
    if case is None:
        if expected_version:
            raise StaleOnboardingVersion()
        case = UserOnboardingCase.objects.create(user=user)
    elif case.updated_at.isoformat() != (expected_version or ""):
        raise StaleOnboardingVersion()
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


@transaction.atomic
def update_tool_setup(
    *,
    actor: User,
    user: User,
    tool: str,
    state: str,
    expected_version: str,
) -> bool:
    ensure_manage_authority(actor, user)
    if tool not in OnboardingToolSetup.Tool.values:
        raise ValidationError({"tool": "Choose an approved onboarding tool."})
    if state not in OnboardingToolSetup.State.values:
        raise ValidationError({"state": "Choose an approved setup state."})
    case = _lock_case(user, expected_version)
    setup = (
        OnboardingToolSetup.objects.select_for_update()
        .filter(case=case, tool=tool)
        .first()
    )
    before = setup.state if setup else OnboardingToolSetup.State.NOT_STARTED
    if before == state:
        return False
    if setup is None:
        setup = OnboardingToolSetup.objects.create(
            case=case, tool=tool, state=state, updated_by=actor
        )
    else:
        setup.state = state
        setup.updated_by = actor
        setup.save(update_fields=["state", "updated_by", "updated_at"])
    _touch(case, actor)
    log_event(
        "user.onboarding.tool_setup_changed",
        actor=actor_from_user(actor),
        target=_target(actor, user),
        before={"tool": tool, "state": before},
        after={"tool": tool, "state": state},
        office_id=user.office.stable_key if user.office else "",
        channel="onboarding_workspace",
    )
    _publish(
        "user.onboarding.tool_setup_changed",
        actor,
        user,
        {"tool": tool, "state": state},
    )
    return True


def resend_notice(
    *,
    actor: User,
    user: User,
    source: str,
    notice: str,
    idempotency_key: str,
) -> None:
    """Delegate to the owning source, which re-checks permission and dedupes."""
    ensure_manage_authority(actor, user)
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
        user=user,
        notice=notice,
        idempotency_key=idempotency_key,
    )
    log_event(
        "user.onboarding.notice_resent",
        actor=actor_from_user(actor),
        target=_target(actor, user),
        after={"source": source, "notice": notice},
        office_id=user.office.stable_key if user.office else "",
        channel="onboarding_workspace",
        metadata={"idempotency_key": idempotency_key},
    )
    _publish(
        "user.onboarding.notice_resent",
        actor,
        user,
        {"source": source, "notice": notice},
    )
