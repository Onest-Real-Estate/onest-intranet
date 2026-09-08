"""Role and scope assignment administration — dedicated ops surface.

Guarded by ``web.assign_user_roles``. Per-user grant/revoke on the
administrative record remains available through ``user_administration_roles``;
this module owns the Assign User Roles destination under Operations.
"""

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
    RoleAssignmentEditForm,
    RoleAssignmentGrantForm,
    RoleAssignmentPreviewForm,
    RoleAssignmentRevokeForm,
    form_errors,
)
from ..models import User, UserRoleAssignment
from ..services.agent_administration import administered_user_queryset
from ..services.role_assignment_admin import (
    StaleRoleAssignmentVersion,
    admin_edit_assignment,
    admin_grant_assignment,
    admin_revoke_assignment,
    build_assignment_list,
    parse_list_filters,
    preview_edit,
    preview_grant,
    preview_revoke,
    workspace_payload,
)

__all__ = [
    "role_assignment_index",
    "role_assignment_workspace",
    "role_assignment_preview",
    "role_assignment_mutate",
]


def _target(request: HttpRequest, user_id: int) -> User:
    actor = cast(User, request.user)
    return get_object_or_404(administered_user_queryset(actor), pk=user_id)


def _workspace_props(
    actor: User,
    target: User,
    *,
    errors: dict | None = None,
    preview: dict | None = None,
) -> dict:
    return {
        "workspace": workspace_payload(actor, target),
        "validation": errors or empty_validation_errors(),
        "preview": preview,
        "scope": operations_scope_payload(actor),
    }


def _render_workspace(
    request: HttpRequest,
    target: User,
    *,
    errors: dict,
    preview: dict | None = None,
    status: int,
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        "RoleAssignmentWorkspace",
        _workspace_props(actor, target, errors=errors, preview=preview),
    )
    response.status_code = status
    return response


@enforce_policy("operations_admin_assign_roles")
@require_GET
@inertia("RoleAssignmentAdministration")
def role_assignment_index(request: HttpRequest):
    actor = cast(User, request.user)
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    filters = parse_list_filters(request.GET)
    payload = build_assignment_list(actor, filters=filters, page=page)
    return {
        **payload,
        "scope": operations_scope_payload(actor),
    }


