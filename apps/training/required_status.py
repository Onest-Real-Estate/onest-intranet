"""Deterministic required-training status for onboarding and dashboards."""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.training.audience import Kind, visible_training_content
from apps.training.models import TrainingAudience, TrainingContent, TrainingProgress
from apps.training.taxonomy import VERSION_POLICY_ANY, VERSION_POLICY_CURRENT
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import normalize_role_code

Status = TrainingProgress.Status


def live_required_queryset(user: User, *, at=None):
    """Visible, required, currently live training for one learner."""
    return (
        visible_training_content(user, at=at)
        .filter(is_required=True)
        .select_related("category", "owner_office")
        .order_by("display_order", "title", "pk")
    )


def _completed_content_ids(user: User, content_ids: list[int]) -> set[int]:
    if not content_ids:
        return set()
    return set(
        TrainingProgress.objects.filter(
            user=user,
            content_id__in=content_ids,
            status=Status.COMPLETED,
        ).values_list("content_id", flat=True)
    )


def _family_completed(
    *,
    content: TrainingContent,
    completed_ids: set[int],
    family_completed_ids: dict[object, set[int]],
) -> bool:
    policy = content.version_completion_policy
    if policy == VERSION_POLICY_ANY:
        return bool(family_completed_ids.get(content.version_family))
    return content.pk in completed_ids


def is_content_satisfied(
    user: User,
    content: TrainingContent,
    *,
    completed_ids: set[int] | None = None,
) -> bool:
    """Whether ``user`` has satisfied ``content`` under its version policy."""
    if completed_ids is None:
        if content.version_completion_policy == VERSION_POLICY_ANY:
            return TrainingProgress.objects.filter(
                user=user,
                content__version_family=content.version_family,
                status=Status.COMPLETED,
            ).exists()
        return TrainingProgress.objects.filter(
            user=user,
            content=content,
            status=Status.COMPLETED,
        ).exists()
    if content.version_completion_policy == VERSION_POLICY_ANY:
        return (
            content.pk in completed_ids
            or TrainingProgress.objects.filter(
                user=user,
                content__version_family=content.version_family,
                status=Status.COMPLETED,
            ).exists()
        )
    return content.pk in completed_ids


def required_training_summary(user: User, *, at=None) -> dict[str, Any]:
    """Single-user required-training summary for library and dashboard."""
    moment = at or timezone.now()
    required = list(live_required_queryset(user, at=moment))
    required_count = len(required)
    if required_count == 0:
        return {
            "requiredCount": 0,
            "completedCount": 0,
            "percent": 100,
            "remainingCount": 0,
            "nextItem": None,
        }

    content_ids = [row.pk for row in required]
    families = {row.version_family for row in required}
    completed_ids = _completed_content_ids(user, content_ids)

    any_policy_families = {
        row.version_family
        for row in required
        if row.version_completion_policy == VERSION_POLICY_ANY
    }
    family_hits: dict[object, set[int]] = {family: set() for family in families}
    if any_policy_families:
        for content_id, family in TrainingProgress.objects.filter(
            user=user,
            status=Status.COMPLETED,
            content__version_family__in=any_policy_families,
        ).values_list("content_id", "content__version_family"):
            family_hits.setdefault(family, set()).add(content_id)

    completed_count = 0
    next_item = None
    for row in required:
        satisfied = _family_completed(
            content=row,
            completed_ids=completed_ids,
            family_completed_ids=family_hits,
        )
        if satisfied:
            completed_count += 1
        elif next_item is None:
            next_item = {
                "id": row.pk,
                "title": row.title,
                "detailUrl": f"/training-learning/{row.pk}",
            }

    percent = int(round((completed_count / required_count) * 100))
    return {
        "requiredCount": required_count,
        "completedCount": completed_count,
        "percent": percent,
        "remainingCount": required_count - completed_count,
        "nextItem": next_item,
    }


def _office_parent_map() -> dict[int, int | None]:
    return dict(Office.objects.values_list("pk", "parent_id"))


def _office_chain_ids(
    office_id: int | None, parent_map: dict[int, int | None]
) -> frozenset[int]:
    if office_id is None:
        return frozenset()
    chain: list[int] = []
    seen: set[int] = set()
    node: int | None = office_id
    while node is not None and node not in seen:
        seen.add(node)
        chain.append(node)
        node = parent_map.get(node)
    return frozenset(chain)


def _live_roles_by_user(user_ids: list[int], *, at) -> dict[int, frozenset[str]]:
    if not user_ids:
        return {}
    rows = (
        UserRoleAssignment.objects.filter(user_id__in=user_ids)
        .exclude(status=UserRoleAssignment.Status.REVOKED)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=at))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=at))
        .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=at))
        .values_list("user_id", "role")
    )
    by_user: dict[int, set[str]] = {uid: set() for uid in user_ids}
    for user_id, role in rows:
        code = normalize_role_code(role) or role
        by_user.setdefault(user_id, set()).add(code)
    return {uid: frozenset(roles) for uid, roles in by_user.items()}


