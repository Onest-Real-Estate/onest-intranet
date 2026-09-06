"""Ticket notices, and the resolver that keeps them honest over time.

Two halves:

* :func:`queue_ticket_notice` turns a lifecycle event into notification rows.
  It runs after commit, so it never announces a change that rolled back.
* :func:`resolve_ticket_notifications` is asked, every time somebody opens
  their inbox, whether each notice still refers to something they may see.
  That is what makes revocation work: a notice about a ticket stops resolving
  the moment it leaves the reader's scope, without anything going back to
  rewrite delivered rows.

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

logger = logging.getLogger("apps.it_support")

SOURCE_MODULE = "it_support"
RECORD_TYPE = "support_ticket"

#: What each event says to the **requester**. Anything not listed is silent
#: for them: a ticket moving between two staff-internal states is not news,
#: and a notice per move trains people to ignore the inbox.
_REQUESTER_COPY: dict[str, str] = {
    "created": "We received your IT request",
    "assigned": "Your IT request has an owner",
    "staff_replied": "IT replied to your request",
    "status:waiting_user": "IT needs more information from you",
    "status:resolved": "Your IT request was resolved",
    "status:closed": "Your IT request was closed",
}

#: What each event says to the **desk**. Assignment is addressed to the person
#: who received it; the rest reach whoever is already on the ticket.
_STAFF_COPY: dict[str, str] = {
    "created": "New IT request",
    "escalated": "An IT request was raised to urgent",
    "user_replied": "A requester replied on an IT ticket",
}

_HIGH_PRIORITY = frozenset({"escalated", "status:waiting_user"})


def queue_ticket_notice(
    *, ticket_id: int, event: str, dedupe_key: str, actor_id: int | None = None
) -> int:
    """Deliver the notices this event warrants. Returns rows created.

    Safe to call twice with the same ``dedupe_key``: delivery is keyed per
    recipient and the second call creates nothing. That is what lets the
    caller schedule this from ``transaction.on_commit`` without worrying about
    a retried request.
    """
    from apps.it_support.models import SupportTicket
    from apps.notifications.service import deliver_many

    ticket = (
        SupportTicket.objects.filter(pk=ticket_id)
        .select_related("submitter", "about_user", "assignee")
        .first()
    )
    if ticket is None:
        return 0

    requests: list[NotificationRequest] = []
    priority = (
        NotificationPriority.HIGH
        if event in _HIGH_PRIORITY
        else NotificationPriority.NORMAL
    )

    def add(recipient_id: int | None, title: str) -> None:
        # The person who did it already knows.
        if not recipient_id or recipient_id == actor_id:
            return
        if any(request.recipient_id == recipient_id for request in requests):
            return
        requests.append(
            NotificationRequest(
                recipient_id=recipient_id,
                notification_type=NotificationType.ADMINISTRATIVE,
                event_key=dedupe_key,
                title=f"{title} · {ticket.reference}",
                # Per recipient, so one person's read state never suppresses
                # another's delivery.
                dedupe_key=f"{dedupe_key}:{recipient_id}",
                priority=priority,
                source_module=SOURCE_MODULE,
                source_record_type=RECORD_TYPE,
                source_record_id=str(ticket.public_id),
            )
        )

    requester_copy = _REQUESTER_COPY.get(event)
    if requester_copy:
        add(ticket.submitter_pk, requester_copy)
        # The agent a ticket was raised *about* is waiting on it too.
        add(ticket.about_user_pk, requester_copy)

    staff_copy = _STAFF_COPY.get(event)
    if staff_copy:
        # Only the person who owns it. Fanning "new ticket" out to every
        # grant-holder would make the inbox the thing people mute first; the
        # queue itself is where unassigned work is found.
        add(ticket.assignee_pk, staff_copy)

    if not requests:
        return 0

    created = deliver_many(requests)
    logger.info(
        "it_support: %s notice for %s reached %d of %d recipients",
        event,
        ticket.reference,
        created,
        len(requests),
    )
    return created


def resolve_ticket_notifications(user, notifications: Sequence) -> dict:
    """Whether each notice still points at something this reader may open.

    Re-runs the module's own scope filter rather than trusting the notification
    row, so losing a grant or an office assignment silently retires every
    notice about tickets it covered. One query for the whole page.
    """
    from apps.it_support.models import SupportTicket
    from apps.it_support.taxonomy import SupportPermission
    from apps.web.capability import access_for

    wanted = {str(n.source_record_id) for n in notifications if n.source_record_id}
    if not wanted:
        return {}

    can_triage = user.has_perm(SupportPermission.TRIAGE)
    visible = {
        str(public_id): (reference, status)
        for public_id, reference, status in SupportTicket.objects.for_reader(
            user, access=access_for(user), can_triage=can_triage
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
            # Being in `visible` *is* the statement that the detail page will
            # admit this reader.
            action_available=True,
        )
    return resolved


register_resolver(SOURCE_MODULE, resolve_ticket_notifications)
