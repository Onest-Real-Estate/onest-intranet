"""Operational tasks as agenda rows — the task appointments in My Day.

A task earns a place on somebody's day only when it has a **due date**: a
deadline is a time-bound obligation, an undated task is a queue item and belongs
in Action Items instead. The two widgets deliberately overlap for dated work and
answer different questions — "what must I act on" versus "what shape is my day".

Scope is the task module's own: rows come from work *assigned to* this reader,
which is a subset of what ``for_reader`` would allow. A manager who can see
forty tasks across three offices does not have forty appointments.
"""

from __future__ import annotations

from django.urls import reverse

from apps.operational_tasks.models import OperationalTask
from apps.operational_tasks.taxonomy import (
    CATEGORY_LABELS,
    TaskPriority,
    TaskStatus,
)
from apps.web.my_day.contract import (
    AgendaEvent,
    EventPriority,
    EventSource,
    EventSourceContext,
)

#: A blocked or waiting task is not something the assignee can act on today, so
#: it is not on their agenda. Terminal work has left the board entirely.
AGENDA_STATUSES = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)

#: Task priority and agenda priority share a ramp, written out rather than
#: assumed: they are separate contracts owned by separate modules, and a silent
#: coupling would break quietly the first time either moved.
_PRIORITY_MAP = {
    TaskPriority.CRITICAL: EventPriority.CRITICAL,
    TaskPriority.HIGH: EventPriority.HIGH,
    TaskPriority.NORMAL: EventPriority.NORMAL,
    TaskPriority.LOW: EventPriority.LOW,
}

#: Bounded so one reader with a large backlog cannot make the dashboard slow.
#: The widget shows a handful; this only has to be a superset of that.
MAX_ROWS = 50


def collect_task_events(context: EventSourceContext) -> list[AgendaEvent]:
    user = context.user
    if getattr(user, "is_anonymous", False):
        return []

    tasks = (
        OperationalTask.objects.filter(
            assignee=user,
            status__in=AGENDA_STATUSES,
            due_at__isnull=False,
            # Everything from the start of the reader's day forward, plus
            # anything already past due — a missed deadline is the row they
            # most need, so the window opens backwards for those alone rather
            # than reaching back indefinitely for everything.
            due_at__lt=context.window_end,
        )
        .select_related("office")
        .order_by("due_at", "priority", "pk")[:MAX_ROWS]
    )

    events: list[AgendaEvent] = []
    for task in tasks:
        due_at = task.due_at
        if due_at is None:
            # The queryset already excludes these; this narrows the type for
            # the checker and keeps the invariant stated where it is relied on
            # rather than only in the filter twenty lines up.
            continue
        category = str(CATEGORY_LABELS.get(task.category, "Task"))
        events.append(
            AgendaEvent(
                id=f"operational_task:{task.public_id}",
                # Keyed on the record, not the status: the same task must
                # collapse to one row rather than reappearing when it moves.
                dedupe_key=f"operational_task:{task.public_id}",
                source=EventSource.TASK,
                title=task.title,
                start_at=due_at,
                # A deadline is an instant, not a span. Giving it a synthetic
                # end would render a duration nobody scheduled.
                end_at=None,
                all_day=False,
                location=task.office.name,
                priority=_PRIORITY_MAP.get(task.priority, EventPriority.NORMAL),
                context=f"{category} · {task.reference}",
                cta_label="Open task",
                # Reversed, and the detail view re-authorizes this reader on
                # arrival — the row is a convenience, never the grant.
                cta_href=reverse("operational_task_detail", args=[str(task.public_id)]),
                source_module="operational_tasks",
                source_record_type="operational_task",
                source_record_id=str(task.public_id),
            )
        )
    return events
