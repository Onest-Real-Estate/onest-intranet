"""Course module authoring and rollup completion."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.training.administration import assert_can_author
from apps.training.audience import visible_training_content
from apps.training.models import TrainingContent, TrainingModule, TrainingProgress
from apps.training.progress_service import mark_completed, touch_progress
from apps.training.taxonomy import (
    CONTENT_TYPE_COURSE,
    PROGRESS_SOURCE_COURSE_ROLLUP,
)
from apps.user.models import User

Status = TrainingProgress.Status


class CourseError(ValidationError):
    """Domain validation for course mutations."""


@transaction.atomic
def save_modules(
    *,
    actor: User,
    course: TrainingContent,
    child_ids: list[int],
) -> list[TrainingModule]:
    assert_can_author(actor, course.owner_office)
    if course.status != TrainingContent.Status.DRAFT:
        raise CourseError({"content": ["Modules can only change on drafts."]})
    if course.content_type != CONTENT_TYPE_COURSE:
        raise CourseError({"content": ["This item is not a course."]})

    unique_ids: list[int] = []
    seen: set[int] = set()
    for raw in child_ids:
        child_id = int(raw)
        if child_id == course.pk:
            raise CourseError({"modules": ["A course cannot include itself."]})
        if child_id in seen:
            continue
        seen.add(child_id)
        unique_ids.append(child_id)

    children = {
        row.pk: row
        for row in TrainingContent.objects.filter(pk__in=unique_ids).select_related(
            "owner_office"
        )
    }
    if len(children) != len(unique_ids):
        raise CourseError({"modules": ["One or more modules were not found."]})

    TrainingModule.objects.filter(course=course).delete()
    rows = []
    for index, child_id in enumerate(unique_ids):
        rows.append(
            TrainingModule(
                course=course,
                child=children[child_id],
                sort_order=index,
            )
        )
    return TrainingModule.objects.bulk_create(rows)


def course_rollup(user: User, course: TrainingContent) -> dict[str, Any]:
    modules = list(
        TrainingModule.objects.filter(course=course)
        .select_related("child")
        .order_by("sort_order", "pk")
    )
    if not modules:
        return {"total": 0, "completed": 0, "percent": 0, "modules": []}

    visible_ids = set(
        visible_training_content(user)
        .filter(pk__in=[m.child_id for m in modules])
        .values_list("pk", flat=True)
    )
    visible_modules = [m for m in modules if m.child_id in visible_ids]
    completed_ids = set(
        TrainingProgress.objects.filter(
            user=user,
            content_id__in=[m.child_id for m in visible_modules],
            status=Status.COMPLETED,
        ).values_list("content_id", flat=True)
    )
    total = len(visible_modules)
    completed = sum(1 for m in visible_modules if m.child_id in completed_ids)
    percent = int(round((completed / total) * 100)) if total else 0
    return {
        "total": total,
        "completed": completed,
        "percent": percent,
        "modules": [
            {
                "id": m.child_id,
                "completed": m.child_id in completed_ids,
            }
            for m in visible_modules
        ],
    }


@transaction.atomic
def maybe_complete_course(
    user: User, course: TrainingContent
) -> TrainingProgress | None:
    """Mark a course complete when every visible module is complete."""
    if course.content_type != CONTENT_TYPE_COURSE:
        return None
    rollup = course_rollup(user, course)
    if rollup["total"] == 0:
        return None
    if rollup["completed"] < rollup["total"]:
        touch_progress(
            user,
            course,
            status=Status.IN_PROGRESS,
            source=PROGRESS_SOURCE_COURSE_ROLLUP,
            progress_percent=rollup["percent"],
            evidence={"rollup": rollup},
        )
        return None
    return mark_completed(
        user,
        course,
        source=PROGRESS_SOURCE_COURSE_ROLLUP,
        evidence={"rollup": rollup},
        progress_percent=100,
    )


def admin_modules_payload(content: TrainingContent) -> list[dict[str, Any]]:
    return [
        {
            "id": module.child.pk,
            "title": module.child.title,
            "contentType": module.child.content_type,
            "sortOrder": module.sort_order,
        }
        for module in TrainingModule.objects.filter(course=content)
        .select_related("child")
        .order_by("sort_order", "pk")
    ]
