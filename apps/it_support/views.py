"""The IT support module's HTTP surface.

Two audiences share one detail page and one set of write endpoints:

* a **requester** reading the ticket they raised, and
* a **triager** working the queue.

They are separated by capability flags computed per request, never by which
URL was used — a second detail view would be a second place to get the
internal-note rule wrong.

Two rules, the same ones the feedback and task modules follow:

* **Load through the scoped queryset, never by bare id.** A ticket outside the
  actor's reach is a 404, not a 403 — confirming an id exists is itself a
  disclosure across a scope boundary.
* **Answer the failure the caller actually hit.** A refused field is 422 with
  the messages attached; a row that moved underneath is 409 with the current
  state re-rendered, so the recovery is "read theirs, then reapply mine".
"""

from __future__ import annotations

import logging
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.it_support import services
from apps.it_support.models import SupportTicket
from apps.it_support.payloads import (
    filter_options,
    queue_metrics,
    ticket_detail,
    ticket_row,
)
from apps.it_support.services import ActorContext, ConcurrentUpdate
from apps.it_support.taxonomy import (
    CATEGORY_CODES,
    OPEN_STATUSES,
    PRIORITY_BY_KEY,
    STATUS_CODES,
    ContactMethod,
    SupportPermission,
)
from apps.user.models import Office, User
from apps.web.authorization import enforce_policy, scope_queryset_for_user_office
from apps.web.capability import access_for
from apps.web.contracts import empty_validation_errors, list_response

SUBMIT_PAGE = "ITSupport"
DETAIL_PAGE = "ITSupportTicket"
QUEUE_PAGE = "ITSupportQueue"
PAGE_SIZE = 25

logger = logging.getLogger("apps.it_support")


def _actor(request: HttpRequest) -> ActorContext:
    user = cast(User, request.user)
    return ActorContext(user=user, permissions=frozenset(user.get_all_permissions()))


def _scoped(request: HttpRequest, *, triage: bool):
    """Every read starts here.

    ``triage`` is the *caller's intent*, not a grant: the requester-facing
    pages pass ``False`` so a triager reading their own ticket list sees their
    own tickets, not the whole queue.
    """
    user = cast(User, request.user)
    actor = _actor(request)
    return SupportTicket.objects.for_reader(
        user,
        access=access_for(user),
        can_triage=triage and actor.can_triage,
    ).select_related("office", "submitter", "assignee", "about_user")


def _load(request: HttpRequest, public_id: str, *, triage: bool) -> SupportTicket:
    ticket = _scoped(request, triage=triage).filter(public_id=public_id).first()
    if ticket is None:
        raise Http404("No ticket matches that reference.")
    return ticket


def _capabilities(actor: ActorContext, ticket: SupportTicket | None = None) -> dict:
    """What this actor may do here. Mirrors the service's grants so the UI can
    hide what it may not do. Never the authorization — every write re-checks."""
    return {
        "triage": actor.can_triage,
        "assign": actor.holds(SupportPermission.ASSIGN, SupportPermission.TRIAGE),
        "note": actor.holds(SupportPermission.NOTE, SupportPermission.TRIAGE),
        "reply": bool(ticket and ticket.concerns(actor.user)) or actor.can_triage,
    }


def _assignable(request: HttpRequest) -> list[dict[str, Any]]:
    """People this actor may hand a ticket to.

    Support staff inside the actor's own office reach — scoped *before*
    serialization like every other list, so the picker never becomes a back
    door into a company-wide staff directory. Membership is asked of the
    permission rather than a role name: a role is a bundle that can change,
    and the question is genuinely "could this person work the ticket".
    """
    from django.contrib.auth.models import Permission

    actor = _actor(request)
    if not actor.holds(SupportPermission.ASSIGN, SupportPermission.TRIAGE):
        return []

    permissions = Permission.objects.filter(
        content_type__app_label="web",
        codename__in=("triage_it_support", "assign_it_support"),
    )
    if not permissions.exists():
        return []

    reader = cast(User, request.user)
    candidates = scope_queryset_for_user_office(
        reader,
        User.objects.filter(is_active=True).filter(
            Q(groups__permissions__in=permissions) | Q(user_permissions__in=permissions)
        ),
        field_name="office",
        access=access_for(reader),
    )
    return [
        {"id": person.pk, "name": person.get_full_name() or person.get_short_name()}
        for person in candidates.distinct().order_by("first_name", "last_name", "pk")[
            :100
        ]
    ]


