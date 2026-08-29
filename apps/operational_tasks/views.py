"""The task module's HTTP surface.

Two rules, the same ones the announcement workspace follows:

* **Load through the scoped queryset, never by bare id.** A task outside the
  actor's reach is a 404, not a 403 — confirming an id exists is itself a
  disclosure across a scope boundary.
* **Answer the failure the caller actually hit.** A refused field is 422 with
  the messages attached; a row that moved underneath is 409 with the current
  state re-rendered, so the recovery is "read theirs, then reapply mine".

Nothing here decides authority. ``enforce_policy`` gates the route on the
reviewed permission and :mod:`apps.operational_tasks.services` re-derives the
actor's grants on every write.
"""

from __future__ import annotations

import re
from datetime import datetime
from datetime import time as dt_time
from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.operational_tasks import services
from apps.operational_tasks.models import OperationalTask
from apps.operational_tasks.payloads import (
    board_columns,
    filter_options,
    task_detail,
    task_row,
)
from apps.operational_tasks.services import ActorContext, ConcurrentUpdate
from apps.operational_tasks.taxonomy import (
    ACTIVE_STATUSES,
    CATEGORY_CODES,
    PRIORITY_BY_KEY,
    STATUS_CODES,
    TaskPermission,
    TaskPriority,
)
from apps.user.models import Office, User
from apps.web.authorization import (
    enforce_policy,
    scope_queryset_for_offices,
    scope_queryset_for_user_office,
)
from apps.web.capability import access_for
from apps.web.contracts import empty_validation_errors, list_response

INDEX_PAGE = "OperationalTasks"
DETAIL_PAGE = "OperationalTaskDetail"
PAGE_SIZE = 25


def _actor(request: HttpRequest) -> ActorContext:
    user = cast(User, request.user)
    return ActorContext(
        user=user,
        permissions=frozenset(user.get_all_permissions()),
    )


def _scoped(request: HttpRequest):
    user = cast(User, request.user)
    return OperationalTask.objects.for_reader(
        user, access=access_for(user)
    ).select_related("office", "assignee", "reporter")


def _load(request: HttpRequest, public_id: str) -> OperationalTask:
    """One task, or 404.

    Deliberately not ``get_object_or_404`` on the bare manager: the lookup runs
    inside the reader's own scope, so an id they may not see is indistinguishable
    from an id that does not exist.
    """
    task = _scoped(request).filter(public_id=public_id).first()
    if task is None:
        raise Http404("No task matches that reference.")
    return task


def _capabilities(actor: ActorContext) -> dict[str, bool]:
    """What this actor may do, mirrored to the UI so it can hide what it may
    not. Never the authorization — every write re-checks in the service."""
    return {
        "manage": actor.holds(TaskPermission.MANAGE),
        "assign": actor.holds(TaskPermission.ASSIGN, TaskPermission.MANAGE),
        "comment": actor.holds(TaskPermission.COMMENT, TaskPermission.MANAGE),
    }


def _assignable(request: HttpRequest) -> list[dict[str, Any]]:
    """People this actor may hand a task to.

    Scoped *before* serialization, like every other list: the picker must not
    become a back door into a company-wide staff directory for somebody whose
    reach is one branch. Membership is asked of the permission rather than of a
    role name, because a role is a bundle that can change and the question here
    is genuinely "could this person work the task".
    """
    from django.contrib.auth.models import Permission

    actor = _actor(request)
    if not actor.holds(TaskPermission.ASSIGN, TaskPermission.MANAGE):
        return []

    codenames = [
        code.split(".", 1)[-1]
        for code in (TaskPermission.MANAGE, TaskPermission.ASSIGN)
    ]
    permissions = Permission.objects.filter(
        content_type__app_label="web", codename__in=codenames
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


def _creatable_offices(request: HttpRequest) -> list[dict[str, Any]]:
    """Offices this actor may file a task against.

    The create form posts an office id, so the set of ids it may legitimately
    send is decided here and re-derived on submit. Serializing the whole office
    tree to somebody who reaches one branch would leak the org chart.
    """
    actor = _actor(request)
    if not actor.holds(TaskPermission.MANAGE):
        return []
    reader = cast(User, request.user)
    offices = scope_queryset_for_offices(reader, Office.objects.filter(is_active=True))
    return [
        {"id": office.pk, "name": office.name}
        for office in offices.order_by("name", "pk")[:200]
    ]


#: A date with no time, the shape ``<input type="date">`` submits.
_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}")
_BAD_DATE = "Use a date like 2026-03-14."
#: Local hour a bare date is due at. End of the working day, not midnight —
#: midnight would make a task due today overdue from the moment it is created.
END_OF_DAY_HOUR = 17


