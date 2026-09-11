"""Support-queue dashboard widget.

The panel is a *view* of the queue at `admin_it_support`, never a second
authorization path: `TicketQuerySet.for_reader` is the module's single
visibility gate and the same triage rule the queue page applies decides how
wide the reader's reach is here.
"""

from __future__ import annotations

from django.urls import reverse

from apps.it_support.models import SupportTicket
from apps.it_support.taxonomy import (
    STATUS_LABELS,
    SupportPermission,
    SupportPriority,
    SupportStatus,
)
from apps.web.capability import has_capability
from apps.web.dashboard.envelope import ProviderResult, empty, ready
from apps.web.dashboard.providers import DashboardContext

_MAX_ROWS = 5

#: Priority to chip tone. Mirrors the action-item ramp so a ticket cannot look
#: more or less urgent on the dashboard than it does in the queue.
_PRIORITY_TONE = {
    SupportPriority.URGENT: "destructive",
    SupportPriority.HIGH: "warning",
    SupportPriority.NORMAL: "info",
    SupportPriority.LOW: "neutral",
}


def _age_label(ticket: SupportTicket, *, now) -> str:
    days = (now - ticket.created_at).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "1 day old"
    return f"{days} days old"


def support_queue(context: DashboardContext) -> ProviderResult:
    """Open IT tickets inside the reader's support reach."""
    user = context.user
    access = context.access
    if not has_capability(user, SupportPermission.VIEW, access=access):
        return empty(
            "No support queue in scope",
            "Open IT requests appear here once you can read them.",
        )

    # Exactly the queue page's rule: office reach only buys tickets for a
    # triager. Without the grant a reader still sees the requests they raised
    # or that were raised about them, which is a queue of one person's own work
    # and is what the panel then shows.
    can_triage = has_capability(user, SupportPermission.TRIAGE, access=access)
    queryset = (
        SupportTicket.objects.for_reader(user, access=access, can_triage=can_triage)
        .open()
        .select_related("submitter", "assignee")
    )

    total = queryset.count()
    if total == 0:
        return empty(
            "Nothing open",
            "IT requests you can act on appear here while they are open.",
            action_label="Open the support queue",
            action_href=reverse("admin_it_support"),
        )

    rows = []
    # Urgent first, then oldest — the two facts that decide what to pick up.
    for ticket in queryset.order_by("priority", "created_at", "pk")[:_MAX_ROWS]:
        submitter = ticket.submitter
        rows.append(
            {
                "id": str(ticket.public_id),
                "title": ticket.subject,
                "subtitle": (
                    submitter.get_full_name() or submitter.email
                    if submitter
                    else ticket.reference
                ),
                "meta": _age_label(ticket, now=context.now),
                "badge": str(STATUS_LABELS.get(ticket.status, ticket.status)),
                "tone": (
                    "destructive"
                    if ticket.status == SupportStatus.NEW
                    and ticket.priority <= SupportPriority.HIGH
                    else _PRIORITY_TONE.get(ticket.priority, "neutral")
                ),
                "href": reverse("it_support_ticket", args=[str(ticket.public_id)]),
            }
        )

    return ready(
        {
            "total": total,
            "rows": rows,
            "viewAllHref": reverse("admin_it_support"),
        }
    )
