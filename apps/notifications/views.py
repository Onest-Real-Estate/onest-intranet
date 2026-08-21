"""The notification centre and the endpoints its rows drive.

Every view here is self-scoped. None of them accepts a recipient identifier,
and the one that takes an object id resolves it through the signed-in
reader's own queryset — so a notification belonging to somebody else answers
exactly like one that does not exist.
"""

from __future__ import annotations

from typing import cast
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.notifications import service
from apps.notifications.contract import TYPE_LABELS
from apps.notifications.forms import (
    ACTION_ARCHIVE,
    ACTION_READ,
    ACTION_UNREAD,
    NotificationStateForm,
)
from apps.notifications.payloads import serialize_page
from apps.notifications.queries import (
    NotificationFilters,
    build_page,
    parse_filters,
    parse_page,
    priority_options,
    status_options,
    type_options,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response

__all__ = [
    "notification_center",
    "notification_state",
    "notification_read_all",
    "notification_summary",
]


def _center_href(filters: NotificationFilters, page: int) -> str:
    """The centre, with the reader's own filters restored.

    Always built from ``reverse`` plus values that survived validation, so a
    mutation can never be talked into redirecting off-site.
    """
    query = {key: value for key, value in filters.as_payload().items() if value}
    if page > 1:
        query["page"] = str(page)
    path = reverse("notifications")
    return f"{path}?{urlencode(query)}" if query else path


def _center_props(
    request: HttpRequest, *, params=None, errors: dict | None = None
) -> dict[str, object]:
    reader = cast(User, request.user)
    now = timezone.now()
    source = request.GET if params is None else params
    filters = parse_filters(source)
    page = build_page(reader, filters=filters, page=parse_page(source), now=now)
    unread_by_type = service.type_counts(reader, now=now)
    return {
        # Not "notifications": that key is the shell's badge payload, shared
        # with every page. A page prop of the same name would shadow it and
        # blank the header count on this page alone.
        "notificationList": list_response(
            serialize_page(reader, page.rows, now=now),
            page=page.page,
            page_size=page.page_size,
            total_items=page.total,
            filters=filters.as_payload(),
        ),
        "filterOptions": {
            "status": status_options(),
            "type": type_options(),
            "priority": priority_options(),
        },
        "summary": service.unread_summary(reader, now=now),
        "unreadByType": {key: unread_by_type.get(key, 0) for key in TYPE_LABELS},
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("notifications")
@require_GET
@inertia("Notifications")
def notification_center(request: HttpRequest):
    return _center_props(request)


@enforce_policy("notification_state")
@require_POST
def notification_state(request: HttpRequest, public_id) -> HttpResponse:
    """Mark one notification read, unread, or archived. Idempotent.

    Repeating an action that has already been applied is a success, not an
    error: two tabs, a retried request, and an impatient double click must all
    end in the same state.
    """
    reader = cast(User, request.user)
    filters = parse_filters(request.POST)
    page = parse_page(request.POST)
    form = NotificationStateForm(request.POST)
    if not form.is_valid():
        return _error_response(request, "That action is not supported.")

    action = form.cleaned_data["action"]
    try:
        if action == ACTION_READ:
            found = service.mark_read(reader, public_id)
        elif action == ACTION_UNREAD:
            found = service.mark_unread(reader, public_id)
        else:
            found = service.archive(reader, public_id)
    except service.MandatoryAcknowledgementRequired as exc:
        return _error_response(request, "; ".join(exc.messages))
    if not found:
        # Not a 404 page: the reader's own list simply no longer contains it,
        # and saying more would confirm that the id exists for somebody else.
        return redirect(_center_href(filters, page))
    if action == ACTION_ARCHIVE:
        # An archived row leaves the current page; landing on a page that no
        # longer exists would show an empty list, so go back to the first.
        page = 1
    return redirect(_center_href(filters, page))


@enforce_policy("notification_read_all")
@require_POST
def notification_read_all(request: HttpRequest) -> HttpResponse:
    """Clear the badge. Mandatory notifications are left for the reader."""
    service.mark_all_read(cast(User, request.user))
    return redirect(_center_href(parse_filters(request.POST), 1))


@enforce_policy("notification_summary")
@require_GET
def notification_summary(request: HttpRequest) -> JsonResponse:
    """Badge counts for the header, polled by the shell.

    Answers only about the caller. There is no parameter that could ask about
    anybody else, and no aggregate that could describe an office.
    """
    return JsonResponse(service.unread_summary(cast(User, request.user)))


def _error_response(request: HttpRequest, message: str) -> HttpResponse:
    """Re-render the centre with the message, keeping the reader's filters.

    422 rather than a redirect with a flash: the reason a mutation was refused
    belongs to the response that refused it.
    """
    response = render(
        request,
        "Notifications",
        _center_props(
            request, params=request.POST, errors={"fields": {}, "form": [message]}
        ),
    )
    response.status_code = 422
    return response
