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

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
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
from apps.web.authorization import enforce_policy
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


def _index_props(request: HttpRequest, *, errors=None) -> dict[str, Any]:
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
        "can": {
            "manage": actor.holds(TaskPermission.MANAGE),
            "assign": actor.holds(TaskPermission.ASSIGN, TaskPermission.MANAGE),
            "comment": actor.holds(TaskPermission.COMMENT, TaskPermission.MANAGE),
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
        "can": {
            "manage": actor.holds(TaskPermission.MANAGE),
            "assign": actor.holds(TaskPermission.ASSIGN, TaskPermission.MANAGE),
            "comment": actor.holds(TaskPermission.COMMENT, TaskPermission.MANAGE),
        },
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
            "can": {
                "manage": actor.holds(TaskPermission.MANAGE),
                "assign": actor.holds(TaskPermission.ASSIGN, TaskPermission.MANAGE),
                "comment": actor.holds(TaskPermission.COMMENT, TaskPermission.MANAGE),
            },
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
    try:
        task = services.create_task(
            actor=actor,
            office=office,
            category=(request.POST.get("category") or "").strip(),
            title=request.POST.get("title") or "",
            description=request.POST.get("description") or "",
            priority=priority,
            team=request.POST.get("team") or "",
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
    response = render(request, INDEX_PAGE, _index_props(request, errors=errors))
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
    assignee = User.objects.filter(pk=raw, is_active=True).first() if raw else None
    if raw and assignee is None:
        return _rerender_detail(
            request,
            task,
            {"fields": {"assignee": ["That person is not available."]}, "form": []},
            status=422,
        )
    try:
        services.assign(actor=actor, task=task, assignee=assignee)
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