def _audience_matches(
    *,
    kind: str,
    role: str,
    office_id: int | None,
    target_user_id: int | None,
    user_id: int,
    user_office_id: int | None,
    office_chain_ids: frozenset[int],
    role_codes: frozenset[str],
) -> bool:
    if kind == Kind.COMPANY:
        return True
    if kind == Kind.ROLE:
        code = normalize_role_code(role) or role
        return code in role_codes
    if kind == Kind.REGION:
        return office_id is not None and office_id in office_chain_ids
    if kind == Kind.OFFICE:
        return office_id is not None and office_id == user_office_id
    if kind == Kind.USER:
        return target_user_id is not None and target_user_id == user_id
    return False


def _state_for_counts(required_count: int, completed_count: int):
    from apps.user.services.onboarding_state import (
        MilestoneStatus,
        SourceMilestone,
        TrainingOnboardingState,
    )

    if required_count == 0:
        status = MilestoneStatus.COMPLETE
        detail = "No required training is assigned."
    elif completed_count >= required_count:
        status = MilestoneStatus.COMPLETE
        detail = f"Completed {completed_count} of {required_count} required items."
    elif completed_count > 0:
        status = MilestoneStatus.PENDING
        detail = f"Completed {completed_count} of {required_count} required items."
    else:
        status = MilestoneStatus.PENDING
        detail = f"{required_count} required training item(s) remaining."

    return TrainingOnboardingState(
        status=status,
        required_count=required_count,
        completed_count=completed_count,
        milestone=SourceMilestone(
            key="required_training",
            label="Required training",
            status=status,
            source="training",
            detail=detail,
        ),
    )


def bulk_required_training_states(users: list[User]) -> dict[int, Any]:
    """Bulk adapter for onboarding with a fixed query budget.

    Queries (independent of batch size):
    1. live required published content
    2. audience selectors for that content
    3. office parent map (ancestor chains in memory)
    4. live role assignments for the batch
    5. completed progress rows for the batch
    """
    if not users:
        return {}

    moment = timezone.now()
    user_ids = [user.pk for user in users]

    required = list(
        TrainingContent.objects.published()
        .within_window(now=moment)
        .filter(is_required=True)
        .order_by("display_order", "title", "pk")
    )
    if not required:
        return {user.pk: _state_for_counts(0, 0) for user in users}

    content_ids = [row.pk for row in required]
    audiences = list(
        TrainingAudience.objects.filter(content_id__in=content_ids).values_list(
            "content_id", "kind", "role", "office_id", "user_id"
        )
    )
    selectors_by_content: dict[int, list[tuple]] = {pk: [] for pk in content_ids}
    for content_id, kind, role, office_id, target_user_id in audiences:
        selectors_by_content.setdefault(content_id, []).append(
            (kind, role, office_id, target_user_id)
        )

    parent_map = _office_parent_map()
    roles_by_user = _live_roles_by_user(user_ids, at=moment)

    completed_rows = list(
        TrainingProgress.objects.filter(
            user_id__in=user_ids,
            status=Status.COMPLETED,
        ).values_list("user_id", "content_id", "content__version_family")
    )
    completed_by_user: dict[int, set[int]] = {uid: set() for uid in user_ids}
    family_by_user: dict[int, dict[object, set[int]]] = {uid: {} for uid in user_ids}
    for user_id, content_id, family in completed_rows:
        completed_by_user.setdefault(user_id, set()).add(content_id)
        family_by_user.setdefault(user_id, {}).setdefault(family, set()).add(content_id)

    result = {}
    for user in users:
        office = getattr(user, "office", None)
        office_id = office.pk if office is not None else None
        chain = _office_chain_ids(office_id, parent_map)
        role_codes = roles_by_user.get(user.pk, frozenset())
        visible: list[TrainingContent] = []
        for row in required:
            selectors = selectors_by_content.get(row.pk, [])
            if not selectors:
                continue
            if any(
                _audience_matches(
                    kind=kind,
                    role=role,
                    office_id=sel_office_id,
                    target_user_id=target_user_id,
                    user_id=user.pk,
                    user_office_id=office_id,
                    office_chain_ids=chain,
                    role_codes=role_codes,
                )
                for kind, role, sel_office_id, target_user_id in selectors
            ):
                visible.append(row)

        completed_ids = completed_by_user.get(user.pk, set())
        family_hits = family_by_user.get(user.pk, {})
        completed_count = sum(
            1
            for row in visible
            if _family_completed(
                content=row,
                completed_ids=completed_ids,
                family_completed_ids=family_hits,
            )
        )
        result[user.pk] = _state_for_counts(len(visible), completed_count)
    return result


def family_satisfied_q(user: User, content: TrainingContent) -> Q:
    """ORM filter fragment: whether the user has a satisfying completion."""
    if content.version_completion_policy == VERSION_POLICY_CURRENT:
        return Q(
            user=user,
            content=content,
            status=Status.COMPLETED,
        )
    return Q(
        user=user,
        content__version_family=content.version_family,
        status=Status.COMPLETED,
    )