# --------------------------------------------------------------------------- #
# Requester surface
# --------------------------------------------------------------------------- #


def _submit_props(request: HttpRequest, *, errors=None, draft=None) -> dict[str, Any]:
    mine = _scoped(request, triage=False).order_by("-created_at")
    return {
        "tickets": [ticket_row(ticket) for ticket in mine[:50]],
        "openCount": mine.filter(status__in=OPEN_STATUSES).count(),
        "options": filter_options(),
        "draft": draft or {},
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("it_support_submit")
@inertia(SUBMIT_PAGE)
def it_support(request: HttpRequest):
    """Raise a request, and read the ones you already raised.

    No permission gates this page: every authenticated person may report that
    the tool they are told to use is broken.
    """
    return _submit_props(request)


@enforce_policy("it_support_submit")
@require_POST
def ticket_create(request: HttpRequest):
    try:
        ticket, created = services.submit(
            user=request.user,
            subject=request.POST.get("subject") or "",
            description=request.POST.get("description") or "",
            category=(request.POST.get("category") or "").strip(),
            submission_key=request.POST.get("submissionKey") or "",
            preferred_contact=(
                request.POST.get("preferredContact") or ContactMethod.HUB
            ).strip(),
            device_info=request.POST.get("deviceInfo") or "",
            location=request.POST.get("location") or "",
            page_url=request.POST.get("pageUrl") or "",
        )
    except ValidationError as exc:
        response = render(
            request,
            SUBMIT_PAGE,
            _submit_props(request, errors=_errors(exc), draft=_draft(request)),
        )
        response.status_code = 422
        return response

    # A file may ride along with the form. A refused attachment must not lose
    # the ticket the person just wrote, so the ticket is kept and the file is
    # not — logged rather than silently dropped, because "my screenshot
    # vanished" is otherwise unanswerable. The detail page lets them retry.
    upload = request.FILES.get("file")
    if created and upload is not None:
        try:
            services.attach_file(actor=_actor(request), ticket=ticket, uploaded=upload)
        except ValidationError as exc:
            logger.info(
                "it_support: attachment refused on %s: %s",
                ticket.reference,
                "; ".join(exc.messages),
            )
    return redirect(reverse("it_support_ticket", args=[str(ticket.public_id)]))


DRAFT_FIELDS = (
    "subject",
    "description",
    "category",
    "preferredContact",
    "deviceInfo",
    "location",
)


def _draft(request: HttpRequest) -> dict[str, str]:
    return {key: (request.POST.get(key) or "")[:2000] for key in DRAFT_FIELDS}


# --------------------------------------------------------------------------- #
# Shared detail
# --------------------------------------------------------------------------- #


def _detail_props(request: HttpRequest, ticket: SupportTicket, *, errors=None) -> dict:
    actor = _actor(request)
    can = _capabilities(actor, ticket)
    return {
        "ticket": ticket_detail(
            ticket,
            replies=services.visible_replies(ticket, actor),
            attachments=services.visible_attachments(ticket, actor),
            transitions=services.available_transitions(ticket, actor),
            can_triage=can["triage"],
        ),
        "can": can,
        "assignees": _assignable(request),
        "options": filter_options(),
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("it_support_detail")
@inertia(DETAIL_PAGE)
def ticket_detail_view(request: HttpRequest, public_id: str):
    return _detail_props(request, _load(request, public_id, triage=True))


def _errors(exc: ValidationError) -> dict[str, Any]:
    """The repository's validation shape, built from a service exception.

    These failures come from the service layer, which is deliberately
    form-free so the same rules apply to a Celery caller and an HTTP one.
    """
    if hasattr(exc, "message_dict"):
        return {"fields": dict(exc.message_dict), "form": []}
    return {"fields": {}, "form": list(exc.messages)}


def _rerender_detail(
    request: HttpRequest, ticket: SupportTicket, errors: dict, *, status: int
) -> HttpResponse:
    """Re-render the detail page carrying the failure.

    A 409 re-renders from the *stored* row on purpose: the caller's next action
    should be based on what is actually there, not on what they submitted.
    """
    fresh = _load(request, str(ticket.public_id), triage=True)
    response = render(
        request, DETAIL_PAGE, _detail_props(request, fresh, errors=errors)
    )
    response.status_code = status
    return response


def _redirect_detail(ticket: SupportTicket) -> HttpResponse:
    return redirect(reverse("it_support_ticket", args=[str(ticket.public_id)]))


@enforce_policy("it_support_write")
@require_POST
def ticket_transition(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    try:
        services.transition(
            actor=_actor(request),
            ticket=ticket,
            to_status=(request.POST.get("status") or "").strip(),
            expected_status=(request.POST.get("expectedStatus") or "").strip() or None,
            note=request.POST.get("note") or "",
            note_internal=request.POST.get("noteInternal") == "1",
        )
    except ConcurrentUpdate as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=409)
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return _redirect_detail(ticket)


@enforce_policy("it_support_write")
@require_POST
def ticket_assign(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    raw = (request.POST.get("assignee") or "").strip()
    assignee = None
    if raw:
        # Resolved against the same scoped set the picker was built from, so a
        # hand-edited id cannot route work to somebody outside the actor's reach.
        allowed = {person["id"] for person in _assignable(request)}
        if raw.isdigit() and int(raw) in allowed:
            assignee = User.objects.filter(pk=int(raw), is_active=True).first()
        if assignee is None:
            return _rerender_detail(
                request,
                ticket,
                {"fields": {"assignee": ["That person is not available."]}, "form": []},
                status=422,
            )

    raw_expected = (request.POST.get("expectedAssignee") or "").strip()
    if "expectedAssignee" not in request.POST:
        expected: Any = services.UNSET
    elif not raw_expected:
        expected = None
    elif raw_expected.isdigit():
        expected = int(raw_expected)
    else:
        expected = services.UNSET

    try:
        services.assign(
            actor=_actor(request),
            ticket=ticket,
            assignee=assignee,
            expected_assignee_id=expected,
        )
    except ConcurrentUpdate as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=409)
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return _redirect_detail(ticket)


@enforce_policy("it_support_write")
@require_POST
def ticket_prioritise(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    priority = PRIORITY_BY_KEY.get((request.POST.get("priority") or "").strip())
    if priority is None:
        return _rerender_detail(
            request,
            ticket,
            {"fields": {"priority": ["Unknown priority."]}, "form": []},
            status=422,
        )
    try:
        services.set_priority(actor=_actor(request), ticket=ticket, priority=priority)
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return _redirect_detail(ticket)


@enforce_policy("it_support_write")
@require_POST
def ticket_reply(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    try:
        services.add_reply(
            actor=_actor(request),
            ticket=ticket,
            body=request.POST.get("body") or "",
            internal=request.POST.get("internal") == "1",
        )
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return _redirect_detail(ticket)


@enforce_policy("it_support_write")
@require_POST
def ticket_attach(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    try:
        services.attach_file(
            actor=_actor(request),
            ticket=ticket,
            uploaded=request.FILES.get("file"),
            internal=request.POST.get("internal") == "1",
        )
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return _redirect_detail(ticket)


@enforce_policy("it_support_attachment")
@require_GET
def ticket_attachment_download(
    request: HttpRequest, public_id: str, attachment_id: str
) -> FileResponse:
    """Stream one attachment, authorized on this request for this reader.

    Streamed rather than redirected to a signed link: the scope check runs now,
    and nothing durable is handed out that could outlive the reader's access.
    An IT-only file is a 404 — not a 403 — for a requester, because a 403 would
    confirm the file exists.
    """
    actor = _actor(request)
    ticket = _load(request, public_id, triage=True)
    attachment = services.load_attachment(
        ticket=ticket, actor=actor, public_id=attachment_id
    )
    if attachment is None or not attachment.file:
        raise Http404("No attachment matches that reference.")

    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=attachment.display_name,
        content_type=attachment.media_type or "application/octet-stream",
    )
    # Private, and never stored by a shared cache: the same URL means different
    # things to different readers.
    response["Cache-Control"] = "private, max-age=0, no-store"
    return response


# --------------------------------------------------------------------------- #
# IT queue
# --------------------------------------------------------------------------- #


def _clean_filters(params) -> dict[str, str]:
    """Client input, narrowed to codes this build recognises.

    An unknown value is dropped rather than passed to the ORM: a filter is only
    ever allowed to narrow the set the scope already decided.
    """
    status = (params.get("status") or "").strip()
    category = (params.get("category") or "").strip()
    priority = (params.get("priority") or "").strip()
    assigned = (params.get("assigned") or "").strip()
    office = (params.get("office") or "").strip()
    return {
        "status": status if status in STATUS_CODES else "",
        "category": category if category in CATEGORY_CODES else "",
        "priority": priority if priority in PRIORITY_BY_KEY else "",
        "assigned": assigned if assigned in {"me", "unassigned"} else "",
        "office": office if office.isdigit() else "",
        "q": (params.get("q") or "").strip()[:120],
    }


def _apply_filters(queryset, filters: dict[str, str], *, user):
    if filters["status"]:
        queryset = queryset.filter(status=filters["status"])
    else:
        # The default view is live work. Closed tickets are history and would
        # dominate the queue within a month.
        queryset = queryset.filter(status__in=OPEN_STATUSES)
    if filters["category"]:
        queryset = queryset.filter(category=filters["category"])
    if filters["priority"]:
        queryset = queryset.filter(priority=PRIORITY_BY_KEY[filters["priority"]])
    if filters["assigned"] == "me":
        queryset = queryset.filter(assignee=user)
    elif filters["assigned"] == "unassigned":
        queryset = queryset.filter(assignee__isnull=True)
    if filters["office"]:
        # Narrows the already-scoped set: an office id the reader cannot reach
        # simply matches nothing.
        queryset = queryset.filter(office_id=int(filters["office"]))
    if filters["q"]:
        queryset = queryset.filter(
            Q(subject__icontains=filters["q"]) | Q(reference__icontains=filters["q"])
        )
    return queryset


def _office_options(request: HttpRequest) -> list[dict[str, Any]]:
    """Offices whose tickets this reader can already see."""
    scoped = _scoped(request, triage=True)
    rows = (
        Office.objects.filter(pk__in=scoped.values("office_id"))
        .order_by("name", "pk")
        .values("pk", "name")[:200]
    )
    return [{"value": str(row["pk"]), "label": row["name"]} for row in rows]


@enforce_policy("operations_admin_it_support")
@inertia(QUEUE_PAGE)
def it_support_queue(request: HttpRequest):
    user = cast(User, request.user)
    actor = _actor(request)
    filters = _clean_filters(request.GET)
    scoped = _scoped(request, triage=True)

    queryset = _apply_filters(scoped, filters, user=user).order_by(
        "priority", "created_at"
    )
    total = queryset.count()
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    start = (page - 1) * PAGE_SIZE
    rows = [ticket_row(ticket) for ticket in queryset[start : start + PAGE_SIZE]]

    return {
        "tickets": list_response(
            rows, page=page, page_size=PAGE_SIZE, total_items=total, filters=filters
        ),
        # Counted on the scoped queryset, so a triager whose reach is one branch
        # sees that branch's numbers rather than the brokerage's.
        "metrics": queue_metrics(scoped),
        "options": filter_options(),
        "offices": _office_options(request),
        "can": _capabilities(actor),
        "errors": empty_validation_errors(),
    }
