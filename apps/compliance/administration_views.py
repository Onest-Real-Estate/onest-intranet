"""Compliance administration HTTP surface."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.compliance.acknowledgements import scoped_report, waive
from apps.compliance.administration import (
    StalePolicyVersion,
    TransitionRefused,
    audience_choice_payload,
    build_admin_index,
    capabilities,
    category_options,
    create_draft,
    detail_payload,
    duplicate_version,
    publication_queryset,
    publishable_office_queryset,
    transition,
    update_draft,
)
from apps.compliance.forms import (
    PolicyDuplicateForm,
    PolicyTransitionForm,
    PolicyVersionForm,
    PolicyWaiverForm,
)
from apps.compliance.media_service import (
    allowed_matrix_payload,
    assert_can_manage_media,
    remove_file,
    upload_document,
)
from apps.compliance.models import PolicyFile, PolicyVersion
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, validation_errors

INDEX_PAGE = "ComplianceAdministration"
WORKSPACE_PAGE = "ComplianceWorkspace"
REPORT_PAGE = "ComplianceAckReport"

MANAGE_PERMISSION = "web.manage_policies"
VIEW_PERMISSION = "web.view_compliance"


def _require_view(actor: User) -> None:
    if not (
        has_effective_permission(actor, VIEW_PERMISSION)
        or has_effective_permission(actor, MANAGE_PERMISSION)
    ):
        raise PermissionDenied("You cannot view compliance.")


def _require_manage(actor: User) -> None:
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        raise PermissionDenied("You cannot manage policies.")


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _target(request: HttpRequest, policy_id: int) -> PolicyVersion:
    actor = cast(User, request.user)
    return get_object_or_404(publication_queryset(actor), pk=policy_id)


@enforce_policy("operations_admin_compliance")
@require_GET
@inertia(INDEX_PAGE)
def admin_compliance(request: HttpRequest):
    actor = cast(User, request.user)
    _require_view(actor)
    return {
        **build_admin_index(actor, params=request.GET, page=_page_param(request)),
        "errors": empty_validation_errors(),
    }


def workspace_props(
    actor: User,
    *,
    policy: PolicyVersion | None = None,
    errors: dict | None = None,
) -> dict[str, Any]:
    return {
        "policy": detail_payload(policy, actor=actor) if policy else None,
        "officeOptions": [
            {"value": office.pk, "label": office.name}
            for office in publishable_office_queryset(actor)
        ],
        "categoryOptions": category_options(
            include_codes=(
                (policy.category.code,) if policy and policy.category else ()
            )
        ),
        "audienceOptions": audience_choice_payload(actor),
        "capabilities": capabilities(actor).payload(),
        "mediaLimits": allowed_matrix_payload(),
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("policy_admin_new")
@require_GET
@inertia(WORKSPACE_PAGE)
def policy_admin_new(request: HttpRequest):
    actor = cast(User, request.user)
    _require_manage(actor)
    return workspace_props(actor)


@enforce_policy("policy_admin_edit")
@require_GET
@inertia(WORKSPACE_PAGE)
def policy_admin_edit(request: HttpRequest, policy_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    return workspace_props(actor, policy=_target(request, policy_id))


def _render_workspace(
    request: HttpRequest,
    *,
    policy: PolicyVersion | None,
    errors: dict,
    status: int,
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(actor, policy=policy, errors=errors),
    )
    response.status_code = status
    return response


def _validation_payload(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        data = exc.message_dict
        return {
            "fields": {
                field: [str(message) for message in messages]
                for field, messages in data.items()
                if field != "__all__"
            },
            "form": [str(message) for message in data.get("__all__", [])],
        }
    return {"fields": {}, "form": [str(message) for message in exc.messages]}


def _submit(request: HttpRequest, policy: PolicyVersion | None) -> HttpResponse:
    actor = cast(User, request.user)
    form = PolicyVersionForm(
        request.POST, instance=policy or PolicyVersion(), actor=actor
    )
    if not form.is_valid():
        return _render_workspace(
            request, policy=policy, errors=validation_errors(form), status=422
        )
    try:
        if policy is None:
            saved = create_draft(
                actor=actor,
                office=form.cleaned_data["owner_office"],
                cleaned=form.field_values,
                selectors=form.selectors,
            )
        else:
            saved = update_draft(
                actor=actor,
                version=policy,
                cleaned=form.field_values,
                selectors=form.selectors,
                expected_version=form.cleaned_data.get("expected_version", ""),
            )
    except StalePolicyVersion as exc:
        return _render_workspace(
            request,
            policy=PolicyVersion.objects.get(pk=policy.pk) if policy else None,
            errors={"fields": {}, "form": [exc.message]},
            status=409,
        )
    except ValidationError as exc:
        return _render_workspace(
            request, policy=policy, errors=_validation_payload(exc), status=422
        )
    return redirect("policy_admin_edit", policy_id=saved.pk)


@enforce_policy("policy_admin_create")
@require_POST
def policy_admin_create(request: HttpRequest):
    _require_manage(cast(User, request.user))
    return _submit(request, None)


@enforce_policy("policy_admin_update")
@require_POST
def policy_admin_update(request: HttpRequest, policy_id: int):
    _require_manage(cast(User, request.user))
    return _submit(request, _target(request, policy_id))


def _lifecycle_failure(
    request: HttpRequest, policy: PolicyVersion, message: str, status: int
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(
            actor,
            policy=PolicyVersion.objects.get(pk=policy.pk),
            errors={"fields": {}, "form": [message]},
        ),
    )
    response.status_code = status
    return response


@enforce_policy("policy_admin_lifecycle")
@require_POST
def policy_admin_lifecycle(request: HttpRequest, policy_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    policy = _target(request, policy_id)
    form = PolicyTransitionForm(request.POST)
    if not form.is_valid():
        return _lifecycle_failure(
            request, policy, "That is not a compliance action.", 422
        )
    try:
        transition(
            actor=actor,
            version=policy,
            action=form.cleaned_data["action"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StalePolicyVersion as exc:
        return _lifecycle_failure(request, policy, exc.message, 409)
    except TransitionRefused as exc:
        return _lifecycle_failure(request, policy, exc.message, 422)
    except ValidationError as exc:
        response = render(
            request,
            WORKSPACE_PAGE,
            workspace_props(
                actor,
                policy=PolicyVersion.objects.get(pk=policy.pk),
                errors=_validation_payload(exc),
            ),
        )
        response.status_code = 422
        return response
    return redirect("policy_admin_edit", policy_id=policy.pk)


@enforce_policy("policy_admin_duplicate")
@require_POST
def policy_admin_duplicate(request: HttpRequest, policy_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    policy = _target(request, policy_id)
    form = PolicyDuplicateForm(request.POST)
    if not form.is_valid():
        return _lifecycle_failure(request, policy, "Send the current version.", 422)
    try:
        draft = duplicate_version(
            actor=actor,
            version=policy,
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StalePolicyVersion as exc:
        return _lifecycle_failure(request, policy, exc.message, 409)
    except ValidationError as exc:
        return _lifecycle_failure(
            request, policy, "; ".join(str(m) for m in exc.messages), 422
        )
    return redirect("policy_admin_edit", policy_id=draft.pk)


@enforce_policy("policy_admin_file_upload")
@require_POST
def policy_admin_file_upload(request: HttpRequest, policy_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    policy = _target(request, policy_id)
    assert_can_manage_media(actor, policy)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _lifecycle_failure(request, policy, "Choose a file to upload.", 422)
    role = (request.POST.get("role") or PolicyFile.Role.DOCUMENT).strip()
    try:
        upload_document(actor, policy, uploaded, role=role)
    except ValidationError as exc:
        return _lifecycle_failure(
            request,
            policy,
            "; ".join(str(m) for m in getattr(exc, "messages", [exc])),
            422,
        )
    return redirect("policy_admin_edit", policy_id=policy.pk)


@enforce_policy("policy_admin_file_remove")
@require_POST
def policy_admin_file_remove(request: HttpRequest, file_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    row = get_object_or_404(
        PolicyFile.objects.select_related(
            "policy_version", "policy_version__owner_office"
        ),
        pk=file_id,
    )
    if not publication_queryset(actor).filter(pk=row.policy_version.pk).exists():
        raise PermissionDenied("That file is not available.")
    try:
        remove_file(actor, row)
    except ValidationError as exc:
        return _lifecycle_failure(
            request,
            row.policy_version,
            "; ".join(str(m) for m in getattr(exc, "messages", [exc])),
            422,
        )
    return redirect("policy_admin_edit", policy_id=row.policy_version.pk)


@enforce_policy("policy_ack_report")
@require_GET
@inertia(REPORT_PAGE)
def policy_ack_report(request: HttpRequest):
    actor = cast(User, request.user)
    _require_view(actor)
    return {
        "report": scoped_report(actor, request.GET),
        "capabilities": capabilities(actor).payload(),
        "errors": empty_validation_errors(),
    }


@enforce_policy("policy_ack_waive")
@require_POST
def policy_ack_waive(request: HttpRequest, policy_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    policy = _target(request, policy_id)
    form = PolicyWaiverForm(request.POST, actor=actor)
    if not form.is_valid():
        response = render(
            request,
            REPORT_PAGE,
            {
                "report": scoped_report(actor, {"policy": str(policy_id)}),
                "capabilities": capabilities(actor).payload(),
                "errors": validation_errors(form),
            },
        )
        response.status_code = 422
        return response
    try:
        waive(
            actor,
            user_id=form.cleaned_data["user"].pk,
            version_id=policy.pk,
            reason=form.cleaned_data["reason"],
        )
    except ValidationError as exc:
        response = render(
            request,
            REPORT_PAGE,
            {
                "report": scoped_report(actor, {"policy": str(policy_id)}),
                "capabilities": capabilities(actor).payload(),
                "errors": _validation_payload(exc),
            },
        )
        response.status_code = 422
        return response
    return redirect("policy_ack_report")
