"""Scoped New Agent List and operational onboarding workspace."""

from __future__ import annotations

import mimetypes
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
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
    OnboardingContractForm,
    OnboardingHandoffForm,
    OnboardingNoticeForm,
    OnboardingOwnerForm,
    OnboardingTaskCreateForm,
    OnboardingTaskResolveForm,
    OnboardingToolActionForm,
)
from apps.user.services.agent_administration import assignable_office_queryset
from apps.user.services.onboarding_metrics import (
    OnboardingErrorCode,
    record_onboarding_error,
)
from apps.user.services.onboarding_office import (
    office_confirmation_is_current,
    office_confirmation_payload,
)
from apps.user.services.onboarding_operations import (
    SourceActionUnavailable,
    StaleOnboardingVersion,
    assign_owner,
    create_task,
    initiate_contract,
    owner_queryset,
    perform_tool_action,
    resend_notice,
    resolve_task,
    retry_office_handoff,
)
from apps.user.services.onboarding_state import (
    build_onboarding_states,
    new_agent_queryset,
    overall_status_options,
    state_payload,
)
from apps.user.services.role_assignments import has_effective_permission
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response, validation_errors
from apps.web.flash import set_flash

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
        Q(
            target_type=UserOnboardingCase._meta.label_lower,
            target_id=str(target.pk),
            action__startswith="user.onboarding.",
        )
        | Q(
            action="onboarding_tool.state_changed",
            metadata__agent_id=target.pk,
        )
    ).order_by("-occurred_at")[:12]
    can_read_sensitive = has_effective_permission(
        actor, "user.view_user_administration"
    )
    profile_fields = [
        {"key": "legalName", "label": "Legal name", "value": target.get_full_name()},
        {
            "key": "preferredName",
            "label": "Preferred name",
            "value": target.preferred_name,
        },
        {"key": "email", "label": "Microsoft email", "value": target.email},
        {
            "key": "languages",
            "label": "Languages",
            "value": ", ".join(target.languages or []),
        },
        {"key": "bio", "label": "Professional bio", "value": target.bio},
    ]
    if can_read_sensitive:
        profile_fields.extend(
            [
                {
                    "key": "phoneNumber",
                    "label": "Phone",
                    "value": target.phone_number,
                },
                {
                    "key": "homeAddress",
                    "label": "Home / mailing address",
                    "value": ", ".join(
                        item
                        for item in (
                            target.street_address,
                            target.city,
                            target.state,
                            target.zip_code,
                        )
                        if item
                    ),
                },
                {
                    "key": "license",
                    "label": "Real-estate license",
                    "value": " · ".join(
                        item
                        for item in (target.license_state, target.license_number)
                        if item
                    ),
                },
                {"key": "mlsNumber", "label": "MLS number", "value": target.mls_number},
                {
                    "key": "nrdsNumber",
                    "label": "NRDS number",
                    "value": target.nrds_number,
                },
            ]
        )
    confirmed_office = None
    if target.office and office_confirmation_is_current(target, state.case):
        confirmed_office = office_confirmation_payload(target.office)
    return {
        "onboarding": state_payload(actor, state, detail=True),
        "profileSummary": {
            "headshotUrl": (
                reverse("new_agent_onboarding_headshot", args=[target.pk])
                if target.headshot
                else None
            ),
            "fields": profile_fields,
            "sensitiveFieldsIncluded": can_read_sensitive,
        },
        "confirmedOffice": confirmed_office,
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


@enforce_policy("new_agent_onboarding_headshot")
@require_GET
def onboarding_headshot(request: HttpRequest, user_id: int) -> FileResponse:
    actor = cast(User, request.user)
    target = _target(actor, user_id)
    if not target.headshot:
        raise Http404
    content_type, _ = mimetypes.guess_type(target.headshot.name)
    response = FileResponse(
        target.headshot.open("rb"),
        as_attachment=False,
        filename=target.headshot.name.rsplit("/", 1)[-1],
        content_type=content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, max-age=300"
    return response


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


def _mutation_error(request, actor, target, form, callback, *, success_message: str):
    if not form.is_valid():
        record_onboarding_error(OnboardingErrorCode.ADMIN_ACTION_INVALID)
        return _render_error(
            request, actor, target, validation_errors(form), status=422
        )
    try:
        callback(form.cleaned_data)
    except StaleOnboardingVersion as exc:
        record_onboarding_error(OnboardingErrorCode.ADMIN_ACTION_STALE)
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
        record_onboarding_error(OnboardingErrorCode.ADMIN_ACTION_INVALID)
        return _render_error(request, actor, target, validation, status=422)
    set_flash(request, level="success", message=success_message)
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
        success_message="Onboarding owner updated.",
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
    return _mutation_error(
        request,
        actor,
        target,
        form,
        callback,
        success_message="Onboarding task updated.",
    )


@enforce_policy("new_agent_onboarding_tools")
@require_POST
def onboarding_tools(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(actor, user_id)
    form = OnboardingToolActionForm(request.POST)
    return _mutation_error(
        request,
        actor,
        target,
        form,
        lambda data: perform_tool_action(
            actor=actor,
            user=target,
            tool=data["tool"],
            action=data["action"],
            reason=data.get("reason", ""),
            expected_version=data.get("expected_version", ""),
        ),
        success_message="Tool onboarding updated.",
    )


@enforce_policy("new_agent_onboarding_contract")
@require_POST
def onboarding_contract(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(actor, user_id)
    form = OnboardingContractForm(request.POST)
    return _mutation_error(
        request,
        actor,
        target,
        form,
        lambda data: initiate_contract(
            actor=actor,
            user=target,
            expected_version=data["expected_version"],
        ),
        success_message="Agent contract initiated.",
    )


@enforce_policy("new_agent_onboarding_handoff")
@require_POST
def onboarding_handoff(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(actor, user_id)
    form = OnboardingHandoffForm(request.POST)
    return _mutation_error(
        request,
        actor,
        target,
        form,
        lambda data: retry_office_handoff(
            actor=actor,
            user=target,
            expected_version=data["expected_version"],
        ),
        success_message="Office handoff sent again.",
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
            expected_version=data["expected_version"],
        ),
        success_message="Notice retry requested.",
    )


def onboarding_detail_href(user_id: int) -> str:
    return reverse("new_agent_onboarding", args=[user_id])