def _due_at(raw: str):
    """A client-supplied due date, or a refusal.

    Parsed rather than passed through: an unparseable value must become a
    field error the writer can fix, not a silent ``None`` that quietly drops
    the date they typed.
    """
    text = (raw or "").strip()
    if not text:
        return None

    # A bare ``YYYY-MM-DD`` is handled *before* ``parse_datetime``, not after
    # it fails: Django 6 parses a date-only string to midnight, so a fallback
    # branch would never run and "due the 3rd" would silently mean "due 00:00
    # on the 3rd" — a task due today would read as overdue for the whole day.
    # ``<input type="date">`` sends exactly this shape.
    parsed = None
    if _DATE_ONLY.fullmatch(text):
        try:
            day = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValidationError({"dueAt": [_BAD_DATE]}) from exc
        parsed = datetime.combine(day, dt_time(END_OF_DAY_HOUR, 0))
    else:
        parsed = parse_datetime(text)
    if parsed is None:
        raise ValidationError({"dueAt": [_BAD_DATE]})
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _tags(raw: str) -> list[str]:
    """Comma-separated tags, deduplicated and bounded. Free text, never a
    permission subject: nothing authorizes from a tag."""
    seen: list[str] = []
    for part in (raw or "").split(","):
        tag = part.strip()[:40]
        if tag and tag not in seen:
            seen.append(tag)
    return seen[:12]


def _clean_filters(params) -> dict[str, str]:
    """Client input, narrowed to codes this build recognises.

    An unknown value is dropped rather than passed to the ORM: a filter is only
    ever allowed to narrow the set the scope already decided.
    """
    status = (params.get("status") or "").strip()
    category = (params.get("category") or "").strip()
    priority = (params.get("priority") or "").strip()
    assigned = (params.get("assigned") or "").strip()
    return {
        "status": status if status in STATUS_CODES else "",
        "category": category if category in CATEGORY_CODES else "",
        "priority": priority if priority in PRIORITY_BY_KEY else "",
        "assigned": assigned if assigned in {"me", "unassigned"} else "",
        "q": (params.get("q") or "").strip()[:120],
    }


def _apply_filters(queryset, filters: dict[str, str], *, user):
    if filters["status"]:
        queryset = queryset.filter(status=filters["status"])
    else:
        # The default view is live work. Closed and cancelled tasks are history
        # and would otherwise dominate the list within a month.
        queryset = queryset.filter(status__in=ACTIVE_STATUSES)
    if filters["category"]:
        queryset = queryset.filter(category=filters["category"])
    if filters["priority"]:
        queryset = queryset.filter(priority=PRIORITY_BY_KEY[filters["priority"]])
    if filters["assigned"] == "me":
        queryset = queryset.filter(assignee=user)
    elif filters["assigned"] == "unassigned":
        queryset = queryset.filter(assignee__isnull=True)
    if filters["q"]:
        queryset = queryset.filter(title__icontains=filters["q"])
    return queryset


#: The create drawer's fields, echoed back verbatim when a save is refused so
#: nothing typed is lost. Bounded and string-only: this is client text going
#: straight back out, and it is never read as anything but a form value.
DRAFT_FIELDS = (
    "office",
    "category",
    "title",
    "description",
    "priority",
    "team",
    "assignee",
    "dueAt",
    "tags",
)


def _draft(request: HttpRequest) -> dict[str, str]:
    return {key: (request.POST.get(key) or "")[:2000] for key in DRAFT_FIELDS}


