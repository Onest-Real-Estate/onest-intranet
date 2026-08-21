"""Scoped office and regional administration — Operations destination."""

from __future__ import annotations

from typing import cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, validation_errors
from apps.web.operations import operations_scope_payload

from ..forms import (
    OfficeContactEndForm,
    OfficeContactUpsertForm,
    OfficeImpactPreviewForm,
    OfficeInfoUpdateForm,
    OfficeStructureUpdateForm,
    form_errors,
)
from ..models import Office, OfficeContactAssignment, User
from ..office_payloads import office_info_payload
from ..services.office_administration import (
    ConfirmationRequired,
    StaleOfficeVersion,
    administration_page_props,
    build_office_list,
    end_contact,
    managed_office_queryset,
    parse_list_filters,
    preview_high_impact,
    update_office_info,
    update_office_structure,
    upsert_contact,
)

__all__ = [
    "office_administration_index",
    "office_administration_detail",
    "office_administration_update",
    "office_administration_structure",
    "office_administration_impact",
    "office_administration_contact",
    "office_administration_contact_end",
    "office_info",
]

_STALE = {
    "fields": {},
    "form": ["This office changed since you opened it. Reload and try again."],
}


def _office(request: HttpRequest, office_id: int) -> Office:
    actor = cast(User, request.user)
    return get_object_or_404(managed_office_queryset(actor), pk=office_id)


def _detail_props(
    actor: User,
    office: Office,
    *,
    errors: dict | None = None,
    preview: dict | None = None,
) -> dict:
    props = administration_page_props(actor, office)
    props["validation"] = errors or empty_validation_errors()
    props["preview"] = preview
    return props