@enforce_policy("role_assignment_workspace")
@require_GET
@inertia("RoleAssignmentWorkspace")
def role_assignment_workspace(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(request, user_id)
    return _workspace_props(actor, target)


@enforce_policy("role_assignment_preview")
@require_POST
def role_assignment_preview(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(request, user_id)
    form = RoleAssignmentPreviewForm(request.POST, actor=actor)
    if not form.is_valid():
        return JsonResponse({"errors": validation_errors(form)}, status=422)
    action = form.cleaned_data["action"]
    try:
        if action == "grant":
            preview = preview_grant(
                actor=actor,
                target=target,
                role=form.cleaned_data.get("role") or "",
                scope_type=form.cleaned_data.get("scope_type") or "",
                scope_office=form.cleaned_data.get("scope_office"),
                starts_at=form.cleaned_data.get("starts_at"),
                ends_at=form.cleaned_data.get("ends_at"),
            )
        elif action == "edit":
            assignment = get_object_or_404(
                UserRoleAssignment.objects.select_related("scope_office", "user"),
                pk=form.cleaned_data.get("assignment"),
                user=target,
            )
            preview = preview_edit(
                actor=actor,
                target=target,
                assignment=assignment,
                starts_at=form.cleaned_data.get("starts_at"),
                ends_at=form.cleaned_data.get("ends_at"),
            )
        else:
            assignment = get_object_or_404(
                UserRoleAssignment.objects.select_related("scope_office", "user"),
                pk=form.cleaned_data.get("assignment"),
                user=target,
            )
            preview = preview_revoke(actor=actor, target=target, assignment=assignment)
    except ValidationError as exc:
        return JsonResponse(
            {"errors": {"fields": {}, "form": list(exc.messages)}},
            status=422,
        )
    except PermissionDenied as exc:
        return JsonResponse({"errors": {"fields": {}, "form": [str(exc)]}}, status=403)
    return JsonResponse({"preview": preview})


@enforce_policy("role_assignment_mutate")
@require_POST
def role_assignment_mutate(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(request, user_id)
    action = request.POST.get("action", "")
    if action == "grant":
        return _mutate_grant(request, actor, target)
    if action == "edit":
        return _mutate_edit(request, actor, target)
    if action == "revoke":
        return _mutate_revoke(request, actor, target)
    raise PermissionDenied("Unsupported role assignment action.")


def _mutate_grant(request: HttpRequest, actor: User, target: User) -> HttpResponse:
    form = RoleAssignmentGrantForm(request.POST, actor=actor)
    if not form.is_valid():
        return _render_workspace(request, target, errors=form_errors(form), status=422)
    try:
        admin_grant_assignment(
            actor=actor,
            target=target,
            role=form.cleaned_data["role"],
            scope_type=form.cleaned_data["scope_type"],
            scope_office=form.cleaned_data.get("scope_office"),
            starts_at=form.cleaned_data.get("starts_at"),
            ends_at=form.cleaned_data.get("ends_at"),
            business_reason=form.cleaned_data["business_reason"],
            expected_version=form.cleaned_data.get("expected_version", ""),
            confirmed=bool(form.cleaned_data.get("confirmed")),
        )
    except StaleRoleAssignmentVersion as exc:
        return _render_workspace(
            request,
            User.objects.get(pk=target.pk),
            errors={"fields": {}, "form": [exc.message]},
            status=409,
        )
    except ValidationError as exc:
        return _render_workspace(
            request,
            target,
            errors={"fields": {}, "form": list(exc.messages)},
            status=422,
        )
    return redirect("admin_assign_roles_user", user_id=target.pk)


def _mutate_edit(request: HttpRequest, actor: User, target: User) -> HttpResponse:
    form = RoleAssignmentEditForm(request.POST)
    if not form.is_valid():
        return _render_workspace(request, target, errors=form_errors(form), status=422)
    assignment = get_object_or_404(
        UserRoleAssignment.objects.select_related("scope_office", "user"),
        pk=form.cleaned_data["assignment"],
        user=target,
    )
    try:
        admin_edit_assignment(
            actor=actor,
            target=target,
            assignment=assignment,
            starts_at=form.cleaned_data.get("starts_at"),
            ends_at=form.cleaned_data.get("ends_at"),
            business_reason=form.cleaned_data["business_reason"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleRoleAssignmentVersion as exc:
        return _render_workspace(
            request,
            User.objects.get(pk=target.pk),
            errors={"fields": {}, "form": [exc.message]},
            status=409,
        )
    except ValidationError as exc:
        return _render_workspace(
            request,
            target,
            errors={"fields": {}, "form": list(exc.messages)},
            status=422,
        )
    return redirect("admin_assign_roles_user", user_id=target.pk)


def _mutate_revoke(request: HttpRequest, actor: User, target: User) -> HttpResponse:
    form = RoleAssignmentRevokeForm(request.POST)
    if not form.is_valid():
        return _render_workspace(request, target, errors=form_errors(form), status=422)
    assignment = get_object_or_404(
        UserRoleAssignment.objects.select_related("scope_office", "user"),
        pk=form.cleaned_data["assignment"],
        user=target,
    )
    try:
        admin_revoke_assignment(
            actor=actor,
            target=target,
            assignment=assignment,
            business_reason=form.cleaned_data["business_reason"],
            expected_version=form.cleaned_data.get("expected_version", ""),
            confirmed=bool(form.cleaned_data.get("confirmed")),
        )
    except StaleRoleAssignmentVersion as exc:
        return _render_workspace(
            request,
            User.objects.get(pk=target.pk),
            errors={"fields": {}, "form": [exc.message]},
            status=409,
        )
    except ValidationError as exc:
        return _render_workspace(
            request,
            target,
            errors={"fields": {}, "form": list(exc.messages)},
            status=422,
        )
    return redirect("admin_assign_roles_user", user_id=target.pk)
