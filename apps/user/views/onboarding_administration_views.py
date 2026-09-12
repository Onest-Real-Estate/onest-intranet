"""Scoped New Agent List and operational onboarding workspace."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.audit.models import AuditEvent
from apps.onboarding_tools.payloads import state_options
from apps.user.models import (
    OnboardingTask,
    User,
    UserOnboardingCase,
)
from apps.user.onboarding_forms import (
    OnboardingNoticeForm,
    OnboardingOwnerForm,
    OnboardingTaskCreateForm,
    OnboardingTaskResolveForm,
    OnboardingToolForm,
)
from apps.user.services.agent_administration import assignable_office_queryset
from apps.user.services.onboarding_operations import (
    SourceActionUnavailable,
    StaleOnboardingVersion,
    assign_owner,
    create_task,
    owner_queryset,
    resend_notice,
    resolve_task,
    update_tool_setup,
)
from apps.user.services.onboarding_state import (
    build_onboarding_states,
    new_agent_queryset,
    overall_status_options,
    state_payload,
)
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response, validation_errors

PAGE_SIZE = 25
SORT_KEYS = {"name", "office", "owner", "startDate", "overallStatus"}


def _prefetched_queryset(actor: User):
    return (
        new_agent_queryset(actor)
        .select_related(
            "office",
            "office__region",
            "onboarding_case",
            "onboarding_case__owner",
            "onboarding_case__updated_by",
        )
        .prefetch_related(
            Prefetch(
                "onboarding_case__tasks",
                queryset=OnboardingTask.objects.select_related("created_by").order_by(
                    "status", "due_on", "created_at"
                ),
            ),
        )
    )


def _target(actor: User, user_id: int) -> User:
    return get_object_or_404(_prefetched_queryset(actor), pk=user_id)


def _parse_page(value: str) -> int:
    try:
        return max(1, int(value))
    except ValueError:
        return 1


def _filters(request: HttpRequest) -> dict[str, str]:
    return {
        "q": request.GET.get("q", "").strip(),
        "office": request.GET.get("office", "").strip(),
        "owner": request.GET.get("owner", "").strip(),
        "blocker": request.GET.get("blocker", "").strip(),
        "overallStatus": request.GET.get("overallStatus", "").strip(),
        "startFrom": request.GET.get("startFrom", "").strip(),
        "startTo": request.GET.get("startTo", "").strip(),
        "contractStatus": request.GET.get("contractStatus", "").strip(),
        "trainingStatus": request.GET.get("trainingStatus", "").strip(),
    }


def _apply_database_filters(queryset, filters: dict[str, str]):
    query = filters["q"]
    if query:
        queryset = queryset.filter(
            Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(display_name__icontains=query)
        )
    if filters["office"].isdigit():
        queryset = queryset.filter(office_id=int(filters["office"]))
    if filters["owner"].isdigit():
        queryset = queryset.filter(onboarding_case__owner_id=int(filters["owner"]))
    start_from = parse_date(filters["startFrom"])
    start_to = parse_date(filters["startTo"])
    if start_from:
        queryset = queryset.filter(start_date__gte=start_from)
    if start_to:
        queryset = queryset.filter(start_date__lte=start_to)
    return queryset


def _filter_states(states, filters: dict[str, str]):
    result = states
    if filters["overallStatus"]:
        result = [
            state
            for state in result
            if state.overall_status == filters["overallStatus"]
        ]
    if filters["contractStatus"]:
        result = [
            state
            for state in result
            if state.contract.status == filters["contractStatus"]
        ]
    if filters["trainingStatus"]:
        result = [
            state
            for state in result
            if state.training.status == filters["trainingStatus"]
        ]
    blocker = filters["blocker"]
    if blocker == "any":
        result = [state for state in result if state.blockers]
    elif blocker == "none":
        result = [state for state in result if not state.blockers]
    elif blocker:
        result = [
            state
            for state in result
            if any(item["key"] == blocker for item in state.blockers)
        ]
    return result


def _sort_states(states, sort: str, direction: str):
    reverse_sort = direction == "desc"

    def key(state):
        user = state.user
        case = state.case
        values = {
            "name": (str(user).casefold(), user.pk),
            "office": ((user.office.name if user.office else "").casefold(), user.pk),
            "owner": (
                (str(case.owner) if case and case.owner else "").casefold(),
                user.pk,
            ),
            "startDate": (
                user.start_date.isoformat() if user.start_date else "",
                user.pk,
            ),
            "overallStatus": (state.overall_status, user.pk),
        }
        return values[sort]

    return sorted(states, key=key, reverse=reverse_sort)


def _filter_options(actor: User, scoped_users: list[User]) -> dict[str, Any]:
    user_ids = [user.pk for user in scoped_users]
    assigned_owner_ids = list(
        UserOnboardingCase.objects.filter(user_id__in=user_ids, owner__isnull=False)
        .values_list("owner_id", flat=True)
        .distinct()
    )
    owners = User.objects.filter(pk__in=assigned_owner_ids).order_by(
        "first_name", "last_name", "email"
    )
    return {
        "offices": [
            {"value": str(office.pk), "label": office.path_label()}
            for office in assignable_office_queryset(actor)
        ],
        "owners": [{"value": str(owner.pk), "label": str(owner)} for owner in owners],
        "overallStatuses": overall_status_options(),
        "sourceStatuses": [
            {"value": "complete", "label": "Complete"},
            {"value": "pending", "label": "Pending"},
            {"value": "blocked", "label": "Blocked"},
            {"value": "unavailable", "label": "Source unavailable"},
        ],
        "blockers": [
            {"value": "any", "label": "Any blocker"},
            {"value": "none", "label": "No blockers"},
            {
                "value": "contract_source_unavailable",
                "label": "Contract source",
            },
            {
                "value": "training_source_unavailable",
                "label": "Training source",
            },
            {"value": "account_inactive", "label": "Account disabled"},
            {"value": "start_date_missing", "label": "Missing start date"},
        ],
    }


@enforce_policy("operations_admin_new_agents")
@require_GET
@inertia("NewAgentList")
def new_agent_list(request: HttpRequest):
    actor = cast(User, request.user)
    filters = _filters(request)
    queryset = _apply_database_filters(_prefetched_queryset(actor), filters)
    users = list(queryset)
    states = _filter_states(build_onboarding_states(users), filters)
    sort = request.GET.get("sort", "startDate")
    if sort not in SORT_KEYS:
        sort = "startDate"
    direction = "asc" if request.GET.get("direction") == "asc" else "desc"
    states = _sort_states(states, sort, direction)
    total = len(states)
    page = _parse_page(request.GET.get("page", "1"))
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    return {
        "agents": list_response(
            [
                state_payload(actor, state, detail=False)
                for state in states[start : start + PAGE_SIZE]
            ],
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters,
            sort_key=sort,
            sort_direction=direction,
        ),
        "filterOptions": _filter_options(actor, users),
        "scopeLabel": (
            actor.office.region_name() if actor.office else "Your effective scope"
        ),
    }


def _detail_props(
    actor: User,
    target: User,
    *,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = build_onboarding_states([target])[0]
    events = AuditEvent.objects.filter(
        target_type=UserOnboardingCase._meta.label_lower,
        target_id=str(target.pk),
        action__startswith="user.onboarding.",
    ).order_by("-occurred_at")[:8]
    return {
        "onboarding": state_payload(actor, state, detail=True),
        "ownerOptions": [
            {"value": str(owner.pk), "label": str(owner)}
            for owner in owner_queryset(actor, target)
        ],
        "toolStateOptions": state_options(),
        "activity": [
            {
                "id": str(event.pk),
                "action": event.action,
                "actor": event.actor_label,
                "occurredAt": event.occurred_at.isoformat(),
                "changes": sorted(event.changes.keys()),
            }
            for event in events
        ],
        "validation": validation or empty_validation_errors(),
        "privacy": {
            "notesAllowed": False,
            "taskPolicy": (
                "Task titles are retained for two years after resolution. Keep them "
                "operational; do not include client, contract, medical, or "
                "commission details."
            ),
        },
    }


@enforce_policy("new_agent_onboarding")
@require_GET
@inertia("OnboardingWorkspace")
def onboarding_workspace(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    return _detail_props(actor, _target(actor, user_id))


def _render_error(
    request: HttpRequest,
    actor: User,
    target: User,
    errors: dict[str, Any],
    *,
    status: int,
) -> HttpResponse:
    fresh = _target(actor, cast(int, target.pk))
    response = render(
        request,
        "OnboardingWorkspace",
        _detail_props(actor, fresh, validation=errors),
    )
    response.status_code = status
    return response


def _mutation_error(request, actor, target, form, callback):
    if not form.is_valid():
        return _render_error(
            request, actor, target, validation_errors(form), status=422
        )
    try:
        callback(form.cleaned_data)
    except StaleOnboardingVersion as exc:
        return _render_error(
            request,
            actor,
            target,
            {"fields": {}, "form": [exc.message]},
            status=409,
        )
    except (ValidationError, SourceActionUnavailable) as exc:
        # Keep a field-scoped service error on its field. The reason a
        # correction needs belongs under the note control, not in a summary the
        # writer has to translate back into a box.
        message_dict = getattr(exc, "message_dict", None)
        validation = (
            {
                "fields": {
                    field: list(messages)
                    for field, messages in message_dict.items()
                    if field != "__all__"
                },
                "form": list(message_dict.get("__all__", [])),
            }
            if message_dict
            else {"fields": {}, "form": list(exc.messages)}
        )
        return _render_error(request, actor, target, validation, status=422)
    return redirect("new_agent_onboarding", user_id=target.pk)


@enforce_policy("new_agent_onboarding_owner")
@require_POST
def onboarding_owner(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(actor, user_id)
    form = OnboardingOwnerForm(
        request.POST, owner_queryset=owner_queryset(actor, target)
    )
    return _mutation_error(
        request,
        actor,
        target,
        form,
        lambda data: assign_owner(
            actor=actor,
            user=target,
            owner=data.get("owner"),
            expected_version=data.get("expected_version", ""),
        ),
    )


@enforce_policy("new_agent_onboarding_tasks")
@require_POST
def onboarding_tasks(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(actor, user_id)
    if request.POST.get("action") == "resolve":
        form = OnboardingTaskResolveForm(request.POST)

        def callback(data):
            return resolve_task(
                actor=actor,
                user=target,
                task_id=data["task"],
                expected_version=data.get("expected_version", ""),
            )

    elif request.POST.get("action") == "create":
        form = OnboardingTaskCreateForm(request.POST)

        def callback(data):
            return create_task(
                actor=actor,
                user=target,
                title=data["title"],
                due_on=data.get("due_on"),
                is_blocking=data.get("is_blocking", False),
                expected_version=data.get("expected_version", ""),
            )

    else:
        raise Http404()
    return _mutation_error(request, actor, target, form, callback)


@enforce_policy("new_agent_onboarding_tools")
@require_POST
def onboarding_tools(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(actor, user_id)
    form = OnboardingToolForm(request.POST)
    return _mutation_error(
        request,
        actor,
        target,
        form,
        lambda data: update_tool_setup(
            actor=actor,
            user=target,
            tool=data["tool"],
            state=data["state"],
            note=data.get("note", ""),
            expected_version=data.get("expected_version", ""),
        ),
    )


@enforce_policy("new_agent_onboarding_notice")
@require_POST
def onboarding_notice(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(actor, user_id)
    form = OnboardingNoticeForm(request.POST)
    return _mutation_error(
        request,
        actor,
        target,
        form,
        lambda data: resend_notice(
            actor=actor,
            user=target,
            source=data["source"],
            notice=data["notice"],
            idempotency_key=str(data["idempotency_key"]),
        ),
    )


def onboarding_detail_href(user_id: int) -> str:
    return reverse("new_agent_onboarding", args=[user_id])