def _index_props(
    request: HttpRequest, *, errors=None, draft: dict[str, str] | None = None
) -> dict[str, Any]:
    user = cast(User, request.user)
    actor = _actor(request)
    filters = _clean_filters(request.GET)
    view = "board" if request.GET.get("view") == "board" else "list"

    queryset = _apply_filters(_scoped(request), filters, user=user).order_by(
        "priority", "due_at", "-created_at"
    )
    total = queryset.count()
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    now = timezone.now()
    if view == "board":
        # The board is bounded rather than paginated: a column that silently
        # stops at 25 looks like the work is done.
        rows = [task_row(task, now=now) for task in queryset[:200]]
        board = board_columns(rows)
        listing = list_response(
            [], page=1, page_size=PAGE_SIZE, total_items=total, filters=filters
        )
    else:
        board = None
        start = (page - 1) * PAGE_SIZE
        rows = [task_row(task, now=now) for task in queryset[start : start + PAGE_SIZE]]
        listing = list_response(
            rows,
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters,
        )

    return {
        "tasks": listing,
        "board": board,
        "view": view,
        "filterOptions": filter_options(),
        "summary": {
            "open": _scoped(request).active().count(),
            "overdue": _scoped(request).overdue(at=now).count(),
            "mine": _scoped(request).active().filter(assignee=user).count(),
        },
        "can": _capabilities(actor),
        # Only what the create form legitimately needs, and only for somebody
        # who may actually create: an empty list for everyone else.
        "offices": _creatable_offices(request),
        "categories": filter_options()["categories"],
        "createSheet": {
            # Reopened on a refused save with the draft echoed: the drawer posts
            # natively, so anything not sent back is genuinely lost.
            "open": request.GET.get("create") == "1" or errors is not None,
            "draft": draft or dict.fromkeys(DRAFT_FIELDS, ""),
        },
        "errors": errors or empty_validation_errors(),
    }


# Generated by the operations registry from the destination row.
@enforce_policy("operations_operational_tasks")
@inertia(INDEX_PAGE)
def tasks_index(request: HttpRequest):
    return _index_props(request)


@enforce_policy("operational_task_detail")
@inertia(DETAIL_PAGE)
def task_detail_view(request: HttpRequest, public_id: str):
    actor = _actor(request)
    task = _load(request, public_id)
    return {
        "task": task_detail(
            task,
            comments=services.visible_comments(task, actor),
            attachments=services.visible_attachments(task, actor),
            transitions=services.available_transitions(task, actor),
        ),
        "can": _capabilities(actor),
        "assignees": _assignable(request),
        "errors": empty_validation_errors(),
    }


def _errors(exc: ValidationError) -> dict[str, Any]:
    """The repository's validation shape, built from a service exception.

    ``contracts.validation_errors`` reads a bound Django form; these failures
    come from the service layer, which is deliberately form-free so the same
    rules apply to a Celery caller and an HTTP one alike.
    """
    if hasattr(exc, "message_dict"):
        return {"fields": dict(exc.message_dict), "form": []}
    return {"fields": {}, "form": list(exc.messages)}


def _detail_redirect(task: OperationalTask) -> HttpResponse:
    return redirect(reverse("operational_task_detail", args=[str(task.public_id)]))


def _rerender_detail(
    request: HttpRequest, task: OperationalTask, errors: dict, *, status: int
) -> HttpResponse:
    """Re-render the detail page carrying the failure.

    A 409 re-renders from the *stored* row on purpose: the caller's next action
    should be based on what is actually there, not on the state they submitted.
    """
    actor = _actor(request)
    fresh = _load(request, str(task.public_id))
    response = render(
        request,
        DETAIL_PAGE,
        {
            "task": task_detail(
                fresh,
                comments=services.visible_comments(fresh, actor),
                attachments=services.visible_attachments(fresh, actor),
                transitions=services.available_transitions(fresh, actor),
            ),
            "can": _capabilities(actor),
            "assignees": _assignable(request),
            "errors": errors,
        },
    )
    response.status_code = status
    return response


@enforce_policy("operational_task_write")
@require_POST
def task_create(request: HttpRequest):
    actor = _actor(request)
    office = Office.objects.filter(pk=request.POST.get("office") or 0).first()
    if office is None:
        return _index_422(request, {"office": ["Choose the office that owns this."]})

    priority = PRIORITY_BY_KEY.get(
        (request.POST.get("priority") or "").strip(), TaskPriority.NORMAL
    )
    raw_assignee = (request.POST.get("assignee") or "").strip()
    assignee = None
    if raw_assignee:
        # Resolved against the same scoped set the picker was built from, so a
        # hand-edited id cannot assign work to somebody outside the actor's reach.
        allowed = {person["id"] for person in _assignable(request)}
        assignee = (
            User.objects.filter(pk=raw_assignee, is_active=True).first()
            if raw_assignee.isdigit() and int(raw_assignee) in allowed
            else None
        )
        if assignee is None:
            return _index_422(request, {"assignee": ["That person is not available."]})
    try:
        task = services.create_task(
            actor=actor,
            office=office,
            category=(request.POST.get("category") or "").strip(),
            title=request.POST.get("title") or "",
            description=request.POST.get("description") or "",
            priority=priority,
            assignee=assignee,
            team=request.POST.get("team") or "",
            due_at=_due_at(request.POST.get("dueAt") or ""),
            tags=_tags(request.POST.get("tags") or ""),
        )
    except ValidationError as exc:
        return _index_422(request, exc)
    return _detail_redirect(task)


