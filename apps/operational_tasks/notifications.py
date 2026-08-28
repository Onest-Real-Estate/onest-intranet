"""Task notices, and the resolver that keeps them honest over time.

Two halves:

* :func:`queue_task_notice` turns a lifecycle event into notification rows.
  It runs after commit, so it never announces a change that rolled back.
* :func:`resolve_task_notifications` is asked, every time somebody opens their
  inbox, whether each notice still refers to something they may see. That is
  what makes revocation work: an old "assigned to you" notice stops resolving
  the moment the task leaves the reader's scope, without anything going back
  to rewrite delivered rows.

Notices use the ``administrative`` notification type rather than a new one.
The type enum is a closed set shared with the preference screen and the inbox
filter, and widening it for one module would be a schema and UI change this
work does not need — the source module is what routes resolution.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from apps.notifications.contract import (
    NotificationPriority,
    NotificationRequest,
    NotificationType,
)
from apps.notifications.sources import SourceResolution, register_resolver

logger = logging.getLogger("apps.operational_tasks")

SOURCE_MODULE = "operational_tasks"
RECORD_TYPE = "operational_task"

#: What each lifecycle event says, and who it is for. Anything not listed here
#: is deliberately silent: a task that moves between two working states is not
#: news, and a notice per drag would train people to ignore the inbox.
_EVENT_COPY: dict[str, str] = {
    "assigned": "A task was assigned to you",
    "status:resolved": "A task you reported was resolved",
    "status:closed": "A task you reported was closed",
    "status:blocked": "A task you reported is blocked",
    "status:waiting": "A task you reported needs your input",
    "commented": "There is a new comment on a task you reported",
}

#: Events the assignee hears about, versus the ones the reporter hears about.
#: Nobody is notified about their own action — the actor already knows.
_TO_ASSIGNEE = frozenset({"assigned"})
_TO_REPORTER = frozenset(
    {
        "status:resolved",
        "status:closed",
        "status:blocked",
        "status:waiting",
        "commented",
    }
)

_PRIORITY = {
    "status:blocked": NotificationPriority.HIGH,
    "status:waiting": NotificationPriority.HIGH,
}


def queue_task_notice(
    *, task_id: int, event: str, dedupe_key: str, actor_id: int | None = None
) -> int:
    """Deliver the notices this event warrants. Returns rows created.

    Safe to call twice with the same ``dedupe_key``: delivery is keyed per
    recipient and the second call creates nothing. That is what lets the
    caller schedule this from ``transaction.on_commit`` without worrying about
    a retried request.
    """
    from apps.notifications.service import deliver_many
    from apps.operational_tasks.models import OperationalTask

    if event not in _EVENT_COPY:
        return 0

    task = (
        OperationalTask.objects.filter(pk=task_id)
        .select_related("assignee", "reporter")
        .first()
    )
    if task is None:
        return 0

    recipients: set[int] = set()
    if event in _TO_ASSIGNEE and task.assignee_pk:
        recipients.add(task.assignee_pk)
    if event in _TO_REPORTER and task.reporter_pk:
        recipients.add(task.reporter_pk)
    # The person who did it already knows.
    recipients.discard(actor_id)
    if not recipients:
        return 0

    requests = [
        NotificationRequest(
            recipient_id=recipient_id,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key=dedupe_key,
            title=f"{_EVENT_COPY[event]} · {task.reference}",
            # Per recipient, so one person's read state never suppresses
            # another's delivery.
            dedupe_key=f"{dedupe_key}:{recipient_id}",
            priority=_PRIORITY.get(event, NotificationPriority.NORMAL),
            source_module=SOURCE_MODULE,
            source_record_type=RECORD_TYPE,
            source_record_id=str(task.public_id),
        )
        for recipient_id in sorted(recipients)
    ]
    created = deliver_many(requests)
    logger.info(
        "operational_tasks: %s notice for %s reached %d of %d recipients",
        event,
        task.reference,
        created,
        len(requests),
    )
    return created


def resolve_task_notifications(user, notifications: Sequence) -> dict:
    """Whether each notice still points at something this reader may open.

    Re-runs the module's own scope filter rather than trusting the notification
    row, so losing an office assignment silently retires every notice about
    tasks in it. One query for the whole page.
    """
    from apps.operational_tasks.models import OperationalTask
    from apps.web.capability import access_for

    wanted = {str(n.source_record_id) for n in notifications if n.source_record_id}
    if not wanted:
        return {}

    access = access_for(user)
    visible = {
        str(public_id): (reference, status)
        for public_id, reference, status in OperationalTask.objects.for_reader(
            user, access=access
        )
        .filter(public_id__in=wanted)
        .values_list("public_id", "reference", "status")
    }

    resolved: dict = {}
    for notification in notifications:
        record_id = str(notification.source_record_id)
        found = visible.get(record_id)
        if found is None:
            resolved[notification.public_id] = SourceResolution.unavailable()
            continue
        reference, status = found
        resolved[notification.public_id] = SourceResolution(
            available=True,
            detail=f"{reference} · {status.replace('_', ' ')}",
            # The detail page is not routed yet; the notice still resolves so
            # the reader sees what it refers to rather than a dead row.
            action_available=False,
        )
    return resolved


register_resolver(SOURCE_MODULE, resolve_task_notifications)
