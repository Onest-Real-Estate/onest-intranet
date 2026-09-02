"""Training completion read contract."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.training.models import TrainingContent, TrainingProgress
from apps.training.taxonomy import (
    COMPLETION_COMPLETED,
    COMPLETION_IN_PROGRESS,
    COMPLETION_NOT_STARTED,
)
from apps.user.models import User

Status = TrainingProgress.Status


def completion_state(user: User, content_ids: list[int]) -> dict[int, str]:
    if not content_ids:
        return {}
    rows = TrainingProgress.objects.filter(
        user=user, content_id__in=content_ids
    ).values_list("content_id", "status")
    known = dict(rows)
    return {
        content_id: known.get(content_id, COMPLETION_NOT_STARTED)
        for content_id in content_ids
    }


def apply_completion_filter(
    queryset: QuerySet[TrainingContent],
    user: User,
    *,
    completion: str,
) -> QuerySet[TrainingContent]:
    if completion == COMPLETION_NOT_STARTED:
        started = TrainingProgress.objects.filter(user=user).exclude(
            status=Status.NOT_STARTED
        )
        return queryset.exclude(pk__in=started.values("content_id"))
    if completion in {COMPLETION_IN_PROGRESS, COMPLETION_COMPLETED}:
        matching = TrainingProgress.objects.filter(user=user, status=completion)
        return queryset.filter(pk__in=matching.values("content_id"))
    return queryset


def bulk_agent_onboarding_states(users):
    """Adapter contract for onboarding required-training milestones."""
    from apps.training.required_status import bulk_required_training_states

    return bulk_required_training_states(users)
