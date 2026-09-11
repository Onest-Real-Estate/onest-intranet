"""Feedback-signals dashboard widget.

A window on the triage queue at `admin_feedback`. `FeedbackQuerySet.for_reader`
is the module's single visibility gate and the same triage rule the queue page
applies decides how wide the reader's reach is here.
"""

from __future__ import annotations

from django.urls import reverse

from apps.feedback.models import FeedbackTicket
from apps.feedback.taxonomy import (
    CATEGORY_LABELS,
    STATUS_LABELS,
    FeedbackPermission,
    FeedbackPriority,
)
from apps.web.capability import has_capability
from apps.web.dashboard.envelope import ProviderResult, empty, ready
from apps.web.dashboard.providers import DashboardContext

_MAX_ROWS = 5

_PRIORITY_TONE = {
    FeedbackPriority.CRITICAL: "destructive",
    FeedbackPriority.HIGH: "warning",
    FeedbackPriority.NORMAL: "info",
    FeedbackPriority.LOW: "neutral",
}


def feedback_signals(context: DashboardContext) -> ProviderResult:
    """Open feedback inside the reader's triage reach."""
    user = context.user
    access = context.access
    if not has_capability(user, FeedbackPermission.VIEW, access=access):
        return empty(
            "No feedback in scope",
            "Reports from colleagues appear here once you can read them.",
        )

    # Exactly the queue page's rule: office reach only buys somebody else's
    # report for a triager. Without the grant a reader sees their own reports,
    # which is what "my feedback" already is.
    can_triage = has_capability(user, FeedbackPermission.TRIAGE, access=access)
    queryset = (
        FeedbackTicket.objects.for_reader(user, access=access, can_triage=can_triage)
        .open()
        .select_related("submitter")
    )

    total = queryset.count()
    if total == 0:
        return empty(
            "Nothing open",
            "Feedback you can act on appears here while it is open.",
            action_label="Open the feedback queue",
            action_href=reverse("admin_feedback"),
        )

    rows = []
    for ticket in queryset.order_by("priority", "created_at", "pk")[:_MAX_ROWS]:
        submitter = ticket.submitter
        rows.append(
            {
                "id": str(ticket.public_id),
                "title": ticket.summary,
                "subtitle": (
                    submitter.get_full_name() or submitter.email
                    if submitter
                    else ticket.reference
                ),
                "meta": str(CATEGORY_LABELS.get(ticket.category, ticket.category)),
                "badge": str(STATUS_LABELS.get(ticket.status, ticket.status)),
                "tone": _PRIORITY_TONE.get(ticket.priority, "neutral"),
                "href": reverse("feedback_detail", args=[str(ticket.public_id)]),
            }
        )

    return ready(
        {
            "total": total,
            "rows": rows,
            "viewAllHref": reverse("admin_feedback"),
        }
    )
