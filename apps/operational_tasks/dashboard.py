"""Team-tasks dashboard widget.

A view of the queue at `operational_tasks`, gated on the same permission the
page is gated on. `TaskQuerySet.for_reader` is the module's single visibility
gate and decides reach; nothing here filters in Python afterwards.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone

from apps.operational_tasks.models import OperationalTask
from apps.operational_tasks.taxonomy import (
    STATUS_LABELS,
    TaskPermission,
    TaskPriority,
)
from apps.web.capability import has_capability
from apps.web.dashboard.envelope import ProviderResult, empty, ready
from apps.web.dashboard.providers import DashboardContext

_MAX_ROWS = 5

_PRIORITY_TONE = {
    TaskPriority.CRITICAL: "destructive",
    TaskPriority.HIGH: "warning",
    TaskPriority.NORMAL: "info",
    TaskPriority.LOW: "neutral",
}


def _due_label(task: OperationalTask, *, now) -> str:
    if task.due_at is None:
        return "No due date"
    local = timezone.localtime(task.due_at)
    if task.due_at < now:
        return f"Overdue · {local:%b %-d}"
    return f"Due {local:%b %-d}"


def team_tasks(context: DashboardContext) -> ProviderResult:
    """Live operational tasks inside the reader's effective scope."""
    user = context.user
    access = context.access
    # The same grant the tasks page enforces. A panel admitted by a different
    # permission would link every row into a 403.
    if not has_capability(user, TaskPermission.VIEW, access=access):
        return empty(
            "No team tasks in scope",
            "Operational tasks appear here once you can read them.",
        )

    queryset = (
        OperationalTask.objects.for_reader(user, access=access)
        .active()
        .select_related("assignee", "office")
    )
    total = queryset.count()
    if total == 0:
        return empty(
            "Nothing open",
            "Operational tasks in your scope appear here while they are live.",
            action_label="Open team tasks",
            action_href=reverse("operational_tasks"),
        )

    rows = []
    # Overdue and urgent first. `due_at` nulls sort last so a dated task always
    # outranks an undated one at the same priority.
    for task in queryset.order_by("priority", "due_at", "pk")[:_MAX_ROWS]:
        assignee = task.assignee
        overdue = task.due_at is not None and task.due_at < context.now
        rows.append(
            {
                "id": str(task.public_id),
                "title": task.title,
                "subtitle": (
                    assignee.get_full_name() or assignee.email
                    if assignee
                    else "Unassigned"
                ),
                "meta": _due_label(task, now=context.now),
                "badge": (
                    "Overdue"
                    if overdue
                    else str(STATUS_LABELS.get(task.status, task.status))
                ),
                "tone": (
                    "destructive"
                    if overdue
                    else _PRIORITY_TONE.get(task.priority, "neutral")
                ),
                "href": reverse("operational_task_detail", args=[str(task.public_id)]),
            }
        )

    return ready(
        {
            "total": total,
            "rows": rows,
            "viewAllHref": reverse("operational_tasks"),
        }
    )