def _render_detail(
    request: HttpRequest,
    office: Office,
    *,
    errors: dict,
    preview: dict | None = None,
    status: int,
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        "OfficeAdministrationDetail",
        _detail_props(actor, office, errors=errors, preview=preview),
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


@enforce_policy("operations_admin_offices")
@require_GET
@inertia("OfficeAdministration")
def office_administration_index(request: HttpRequest):
    actor = cast(User, request.user)
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    filters = parse_list_filters(request.GET)
    payload = build_office_list(actor, filters=filters, page=page)
    return {
        **payload,
        "scope": operations_scope_payload(actor),
    }


@enforce_policy("office_administration_detail")
@require_GET
@inertia("OfficeAdministrationDetail")
def office_administration_detail(request: HttpRequest, office_id: int):
    actor = cast(User, request.user)
    office = _office(request, office_id)
    return _detail_props(actor, office)


@enforce_policy("office_administration_update")
@require_POST
def office_administration_update(request: HttpRequest, office_id: int):
    actor = cast(User, request.user)
    office = _office(request, office_id)
    form = OfficeInfoUpdateForm(request.POST)
    if not form.is_valid():
        return _render_detail(request, office, errors=form_errors(form), status=422)
    try:
        update_office_info(
            actor=actor,
            office=office,
            cleaned=form.cleaned_data,
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleOfficeVersion:
        return _render_detail(request, office, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request, office, errors=_validation_error_payload(exc), status=422
        )
    except PermissionDenied:
        raise
    return redirect("admin_office", office_id=office.pk)


@enforce_policy("office_administration_structure")
@require_POST
def office_administration_structure(request: HttpRequest, office_id: int):
    actor = cast(User, request.user)
    office = _office(request, office_id)
    parent_qs = Office.objects.exclude(pk=office.pk)
    form = OfficeStructureUpdateForm(request.POST, parent_queryset=parent_qs)
    if not form.is_valid():
        return _render_detail(request, office, errors=form_errors(form), status=422)
    try:
        update_office_structure(
            actor=actor,
            office=office,
            cleaned=form.cleaned_data,
            expected_version=form.cleaned_data.get("expected_version", ""),
            confirmed=bool(form.cleaned_data.get("confirmed")),
        )
    except ConfirmationRequired as exc:
        return _render_detail(
            request,
            office,
            errors={"fields": {}, "form": [str(exc)]},
            preview={"highImpact": exc.impact, "requiresConfirmation": True},
            status=422,
        )
    except StaleOfficeVersion:
        return _render_detail(request, office, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request, office, errors=_validation_error_payload(exc), status=422
        )
    except PermissionDenied:
        raise
    return redirect("admin_office", office_id=office.pk)


@enforce_policy("office_administration_impact")
@require_POST
def office_administration_impact(request: HttpRequest, office_id: int):
    actor = cast(User, request.user)
    office = _office(request, office_id)
    form = OfficeImpactPreviewForm(
        request.POST, parent_queryset=Office.objects.exclude(pk=office.pk)
    )
    if not form.is_valid():
        return JsonResponse({"errors": validation_errors(form)}, status=422)
    try:
        preview = preview_high_impact(
            actor=actor,
            office=office,
            parent=form.cleaned_data.get("parent"),
            kind=form.cleaned_data.get("kind") or None,
            is_active=form.cleaned_data.get("is_active"),
            is_assignable=form.cleaned_data.get("is_assignable"),
        )
    except PermissionDenied as exc:
        return JsonResponse({"errors": {"fields": {}, "form": [str(exc)]}}, status=403)
    return JsonResponse({"preview": preview})


@enforce_policy("office_administration_contact")
@require_POST
def office_administration_contact(request: HttpRequest, office_id: int):
    actor = cast(User, request.user)
    office = _office(request, office_id)
    form = OfficeContactUpsertForm(request.POST, office=office)
    if not form.is_valid():
        return _render_detail(request, office, errors=form_errors(form), status=422)
    try:
        upsert_contact(
            actor=actor,
            office=office,
            user=form.cleaned_data["user"],
            assignment_type=form.cleaned_data["assignment_type"],
            is_primary=bool(form.cleaned_data.get("is_primary")),
            starts_at=form.cleaned_data.get("starts_at"),
            ends_at=form.cleaned_data.get("ends_at"),
            expected_version=form.cleaned_data.get("expected_version", ""),
            assignment_id=form.cleaned_data.get("assignment"),
        )
    except StaleOfficeVersion:
        return _render_detail(request, office, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request, office, errors=_validation_error_payload(exc), status=422
        )
    return redirect("admin_office", office_id=office.pk)


@enforce_policy("office_administration_contact_end")
@require_POST
def office_administration_contact_end(request: HttpRequest, office_id: int):
    actor = cast(User, request.user)
    office = _office(request, office_id)
    form = OfficeContactEndForm(request.POST)
    if not form.is_valid():
        return _render_detail(request, office, errors=form_errors(form), status=422)
    get_object_or_404(
        OfficeContactAssignment, pk=form.cleaned_data["assignment"], office=office
    )
    try:
        end_contact(
            actor=actor,
            office=office,
            assignment_id=form.cleaned_data["assignment"],
            expected_version=form.cleaned_data.get("expected_version", ""),
            ends_at=form.cleaned_data.get("ends_at"),
        )
    except StaleOfficeVersion:
        return _render_detail(request, office, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request, office, errors=_validation_error_payload(exc), status=422
        )
    return redirect("admin_office", office_id=office.pk)


@enforce_policy("office_info")
@require_GET
@inertia("OfficeInfo")
def office_info(request: HttpRequest):
    """Agent-facing office brochure for the signed-in user's primary office."""
    actor = cast(User, request.user)
    office = actor.office
    if office is None:
        return {
            "officeInfo": None,
            "empty": {
                "title": "No office assigned",
                "description": (
                    "Your profile does not have a primary office yet. "
                    "Update your profile or contact your branch administrator."
                ),
            },
        }
    return {
        "officeInfo": office_info_payload(office, include_internal=True),
        "empty": None,
    }
