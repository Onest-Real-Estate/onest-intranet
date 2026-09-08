"""Dashboard action items for tasks assigned to the signed-in user.

Completion is derived from the task, exactly as the action-item contract
requires: a resolved, closed, or cancelled task simply stops being emitted.
There is no dashboard-side dismissal, and none is wanted — a task is closed by
somebody transitioning it, not by a reader tidying their dashboard.

Only work *assigned to* the reader appears. A manager who can see forty tasks
across three offices is not personally actionable on all of them, and a
dashboard queue that lists other people's work is a queue nobody trusts.
"""

from __future__ import annotations

from django.urls import reverse

from apps.operational_tasks.models import OperationalTask
from apps.operational_tasks.taxonomy import (
    CATEGORY_LABELS,
    TaskPriority,
    TaskStatus,
)
from apps.web.action_items.contract import (
    ActionItem,
    ActionPriority,
    ActionSourceContext,
    ActionType,
)

#: The contract's type enum is closed and has no "task" member. Operational
#: work is administrative follow-up, so it rides the compliance lane, which is
#: the enum's existing home for "somebody must act on this record".
_ACTION_TYPE = ActionType.COMPLIANCE

#: Task priority and action priority use the same ramp, so this is identity
#: today. It is written out anyway: the two are separate contracts owned by
#: separate modules, and a silent coupling would break quietly if either moved.
_PRIORITY_MAP = {
    TaskPriority.CRITICAL: ActionPriority.CRITICAL,
    TaskPriority.HIGH: ActionPriority.HIGH,
    TaskPriority.NORMAL: ActionPriority.NORMAL,
    TaskPriority.LOW: ActionPriority.LOW,
}

#: A blocked or waiting task is not something the assignee can move right now,
#: so it stays off the queue until it comes back to them.
ACTIONABLE_STATUSES = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)


def collect_task_actions(context: ActionSourceContext) -> list[ActionItem]:
    user = context.user
    if getattr(user, "is_anonymous", False):
        return []

    tasks = (
        OperationalTask.objects.filter(assignee=user, status__in=ACTIONABLE_STATUSES)
        .select_related("office")
        .order_by("due_at", "-priority", "pk")[:50]
    )

    items: list[ActionItem] = []
    for task in tasks:
        category = str(CATEGORY_LABELS.get(task.category, "Task"))
        overdue = task.is_overdue(at=context.now)
        context_line = f"{category} · {task.office.name}"
        if overdue:
            context_line = f"Overdue · {context_line}"
        items.append(
            ActionItem(
                id=f"operational_task:{task.public_id}",
                # Keyed on the record, not the status: the same task surfacing
                # again after a status change must collapse onto one row rather
                # than appearing twice.
                dedupe_key=f"operational_task:{task.public_id}",
                title=task.title,
                type=_ACTION_TYPE,
                priority=_PRIORITY_MAP.get(task.priority, ActionPriority.NORMAL),
                due_at=task.due_at,
                source_module="operational_tasks",
                source_record_type="operational_task",
                source_record_id=str(task.public_id),
                context=context_line,
                cta_label="Open task",
                # Reversed, never a literal: the URL is the task module's to
                # own, and it re-authorizes the reader on arrival like every
                # other CTA.
                cta_href=reverse("operational_task_detail", args=[str(task.public_id)]),
                assignee_id=user.pk,
            )
        )
    return items
