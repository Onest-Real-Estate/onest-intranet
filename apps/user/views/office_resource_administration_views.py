"""Scoped office resources administration — Operations destination."""

from __future__ import annotations

from typing import cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors
from apps.web.operations import operations_scope_payload

from ..forms import (
    OfficeResourceFileForm,
    OfficeResourceForm,
    OfficeResourceTransitionForm,
    form_errors,
)
from ..models import Office, OfficeResource, User
from ..services.office_resource_administration import (
    StaleResourceVersion,
    build_resource_list,
    create_resource,
    detail_payload,
    managed_resource_queryset,
    parse_admin_filters,
    replace_file,
    resource_scope,
    transition_resource,
    update_resource,
)

__all__ = [
    "office_resources_admin_index",
    "office_resource_new",
    "office_resource_create",
    "office_resource_detail",
    "office_resource_update",
    "office_resource_file",
    "office_resource_transition",
]

_STALE = {
    "fields": {},
    "form": ["This resource changed since you opened it. Reload and try again."],
}


def _int_param(request: HttpRequest, name: str) -> int | None:
    raw = request.GET.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _detail_props(
    actor: User,
    resource: OfficeResource | None,
    *,
    request: HttpRequest,
    errors: dict | None = None,
) -> dict:
    preview_office_id = _int_param(request, "preview")
    props = detail_payload(actor, resource, preview_office_id=preview_office_id)
    props["scope"] = operations_scope_payload(actor)
    props["validation"] = errors or empty_validation_errors()
    return props


def _render_detail(
    request: HttpRequest,
    actor: User,
    resource: OfficeResource | None,
    *,
    errors: dict,
    status: int,
) -> HttpResponse:
    response = render(
        request,
        "OfficeResourceWorkspace",
        _detail_props(actor, resource, request=request, errors=errors),
    )
    response.status_code = status
    return response


def _validation_error_payload(exc: ValidationError) -> dict:
    if hasattr(exc, "message_dict"):
        fields = {
            field: [str(message) for message in messages]
            for field, messages in exc.message_dict.items()
            if field != "__all__"
        }
        form_msgs = [str(m) for m in exc.message_dict.get("__all__", [])]
        return {"fields": fields, "form": form_msgs or list(exc.messages)}
    return {"fields": {}, "form": list(exc.messages)}


# Draft keys posted from the create sheet, mapped to the camelCase defaults
# the frontend form component repopulates after a 422.
_SHEET_DRAFT_FIELDS = {
    "slug": "slug",
    "title": "title",
    "summary": "summary",
    "category": "category",
    "resource_type": "resourceType",
    "body": "body",
    "url": "url",
    "owner_office": "ownerId",
    "sort_order": "sortOrder",
    "starts_at": "startsAt",
    "ends_at": "endsAt",
}


def _sheet_draft(request: HttpRequest) -> dict[str, str]:
    draft: dict[str, str] = {}
    for source, target in _SHEET_DRAFT_FIELDS.items():
        value = request.POST.get(source, "")
        if value:
            draft[target] = value
    if request.POST.get("is_active") in {"on", "true", "True"}:
        draft["isActive"] = "on"
    return draft


def _render_index_with_sheet_errors(
    request: HttpRequest,
    actor: User,
    *,
    errors: dict,
) -> HttpResponse:
    """Re-render the console with the create sheet reopened and populated."""
    filters = parse_admin_filters(request.POST)
    payload = build_resource_list(actor, filters=filters)
    response = render(
        request,
        "OfficeResourcesAdministration",
        {
            **payload,
            "scope": operations_scope_payload(actor),
            "validation": errors,
            "createSheet": {"open": True, "draft": _sheet_draft(request)},
        },
    )
    response.status_code = 422
    return response


@enforce_policy("admin_office_resources")
@require_GET
@inertia("OfficeResourcesAdministration")
def office_resources_admin_index(request: HttpRequest):
    actor = cast(User, request.user)
    filters = parse_admin_filters(request.GET)
    payload = build_resource_list(actor, filters=filters, page=_page_param(request))
    return {
        **payload,
        "scope": operations_scope_payload(actor),
        "validation": empty_validation_errors(),
        "createSheet": None,
    }


@enforce_policy("admin_office_resource_new")
@require_GET
@inertia("OfficeResourceWorkspace")
def office_resource_new(request: HttpRequest):
    actor = cast(User, request.user)
    return _detail_props(actor, None, request=request)


