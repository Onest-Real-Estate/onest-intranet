"""Idempotent training progress writes and admin corrections."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.service import (
    actor_from_user,
    log_on_commit,
    snapshot_model,
    target_from_instance,
)
from apps.training.administration import assert_can_author
from apps.training.audience import assert_visible
from apps.training.models import TrainingContent, TrainingProgress
from apps.training.taxonomy import (
    COMPLETION_COMPLETED,
    COMPLETION_IN_PROGRESS,
    COMPLETION_NOT_STARTED,
    PROGRESS_SOURCE_ADMIN,
    PROGRESS_SOURCE_CODES,
    PROGRESS_SOURCE_LEARNER,
)
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

MANAGE_PERMISSION = "web.manage_training"

AUDIT_FIELDS = (
    "status",
    "started_at",
    "completed_at",
    "progress_percent",
    "content_version_number",
    "is_required_at_completion",
    "source",
)

Status = TrainingProgress.Status


class ProgressError(ValidationError):
    """Domain validation for progress mutations."""


def _normalize_status(status: str) -> str:
    normalized = (status or "").strip()
    if normalized not in {
        COMPLETION_NOT_STARTED,
        COMPLETION_IN_PROGRESS,
        COMPLETION_COMPLETED,
    }:
        raise ProgressError({"status": ["Unknown progress status."]})
    return normalized


def _normalize_source(source: str) -> str:
    normalized = (source or "").strip()
    if normalized not in PROGRESS_SOURCE_CODES:
        raise ProgressError({"source": ["Unknown progress source."]})
    return normalized


def _normalize_percent(progress_percent: int | None) -> int | None:
    if progress_percent is None:
        return None
    if progress_percent < 0 or progress_percent > 100:
        raise ProgressError(
            {"progress_percent": ["Progress percent must be between 0 and 100."]}
        )
    return progress_percent


def _same_state(
    locked: TrainingProgress,
    *,
    status: str,
    progress_percent: int | None,
) -> bool:
    if locked.status != status:
        return False
    return not (
        progress_percent is not None and locked.progress_percent != progress_percent
    )


def _apply_status(
    locked: TrainingProgress,
    *,
    status: str,
    source: str,
    evidence: dict[str, Any] | None,
    progress_percent: int | None,
    content: TrainingContent,
    now,
) -> list[str]:
    updates = ["status", "source", "updated_at", "content_version_number"]
    locked.status = status
    locked.source = source
    locked.content_version_number = content.version_number
    if evidence is not None:
        locked.evidence = evidence
        updates.append("evidence")
    if progress_percent is not None:
        locked.progress_percent = progress_percent
        updates.append("progress_percent")

    if status == Status.IN_PROGRESS and locked.started_at is None:
        locked.started_at = now
        updates.append("started_at")
    if status == Status.COMPLETED:
        if locked.started_at is None:
            locked.started_at = now
            updates.append("started_at")
        locked.completed_at = now
        updates.append("completed_at")
        locked.is_required_at_completion = content.is_required
        updates.append("is_required_at_completion")
        if locked.progress_percent is None or locked.progress_percent < 100:
            locked.progress_percent = 100
            updates.append("progress_percent")
    if status == Status.NOT_STARTED:
        locked.completed_at = None
        locked.started_at = None
        locked.progress_percent = None
        locked.is_required_at_completion = None
        updates.extend(
            [
                "completed_at",
                "started_at",
                "progress_percent",
                "is_required_at_completion",
            ]
        )
    return updates


def _audit_action(status: str, *, correction: bool) -> str:
    if correction:
        return "training.progress_corrected"
    if status == Status.COMPLETED:
        return "training.progress_completed"
    if status == Status.IN_PROGRESS:
        return "training.progress_started"
    return "training.progress_corrected"


@transaction.atomic
def touch_progress(
    user: User,
    content: TrainingContent,
    *,
    status: str,
    source: str,
    evidence: dict[str, Any] | None = None,
    progress_percent: int | None = None,
    actor: User | None = None,
    reason: str = "",
) -> TrainingProgress:
    """Create or update progress for ``user`` on ``content``.

    Same status (and percent when provided) is idempotent: no second audit.
    """
    target_status = _normalize_status(status)
    target_source = _normalize_source(source)
    target_percent = _normalize_percent(progress_percent)
    now = timezone.now()

    locked = (
        TrainingProgress.objects.select_for_update(of=("self",))
        .filter(user=user, content=content)
        .first()
    )
    if locked is None:
        locked = TrainingProgress(
            user=user,
            content=content,
            status=Status.NOT_STARTED,
            source=target_source,
        )
        locked.save()
        locked = (
            TrainingProgress.objects.select_for_update(of=("self",))
            .filter(pk=locked.pk)
            .get()
        )

    if _same_state(locked, status=target_status, progress_percent=target_percent):
        return locked

    before = snapshot_model(locked, fields=list(AUDIT_FIELDS))
    updates = _apply_status(
        locked,
        status=target_status,
        source=target_source,
        evidence=evidence,
        progress_percent=target_percent,
        content=content,
        now=now,
    )
    locked.save(update_fields=updates)
    after = snapshot_model(locked, fields=list(AUDIT_FIELDS))

    audit_actor = actor or user
    correction = target_source == PROGRESS_SOURCE_ADMIN
    metadata: dict[str, Any] = {
        "learner_id": user.pk,
        "content_id": content.pk,
        "status": target_status,
        "source": target_source,
    }
    if reason:
        metadata["reason"] = reason.strip()[:500]
    if evidence:
        metadata["evidence"] = evidence

    log_on_commit(
        _audit_action(target_status, correction=correction),
        actor=actor_from_user(audit_actor),
        target=target_from_instance(locked, label=content.title),
        before=before,
        after=after,
        metadata=metadata,
    )
    if content.is_required:
        from apps.audit.events import publish

        publish(
            "training.onboarding_progress_changed",
            actor_id=str(audit_actor.pk),
            subject=f"user:{user.pk}",
            payload={"user_id": user.pk},
        )
    return locked


def mark_started(
    user: User,
    content: TrainingContent,
    *,
    source: str = PROGRESS_SOURCE_LEARNER,
    evidence: dict[str, Any] | None = None,
) -> TrainingProgress:
    return touch_progress(
        user,
        content,
        status=Status.IN_PROGRESS,
        source=source,
        evidence=evidence,
    )


def mark_completed(
    user: User,
    content: TrainingContent,
    *,
    source: str = PROGRESS_SOURCE_LEARNER,
    evidence: dict[str, Any] | None = None,
    progress_percent: int | None = 100,
) -> TrainingProgress:
    return touch_progress(
        user,
        content,
        status=Status.COMPLETED,
        source=source,
        evidence=evidence,
        progress_percent=progress_percent,
    )


def learner_update_progress(
    user: User,
    content: TrainingContent,
    *,
    action: str,
    progress_percent: int | None = None,
) -> TrainingProgress:
    """Learner-facing mutation: start, complete, or set percent."""
    assert_visible(user, content, reason="progress_out_of_audience")
    normalized = (action or "").strip().lower()
    if normalized == "start":
        return mark_started(user, content, source=PROGRESS_SOURCE_LEARNER)
    if normalized == "complete":
        if content.is_interactive:
            raise ProgressError(
                {
                    "action": [
                        "Interactive content completes through its quiz or session."
                    ]
                }
            )
        return mark_completed(user, content, source=PROGRESS_SOURCE_LEARNER)
    if normalized == "percent":
        if progress_percent is None:
            raise ProgressError({"progress_percent": ["Provide a progress percent."]})
        status = Status.COMPLETED if progress_percent >= 100 else Status.IN_PROGRESS
        return touch_progress(
            user,
            content,
            status=status,
            source=PROGRESS_SOURCE_LEARNER,
            progress_percent=progress_percent,
        )
    raise ProgressError({"action": ["Unknown progress action."]})


def _assert_can_correct(actor: User, learner: User, content: TrainingContent) -> None:
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        raise PermissionDenied("You cannot correct training progress.")
    assert_can_author(actor, content.owner_office)
    from apps.training.audience import targetable_user_queryset

    if not targetable_user_queryset(actor).filter(pk=learner.pk).exists():
        raise PermissionDenied("That learner is outside your training scope.")


@transaction.atomic
def correct_progress(
    *,
    actor: User,
    learner: User,
    content: TrainingContent,
    status: str,
    reason: str,
    progress_percent: int | None = None,
) -> TrainingProgress:
    reason_text = (reason or "").strip()
    if not reason_text:
        raise ProgressError(
            {"reason": ["Explain the correction so the audit trail is useful."]}
        )
    _assert_can_correct(actor, learner, content)
    return touch_progress(
        learner,
        content,
        status=status,
        source=PROGRESS_SOURCE_ADMIN,
        evidence={"reason": reason_text, "corrected_by": actor.pk},
        progress_percent=progress_percent,
        actor=actor,
        reason=reason_text,
    )
