"""The feedback module's HTTP surface.

Three audiences, three shapes:

* **anybody signed in** may open the form and read their own tickets;
* **support staff** get the inbox and the triage actions;
* **the screenshot view** re-authorizes on every request and streams bytes,
  rather than handing out a link that could outlive the reader's access.

Tickets are always loaded through the reader's own scoped queryset, so an id
outside their reach is a 404 rather than a 403 — confirming that a ticket
exists is itself a disclosure.
"""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.feedback import services
from apps.feedback.diagnostics import disclosure_lines, redact_url
from apps.feedback.models import FeedbackScreenshot, FeedbackTicket
from apps.feedback.payloads import filter_options, ticket_detail, ticket_row
from apps.feedback.services import ActorContext, ConcurrentUpdate
from apps.feedback.taxonomy import (
    CATEGORY_LABELS,
    OPEN_STATUSES,
    PRIORITY_BY_KEY,
    STATUS_CODES,
    URGENCY_LABELS,
    FeedbackPermission,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.capability import access_for
from apps.web.contracts import empty_validation_errors, list_response
from apps.web.flash import set_flash

SUBMIT_PAGE = "FeedbackSubmit"
MINE_PAGE = "FeedbackMine"
DETAIL_PAGE = "FeedbackDetail"
INBOX_PAGE = "FeedbackInbox"
PAGE_SIZE = 25


def _actor(request: HttpRequest) -> ActorContext:
    user = cast(User, request.user)
    return ActorContext(user=user, permissions=frozenset(user.get_all_permissions()))


def _scoped(request: HttpRequest, *, triage: bool):
    user = cast(User, request.user)
    actor = _actor(request)
    return FeedbackTicket.objects.for_reader(
        user,
        access=access_for(user),
        can_triage=triage and actor.can_triage,
    ).select_related("office", "submitter", "assignee")


def _load(request: HttpRequest, public_id: str, *, triage: bool) -> FeedbackTicket:
    ticket = _scoped(request, triage=triage).filter(public_id=public_id).first()
    if ticket is None:
        raise Http404("No ticket matches that reference.")
    return ticket


def _errors(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        data = dict(exc.message_dict)
        form = data.pop("form", [])
        return {"fields": data, "form": list(form)}
    return {"fields": {}, "form": list(exc.messages)}


def _allowed_hosts(request: HttpRequest) -> set[str]:
    """Hosts a submitted page URL may name.

    Read from the request rather than a constant so a deployment behind more
    than one hostname does not silently refuse its own pages.
    """
    from django.conf import settings

    hosts = {host.lstrip(".").lower() for host in settings.ALLOWED_HOSTS if host != "*"}
    hosts.add(request.get_host().split(":")[0].lower())
    return hosts


# --------------------------------------------------------------------------- #
# Submit
# --------------------------------------------------------------------------- #


def _support_contacts(request: HttpRequest) -> list[dict[str, Any]]:
    """The people behind the form, from the reader's own office.

    Real assignments, not invented names: the same records Office Info reads,
    narrowed to the two roles somebody with a broken tool actually wants. An
    office with neither returns an empty list rather than a placeholder — a
    fabricated contact is worse than none.
    """
    from apps.user.office_payloads import office_info_payload

    office = getattr(request.user, "office", None)
    if office is None:
        return []

    contacts = office_info_payload(office)["contacts"]
    wanted = (
        ("itSupport", "IT support", "Logins, devices, and anything that will not load"),
        ("branchAdmin", "Office admin", "Paperwork, access, and day-to-day questions"),
        ("branchManager", "Branch manager", "Escalations and anything urgent"),
    )
    return [
        {
            "key": key,
            "role": role,
            "purpose": purpose,
            "name": person["displayName"],
            "email": person["email"],
            "phone": person.get("phoneNumber") or "",
        }
        for key, role, purpose in wanted
        if (person := contacts.get(key)) is not None
    ]


def _origin_page(request: HttpRequest) -> str:
    """The page the reader came from, or nothing.

    Captured at the click rather than from ``document.referrer``: an Inertia
    visit never sets one, so the referrer was empty in exactly the normal case.

    A hostile or malformed value yields an empty string rather than raising —
    this is the *form*, and refusing to render it because somebody hand-edited
    a query parameter would deny the reader the one page they came for. The
    same value is validated again, strictly, on submit.
    """
    raw = request.GET.get("from") or ""
    if not raw:
        return ""
    try:
        return redact_url(raw, allowed_hosts=_allowed_hosts(request))
    except ValidationError:
        return ""


def _submit_props(request: HttpRequest, *, errors=None) -> dict[str, Any]:
    return {
        "categories": [
            {"value": code, "label": str(label)}
            for code, label in CATEGORY_LABELS.items()
        ],
        "urgencies": [
            {"value": code, "label": str(label)}
            for code, label in URGENCY_LABELS.items()
        ],
        # Generated from the constants that do the capturing, so the promise
        # and the behaviour cannot drift apart.
        "disclosure": disclosure_lines(),
        "contacts": _support_contacts(request),
        # The page the reader came from, captured at the click rather than
        # from `document.referrer` — an Inertia visit never sets one, so the
        # referrer was empty in exactly the normal case. Scrubbed and
        # same-origin checked here as well as on submit.
        "pageUrl": _origin_page(request),
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("feedback_submit")
@inertia(SUBMIT_PAGE)
def feedback_submit(request: HttpRequest):
    return _submit_props(request)


@enforce_policy("feedback_write")
@require_POST
def feedback_create(request: HttpRequest):
    import json

    raw_metadata = request.POST.get("browserMetadata") or "{}"
    try:
        metadata = json.loads(raw_metadata)
    except (TypeError, ValueError):
        # Unparseable metadata is dropped, not fatal: the report matters more
        # than the diagnostics, and the client is not trusted anyway.
        metadata = {}

    try:
        ticket, _created = services.submit(
            user=request.user,
            submission_key=request.POST.get("submissionKey") or "",
            category=(request.POST.get("category") or "").strip(),
            summary=request.POST.get("summary") or "",
            description=request.POST.get("description") or "",
            urgency=(request.POST.get("urgency") or "").strip(),
            page_url=request.POST.get("pageUrl") or "",
            browser_metadata=metadata,
            screenshot=request.FILES.get("screenshot"),
            allowed_hosts=_allowed_hosts(request),
        )
    except ValidationError as exc:
        response = render(
            request, SUBMIT_PAGE, _submit_props(request, errors=_errors(exc))
        )
        response.status_code = 422
        return response
    # Redirect after success so a refresh cannot repeat the write. A replayed
    # POST lands on the same ticket anyway, but the reader should not have to
    # rely on that. Flash so FlashToasts confirms the send across the redirect.
    set_flash(
        request,
        level="success",
        message=f"Report sent — reference {ticket.reference}",
    )
    return redirect(reverse("feedback_detail", args=[str(ticket.public_id)]))


# --------------------------------------------------------------------------- #
# Mine, detail, inbox
# --------------------------------------------------------------------------- #


@enforce_policy("feedback_mine")
@inertia(MINE_PAGE)
def feedback_mine(request: HttpRequest):
    queryset = _scoped(request, triage=False).order_by("-created_at")
    total = queryset.count()
    return {
        "tickets": list_response(
            [ticket_row(ticket) for ticket in queryset[:PAGE_SIZE]],
            page=1,
            page_size=PAGE_SIZE,
            total_items=total,
        ),
        "errors": empty_validation_errors(),
    }


def _assignable(request: HttpRequest) -> list[dict[str, Any]]:
    """People this actor may hand a ticket to.

    Support staff inside the actor's own office reach — scoped *before*
    serialization like every other list, so the assignee picker never becomes a
    back door into a company-wide staff directory for somebody whose reach is
    one branch.

    "Holds the triage grant" is asked of the permission, through groups or a
    direct grant, rather than of a role name: a role is a bundle that can
    change, and the question here is genuinely "could this person work the
    ticket".
    """
    from django.contrib.auth.models import Permission
    from django.db.models import Q

    from apps.web.authorization import scope_queryset_for_user_office

    actor = _actor(request)
    if not actor.can_triage:
        return []

    permission = Permission.objects.filter(
        content_type__app_label="web", codename="triage_feedback"
    ).first()
    if permission is None:
        return []

    reader = cast(User, request.user)
    candidates = scope_queryset_for_user_office(
        reader,
        User.objects.filter(is_active=True).filter(
            Q(groups__permissions=permission) | Q(user_permissions=permission)
        ),
        field_name="office",
        access=access_for(reader),
    )
    return [
        {
            "id": person.pk,
            "name": person.get_full_name() or person.get_short_name(),
        }
        for person in candidates.distinct().order_by("first_name", "last_name", "pk")[
            :100
        ]
    ]


def _detail_props(request: HttpRequest, ticket: FeedbackTicket, *, errors=None):
    actor = _actor(request)
    return {
        "ticket": ticket_detail(
            ticket,
            notes=services.visible_notes(ticket, actor),
            screenshots=FeedbackScreenshot.objects.filter(ticket=ticket),
            transitions=services.available_transitions(ticket, actor),
            can_triage=actor.can_triage,
        ),
        "can": {
            "triage": actor.can_triage,
            "assign": actor.holds(FeedbackPermission.ASSIGN, FeedbackPermission.TRIAGE),
            "note": actor.holds(FeedbackPermission.NOTE, FeedbackPermission.TRIAGE),
        },
        "assignees": _assignable(request),
        "priorities": filter_options()["priorities"],
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("feedback_detail")
@inertia(DETAIL_PAGE)
def feedback_detail(request: HttpRequest, public_id: str):
    return _detail_props(request, _load(request, public_id, triage=True))


def _rerender_detail(
    request: HttpRequest, ticket: FeedbackTicket, errors: dict, *, status: int
) -> HttpResponse:
    """Re-render from the *stored* row.

    A 409 answers with what is actually there, so the caller's next action is
    based on the world rather than on the state they submitted.
    """
    fresh = _load(request, str(ticket.public_id), triage=True)
    response = render(
        request, DETAIL_PAGE, _detail_props(request, fresh, errors=errors)
    )
    response.status_code = status
    return response


# Generated by the operations registry from the destination row.
@enforce_policy("operations_admin_feedback")
@inertia(INBOX_PAGE)
def feedback_inbox(request: HttpRequest):
    actor = _actor(request)
    status = (request.GET.get("status") or "").strip()
    category = (request.GET.get("category") or "").strip()
    assigned = (request.GET.get("assigned") or "").strip()

    filters = {
        "status": status if status in STATUS_CODES else "",
        "category": category if category in CATEGORY_LABELS else "",
        "assigned": assigned if assigned in {"me", "unassigned"} else "",
        "q": (request.GET.get("q") or "").strip()[:120],
    }

    queryset = _scoped(request, triage=True)
    if filters["status"]:
        queryset = queryset.filter(status=filters["status"])
    else:
        # The default view is live work; closed tickets are history and would
        # dominate the queue within a month.
        queryset = queryset.filter(status__in=sorted(OPEN_STATUSES))
    if filters["category"]:
        queryset = queryset.filter(category=filters["category"])
    if filters["assigned"] == "me":
        queryset = queryset.filter(assignee=request.user)
    elif filters["assigned"] == "unassigned":
        queryset = queryset.filter(assignee__isnull=True)
    if filters["q"]:
        queryset = queryset.filter(summary__icontains=filters["q"])

    queryset = queryset.order_by("priority", "-created_at")
    total = queryset.count()
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    start = (page - 1) * PAGE_SIZE

    return {
        "tickets": list_response(
            [ticket_row(t) for t in queryset[start : start + PAGE_SIZE]],
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters,
        ),
        "filterOptions": filter_options(),
        "summary": {
            "open": _scoped(request, triage=True)
            .filter(status__in=sorted(OPEN_STATUSES))
            .count(),
            "mine": _scoped(request, triage=True)
            .filter(assignee=request.user, status__in=sorted(OPEN_STATUSES))
            .count(),
        },
        "can": {
            "triage": actor.can_triage,
            "assign": actor.holds(FeedbackPermission.ASSIGN, FeedbackPermission.TRIAGE),
        },
        "errors": empty_validation_errors(),
    }


# --------------------------------------------------------------------------- #
# Triage writes
# --------------------------------------------------------------------------- #


@enforce_policy("feedback_triage_write")
@require_POST
def feedback_transition(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    try:
        services.transition(
            actor=_actor(request),
            ticket=ticket,
            to_status=(request.POST.get("status") or "").strip(),
            expected_status=(request.POST.get("expectedStatus") or "").strip() or None,
            reply=request.POST.get("reply") or "",
        )
    except ConcurrentUpdate as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=409)
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return redirect(reverse("feedback_detail", args=[public_id]))


@enforce_policy("feedback_triage_write")
@require_POST
def feedback_assign(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    raw = (request.POST.get("assignee") or "").strip()
    assignee = User.objects.filter(pk=raw, is_active=True).first() if raw else None
    if raw and assignee is None:
        return _rerender_detail(
            request,
            ticket,
            {"fields": {"assignee": ["That person is not available."]}, "form": []},
            status=422,
        )
    try:
        services.assign(actor=_actor(request), ticket=ticket, assignee=assignee)
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return redirect(reverse("feedback_detail", args=[public_id]))


@enforce_policy("feedback_triage_write")
@require_POST
def feedback_prioritise(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    rank = PRIORITY_BY_KEY.get((request.POST.get("priority") or "").strip())
    if rank is None:
        return _rerender_detail(
            request,
            ticket,
            {"fields": {"priority": ["Unknown priority."]}, "form": []},
            status=422,
        )
    try:
        services.set_priority(actor=_actor(request), ticket=ticket, priority=rank)
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return redirect(reverse("feedback_detail", args=[public_id]))


@enforce_policy("feedback_write")
@require_POST
def feedback_note(request: HttpRequest, public_id: str):
    """Reply, or write a staff-only note.

    Loaded with ``triage=False`` when the actor cannot triage, so a submitter
    reaches only their own ticket and everybody else gets a 404.
    """
    actor = _actor(request)
    ticket = _load(request, public_id, triage=actor.can_triage)
    try:
        services.add_note(
            actor=actor,
            ticket=ticket,
            body=request.POST.get("body") or "",
            internal=request.POST.get("internal") == "1",
        )
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    except PermissionDenied:
        raise
    return redirect(reverse("feedback_detail", args=[public_id]))


@enforce_policy("feedback_triage_write")
@require_POST
def feedback_convert(request: HttpRequest, public_id: str):
    ticket = _load(request, public_id, triage=True)
    try:
        services.convert_to_task(actor=_actor(request), ticket=ticket)
    except ValidationError as exc:
        return _rerender_detail(request, ticket, _errors(exc), status=422)
    return redirect(reverse("feedback_detail", args=[public_id]))


# --------------------------------------------------------------------------- #
# Screenshot
# --------------------------------------------------------------------------- #


@enforce_policy("feedback_screenshot")
@require_GET
def feedback_screenshot(request: HttpRequest, public_id: str, screenshot_id: str):
    """One image, authorized at access time.

    Streamed rather than redirected to a signed link: the scope check runs on
    *this* request for *this* reader, and nothing durable is handed out that
    could outlive their access. The ticket is loaded through the scoped
    queryset first, so an id outside their reach 404s before any file is
    touched.
    """
    actor = _actor(request)
    ticket = _load(request, public_id, triage=actor.can_triage)
    shot = FeedbackScreenshot.objects.filter(
        ticket=ticket, public_id=screenshot_id
    ).first()
    if shot is None:
        raise Http404("No screenshot matches that reference.")

    response = FileResponse(shot.image.open("rb"), content_type=shot.media_type)
    response["Content-Disposition"] = f'inline; filename="{shot.display_name}"'
    # Private, and never stored by a shared cache: the same URL means different
    # things to different readers.
    response["Cache-Control"] = "private, max-age=0, no-store"
    return response