@enforce_policy("admin_office_resource_create")
@require_POST
def office_resource_create(request: HttpRequest):
    actor = cast(User, request.user)
    sheet_mode = request.POST.get("context") == "sheet"
    scope_offices = Office.objects.filter(pk__in=resource_scope(actor).office_ids)
    form = OfficeResourceForm(request.POST, owner_queryset=scope_offices)
    if not form.is_valid():
        if sheet_mode:
            return _render_index_with_sheet_errors(
                request, actor, errors=form_errors(form)
            )
        return _render_detail(
            request, actor, None, errors=form_errors(form), status=422
        )
    cleaned = dict(form.cleaned_data)
    cleaned["is_active"] = request.POST.get("is_active") in {"on", "true", "True"}
    uploaded = (
        request.FILES.get("file")
        if form.cleaned_data["resource_type"] == "file"
        else None
    )
    if uploaded is None and form.cleaned_data["resource_type"] == "file":
        errors = {
            "fields": {"file": ["Upload a file for file resources."]},
            "form": [],
        }
        if sheet_mode:
            return _render_index_with_sheet_errors(request, actor, errors=errors)
        return _render_detail(request, actor, None, errors=errors, status=422)
    try:
        resource = create_resource(actor, cleaned=cleaned, uploaded_file=uploaded)
    except ValidationError as exc:
        errors = _validation_error_payload(exc)
        if sheet_mode:
            return _render_index_with_sheet_errors(request, actor, errors=errors)
        return _render_detail(
            request,
            actor,
            None,
            errors=errors,
            status=422,
        )
    except PermissionDenied:
        raise
    return redirect("admin_office_resource", resource_id=resource.pk)


@enforce_policy("admin_office_resource")
@require_GET
@inertia("OfficeResourceWorkspace")
def office_resource_detail(request: HttpRequest, resource_id: int):
    actor = cast(User, request.user)
    resource = get_object_or_404(managed_resource_queryset(actor), pk=resource_id)
    return _detail_props(actor, resource, request=request)


@enforce_policy("admin_office_resource_update")
@require_POST
def office_resource_update(request: HttpRequest, resource_id: int):
    actor = cast(User, request.user)
    resource = get_object_or_404(managed_resource_queryset(actor), pk=resource_id)
    scope_offices = Office.objects.filter(pk__in=resource_scope(actor).office_ids)
    form = OfficeResourceForm(request.POST, owner_queryset=scope_offices)
    if not form.is_valid():
        return _render_detail(
            request, actor, resource, errors=form_errors(form), status=422
        )
    cleaned = dict(form.cleaned_data)
    # An unchecked checkbox posts nothing; absence means off.
    cleaned["is_active"] = request.POST.get("is_active") in {"on", "true", "True"}
    try:
        update_resource(
            actor,
            resource.pk,
            cleaned=cleaned,
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleResourceVersion:
        return _render_detail(request, actor, resource, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request,
            actor,
            resource,
            errors=_validation_error_payload(exc),
            status=422,
        )
    except PermissionDenied:
        raise
    return redirect("admin_office_resource", resource_id=resource.pk)


@enforce_policy("admin_office_resource_file")
@require_POST
def office_resource_file(request: HttpRequest, resource_id: int):
    actor = cast(User, request.user)
    resource = get_object_or_404(managed_resource_queryset(actor), pk=resource_id)
    form = OfficeResourceFileForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_detail(
            request, actor, resource, errors=form_errors(form), status=422
        )
    try:
        replace_file(
            actor,
            resource.pk,
            uploaded_file=request.FILES["file"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleResourceVersion:
        return _render_detail(request, actor, resource, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request,
            actor,
            resource,
            errors=_validation_error_payload(exc),
            status=422,
        )
    except PermissionDenied:
        raise
    return redirect("admin_office_resource", resource_id=resource.pk)


@enforce_policy("admin_office_resource_transition")
@require_POST
def office_resource_transition(request: HttpRequest, resource_id: int):
    actor = cast(User, request.user)
    resource = get_object_or_404(managed_resource_queryset(actor), pk=resource_id)
    form = OfficeResourceTransitionForm(request.POST)
    if not form.is_valid():
        return _render_detail(
            request, actor, resource, errors=form_errors(form), status=422
        )
    try:
        transition_resource(
            actor,
            resource.pk,
            action=form.cleaned_data["action"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleResourceVersion:
        return _render_detail(request, actor, resource, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request,
            actor,
            resource,
            errors=_validation_error_payload(exc),
            status=422,
        )
    except PermissionDenied:
        raise
    return redirect("admin_office_resource", resource_id=resource.pk)