def _index_422(
    request: HttpRequest, exc: ValidationError | dict[str, list[str]]
) -> HttpResponse:
    errors = (
        _errors(exc)
        if isinstance(exc, ValidationError)
        else {"fields": exc, "form": []}
    )
    response = render(
        request,
        INDEX_PAGE,
        _index_props(request, errors=errors, draft=_draft(request)),
    )
    response.status_code = 422
    return response


@enforce_policy("operational_task_write")
@require_POST
def task_transition(request: HttpRequest, public_id: str):
    actor = _actor(request)
    task = _load(request, public_id)
    try:
        services.transition(
            actor=actor,
            task=task,
            to_status=(request.POST.get("status") or "").strip(),
            expected_status=(request.POST.get("expectedStatus") or "").strip() or None,
            note=request.POST.get("note") or "",
        )
    except ConcurrentUpdate as exc:
        return _rerender_detail(request, task, _errors(exc), status=409)
    except ValidationError as exc:
        return _rerender_detail(request, task, _errors(exc), status=422)
    except PermissionDenied:
        raise
    return _detail_redirect(task)


@enforce_policy("operational_task_write")
@require_POST
def task_assign(request: HttpRequest, public_id: str):
    actor = _actor(request)
    task = _load(request, public_id)
    raw = (request.POST.get("assignee") or "").strip()
    assignee = None
    if raw:
        # The same scoped set the picker was rendered from. Trusting the posted
        # id alone would let a hand-edited form assign work to anybody.
        allowed = {person["id"] for person in _assignable(request)}
        if raw.isdigit() and int(raw) in allowed:
            assignee = User.objects.filter(pk=int(raw), is_active=True).first()
        if assignee is None:
            return _rerender_detail(
                request,
                task,
                {"fields": {"assignee": ["That person is not available."]}, "form": []},
                status=422,
            )

    raw_expected = (request.POST.get("expectedAssignee") or "").strip()
    # Three cases, and they are genuinely different: absent means "no opinion",
    # an empty string means "I believe this is unassigned", and a number is a
    # claim about who holds it.
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
            actor=actor, task=task, assignee=assignee, expected_assignee_id=expected
        )
    except ConcurrentUpdate as exc:
        return _rerender_detail(request, task, _errors(exc), status=409)
    except ValidationError as exc:
        return _rerender_detail(request, task, _errors(exc), status=422)
    return _detail_redirect(task)


@enforce_policy("operational_task_write")
@require_POST
def task_comment(request: HttpRequest, public_id: str):
    actor = _actor(request)
    task = _load(request, public_id)
    try:
        services.add_comment(
            actor=actor,
            task=task,
            body=request.POST.get("body") or "",
            internal=request.POST.get("internal") == "1",
        )
    except ValidationError as exc:
        return _rerender_detail(request, task, _errors(exc), status=422)
    return _detail_redirect(task)


@enforce_policy("operational_task_write")
@require_POST
def task_attach(request: HttpRequest, public_id: str):
    """Attach one file to a task.

    The task is loaded through the reader's own scope first, so a file cannot
    be pushed onto a task the uploader may not see; the service then judges the
    extension, the size, and the per-task count before anything is written.
    """
    actor = _actor(request)
    task = _load(request, public_id)
    try:
        services.attach_file(
            actor=actor,
            task=task,
            uploaded=request.FILES.get("file"),
            internal=request.POST.get("internal") == "1",
        )
    except ValidationError as exc:
        return _rerender_detail(request, task, _errors(exc), status=422)
    return _detail_redirect(task)


@enforce_policy("operational_task_attachment")
@require_GET
def task_attachment_download(
    request: HttpRequest, public_id: str, attachment_id: str
) -> FileResponse:
    """Stream one attachment, authorized on this request for this reader.

    Streamed rather than redirected to a signed link: the scope check runs now,
    and nothing durable is handed out that could outlive the reader's access.
    The task is resolved inside their scope and the attachment inside
    ``visible_attachments``, so an internal file is a 404 — not a 403 — for
    somebody without the management grant.
    """
    actor = _actor(request)
    task = _load(request, public_id)
    attachment = services.load_attachment(
        task=task, actor=actor, public_id=attachment_id
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
