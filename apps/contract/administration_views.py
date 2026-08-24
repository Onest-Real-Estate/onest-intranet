"""HTTP surface for governed contract template administration."""

from __future__ import annotations

import json
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.contract.forms import (
    ContractTemplateActionForm,
    ContractTemplateCreateForm,
    ContractTemplateVersionForm,
)
from apps.contract.models import ContractTemplateVersion
from apps.contract.tasks import generate_contract_template_preview
from apps.contract.template_service import (
    activate_version,
    capabilities,
    create_draft_version,
    create_template_family,
    generate_preview,
    manageable_template_queryset,
    manageable_version_queryset,
    publish_version,
    retire_version,
    save_draft_version,
    serialize_template_row,
    serialize_version_detail,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response, validation_errors

INDEX_PAGE = "ContractTemplateAdministration"
WORKSPACE_PAGE = "ContractTemplateWorkspace"


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _target(request: HttpRequest, version_id: int) -> ContractTemplateVersion:
    actor = cast(User, request.user)
    return get_object_or_404(manageable_version_queryset(actor), pk=version_id)


def index_props(
    actor: User,
    *,
    params,
    create_sheet: dict[str, Any] | None = None,
    errors: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query = (params.get("q") or "").strip()
    status = (params.get("status") or "").strip()
    jurisdiction = (params.get("jurisdiction") or "").strip().upper()
    rows = manageable_template_queryset(actor)
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(stable_key__icontains=query))
    if status:
        rows = rows.filter(status=status)
    if jurisdiction:
        rows = rows.filter(jurisdiction_state_codes__contains=[jurisdiction])
    items = [serialize_template_row(item) for item in rows.order_by("name")]
    return {
        "templates": list_response(
            items,
            page=_page_param_from_params(params),
            page_size=20,
            total_items=len(items),
            filters={"q": query, "status": status, "jurisdiction": jurisdiction},
            sort_key="name",
        ),
        "capabilities": capabilities(actor).payload(),
        "createSheet": create_sheet,
        "errors": errors or empty_validation_errors(),
    }


def _page_param_from_params(params) -> int:
    try:
        return max(1, int(params.get("page", "1")))
    except ValueError:
        return 1


@enforce_policy("contract_template_admin")
@require_GET
@inertia(INDEX_PAGE)
def contract_template_index(request: HttpRequest):
    actor = cast(User, request.user)
    opening = request.GET.get("create") == "1"
    return index_props(
        actor,
        params=request.GET,
        create_sheet={"open": True, "draft": {}} if opening else None,
    )


def _render_index(
    request: HttpRequest, *, create_sheet: dict[str, Any], errors: dict[str, Any]
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        INDEX_PAGE,
        index_props(
            actor,
            params=request.POST,
            create_sheet=create_sheet,
            errors=errors,
        ),
    )
    response.status_code = 422
    return response


@enforce_policy("contract_template_create")
@require_POST
def contract_template_create(request: HttpRequest):
    actor = cast(User, request.user)
    form = ContractTemplateCreateForm(request.POST, actor=actor)
    if not form.is_valid():
        return _render_index(
            request,
            create_sheet={"open": True, "draft": dict(request.POST)},
            errors=validation_errors(form),
        )
    template = create_template_family(
        actor,
        stable_key=form.cleaned_data["stable_key"],
        name=form.cleaned_data["name"],
        description=form.cleaned_data["description"],
        jurisdiction_state_codes=form.cleaned_data["jurisdiction_state_codes"],
        company_wide=form.cleaned_data["company_wide"],
        applicable_offices=list(form.cleaned_data["applicable_offices"]),
        applicable_regions=list(form.cleaned_data["applicable_regions"]),
        effective_from=form.cleaned_data["effective_from"],
        effective_until=form.cleaned_data["effective_until"],
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label=form.cleaned_data["version_label"],
        display_name=form.cleaned_data["name"],
        description=form.cleaned_data["description"],
        merge_schema=[],
    )
    return redirect("contract_template_workspace", version_id=version.pk)


def workspace_props(
    actor: User,
    *,
    version: ContractTemplateVersion,
    errors: dict[str, Any] | None = None,
    posted: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    detail = serialize_version_detail(version)
    detail["template"] = serialize_template_row(version.template)
    detail["mergeSchemaJson"] = json.dumps(version.merge_schema or [], indent=2)
    try:
        detail["previewUrl"] = version.preview_pdf.url if version.preview_pdf else None
    except ValueError:
        detail["previewUrl"] = None
    return {
        "versionDetail": detail,
        "capabilities": capabilities(actor).payload(),
        "errors": errors or empty_validation_errors(),
        "posted": posted,
    }


@enforce_policy("contract_template_workspace")
@require_GET
@inertia(WORKSPACE_PAGE)
def contract_template_workspace(request: HttpRequest, version_id: int):
    actor = cast(User, request.user)
    return workspace_props(actor, version=_target(request, version_id))


def _render_workspace(
    request: HttpRequest,
    *,
    version: ContractTemplateVersion,
    errors: dict[str, Any],
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(
            actor,
            version=version,
            errors=errors,
            posted={key: request.POST.getlist(key) for key in request.POST},
        ),
    )
    response.status_code = 422
    return response


@enforce_policy("contract_template_update")
@require_POST
def contract_template_update(request: HttpRequest, version_id: int):
    version = _target(request, version_id)
    actor = cast(User, request.user)
    form = ContractTemplateVersionForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_workspace(
            request,
            version=version,
            errors=validation_errors(form),
        )
    try:
        save_draft_version(
            actor,
            version=version,
            expected_version=form.cleaned_data.get("expected_version", ""),
            display_name=form.cleaned_data["display_name"],
            description=form.cleaned_data["description"],
            merge_schema=form.cleaned_data["merge_schema_json"],
            source_upload=form.cleaned_data.get("source_document"),
        )
    except ValidationError as exc:
        errors = (
            {"fields": exc.message_dict, "form": []}
            if hasattr(exc, "message_dict")
            else {"fields": {}, "form": [str(message) for message in exc.messages]}
        )
        return _render_workspace(
            request,
            version=_target(request, version_id),
            errors=errors,
        )
    return redirect("contract_template_workspace", version_id=version_id)


@enforce_policy("contract_template_action")
@require_POST
def contract_template_action(request: HttpRequest, version_id: int):
    version = _target(request, version_id)
    actor = cast(User, request.user)
    form = ContractTemplateActionForm(request.POST)
    if not form.is_valid():
        return _render_workspace(
            request,
            version=version,
            errors={"fields": {}, "form": ["That is not a valid template action."]},
        )
    action = form.cleaned_data["action"]
    try:
        if action == "preview":
            if request.POST.get("background") == "1":
                generate_contract_template_preview.delay(version.pk)
            else:
                generate_preview(version)
        elif action == "publish":
            publish_version(actor, version=version)
        elif action == "activate":
            activate_version(actor, version=version)
        elif action == "retire":
            retire_version(actor, version=version)
    except ValidationError as exc:
        errors = (
            {"fields": exc.message_dict, "form": []}
            if hasattr(exc, "message_dict")
            else {"fields": {}, "form": [str(message) for message in exc.messages]}
        )
        return _render_workspace(
            request,
            version=_target(request, version_id),
            errors=errors,
        )
    return redirect("contract_template_workspace", version_id=version_id)
