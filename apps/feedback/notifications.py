"""Ticket notices, and the resolver that keeps them honest over time.

Two audiences with opposite defaults:

* the **submitter** hears about anything that changes what they should expect —
  a reply, a request for information, a resolution;
* **staff** hear when a ticket is handed to them.

Nobody hears about their own action. Nothing internal ever reaches a notice:
the titles below are generated from the event, never from a note body, so a
staff-only note cannot escape through an email subject line.
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

logger = logging.getLogger("apps.feedback")

SOURCE_MODULE = "feedback"
RECORD_TYPE = "feedback_ticket"

#: Event → what the notice says. An event absent here is silent by design.
_TO_SUBMITTER: dict[str, str] = {
    "status:needs_info": "Support needs more detail on your report",
    "status:resolved": "Your report was resolved",
    "status:closed": "Your report was closed",
    "replied": "Support replied to your report",
}

_TO_ASSIGNEE: dict[str, str] = {
    "assigned": "A support ticket was assigned to you",
}

_PRIORITY = {
    "status:needs_info": NotificationPriority.HIGH,
    "assigned": NotificationPriority.HIGH,
}


def queue_feedback_notice(
    *, ticket_id: int, event: str, dedupe_key: str, actor_id: int | None = None
) -> int:
    """Deliver the notices this event warrants. Returns rows created.

    Safe to call twice with the same key: delivery is keyed per recipient and
    the second call creates nothing.
    """
    from apps.feedback.models import FeedbackTicket
    from apps.notifications.service import deliver_many

    copy = _TO_SUBMITTER.get(event) or _TO_ASSIGNEE.get(event)
    if copy is None:
        return 0

    ticket = (
        FeedbackTicket.objects.filter(pk=ticket_id)
        .select_related("submitter", "assignee")
        .first()
    )
    if ticket is None:
        return 0

    recipients: set[int] = set()
    if event in _TO_SUBMITTER and ticket.submitter_pk:
        recipients.add(ticket.submitter_pk)
    if event in _TO_ASSIGNEE and ticket.assignee_pk:
        recipients.add(ticket.assignee_pk)
    recipients.discard(actor_id)
    if not recipients:
        return 0

    requests = [
        NotificationRequest(
            recipient_id=recipient_id,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key=dedupe_key,
            # The reference, never the summary: a ticket title can quote an
            # error message containing somebody's name, and a notification
            # travels further than the ticket does.
            title=f"{copy} · {ticket.reference}",
            dedupe_key=f"{dedupe_key}:{recipient_id}",
            priority=_PRIORITY.get(event, NotificationPriority.NORMAL),
            source_module=SOURCE_MODULE,
            source_record_type=RECORD_TYPE,
            source_record_id=str(ticket.public_id),
        )
        for recipient_id in sorted(recipients)
    ]
    created = deliver_many(requests)
    logger.info(
        "feedback: %s notice for %s reached %d of %d recipients",
        event,
        ticket.reference,
        created,
        len(requests),
    )
    return created


def resolve_feedback_notifications(user, notifications: Sequence) -> dict:
    """Whether each notice still points at something this reader may open.

    Re-runs the module's own scope filter on every inbox load, so a support
    person who loses the triage grant stops resolving notices about other
    people's tickets — including ones delivered months earlier. One query for
    the whole page.
    """
    from apps.feedback.models import FeedbackTicket
    from apps.web.capability import access_for

    wanted = {str(n.source_record_id) for n in notifications if n.source_record_id}
    if not wanted:
        return {}

    can_triage = user.has_perm("web.triage_feedback")
    visible = {
        str(public_id): (reference, status)
        for public_id, reference, status in FeedbackTicket.objects.for_reader(
            user, access=access_for(user), can_triage=can_triage
        )
        .filter(public_id__in=wanted)
        .values_list("public_id", "reference", "status")
    }

    resolved: dict = {}
    for notification in notifications:
        found = visible.get(str(notification.source_record_id))
        if found is None:
            resolved[notification.public_id] = SourceResolution.unavailable()
            continue
        reference, status = found
        resolved[notification.public_id] = SourceResolution(
            available=True,
            detail=f"{reference} · {status.replace('_', ' ')}",
            action_available=True,
        )
    return resolved


register_resolver(SOURCE_MODULE, resolve_feedback_notifications)
