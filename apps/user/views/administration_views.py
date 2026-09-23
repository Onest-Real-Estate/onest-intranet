"""Broker-controlled profile administration — a surface of its own.

Kept apart from ``auth_views`` on purpose. The self-service endpoints there
never address a user other than ``request.user``; these ones always take a
target from the URL, so every entry point re-derives the actor's authority and
scope before it reads or writes anything. Mixing the two would mean one POST
contract carrying both privileges.
"""

from enum import StrEnum
from typing import cast
from urllib.parse import parse_qsl, urlencode

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.web.authorization import enforce_policy

from ..forms import (
    AccountStateForm,
    AgentAdministrationForm,
    RoleAssignmentGrantForm,
    RoleAssignmentRevokeForm,
    administration_page_props,
    form_errors,
)
from ..models import User, UserRoleAssignment
from ..services.account_state import set_account_state
from ..services.agent_administration import (
    StaleAdministrationVersion,
    administered_user_queryset,
    ensure_change_authority,
    ensure_view_authority,
    grant_role_assignment,
    revoke_role_assignment_for_user,
    update_administration,
)

__all__ = [
    "user_administration",
    "user_administration_submit",
    "user_administration_roles",
    "user_account_state",
]


def _target(request: HttpRequest, user_id: int) -> User:
    """Load the subject through the actor's own scope, never by bare id.

    A user outside the actor's scope is a 404 rather than a 403: confirming
    that an id exists is itself a disclosure across a scope boundary.
    """
    actor = cast(User, request.user)
    return get_object_or_404(administered_user_queryset(actor), pk=user_id)


def _render_administration(
    request: HttpRequest,
    target: User,
    *,
    errors: dict,
    posted=None,
    status: int,
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        "UserAdministration",
        administration_page_props(actor, target, errors=errors, posted=posted),
    )
    response.status_code = status
    return response


@enforce_policy("user_administration")
@require_GET
@inertia("UserAdministration")
def user_administration(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(request, user_id)
    ensure_view_authority(actor, target)
    return administration_page_props(actor, target)


@enforce_policy("user_administration_submit")
@require_POST
def user_administration_submit(request: HttpRequest, user_id: int):
    actor = cast(User, request.user)
    target = _target(request, user_id)
    ensure_change_authority(actor, target)

    form = AgentAdministrationForm(request.POST, instance=target, actor=actor)
    if not form.is_valid():
        return _render_administration(
            request,
            target,
            errors=form_errors(form),
            posted=request.POST,
            status=422,
        )

    try:
        update_administration(
            actor=actor,
            target=target,
            cleaned={
                field: form.cleaned_data[field]
                for field in form.Meta.fields
                if field in form.cleaned_data
            },
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleAdministrationVersion as exc:
        # 409, not 422: nothing the administrator typed is wrong — the record
        # underneath them moved, and they need to see the newer values first.
        return _render_administration(
            request,
            User.objects.get(pk=target.pk),
            errors={"fields": {}, "form": [exc.message]},
            posted=request.POST,
            status=409,
        )
    except ValidationError as exc:
        return _render_administration(
            request,
            target,
            errors={"fields": {}, "form": list(exc.messages)},
            posted=request.POST,
            status=422,
        )

    return redirect("user_administration", user_id=target.pk)


@enforce_policy("user_administration_roles")
@require_POST
def user_administration_roles(request: HttpRequest, user_id: int):
    """Grant or revoke one role assignment for the target user."""
    actor = cast(User, request.user)
    target = _target(request, user_id)
    ensure_change_authority(actor, target)

    action = request.POST.get("action", "")
    if action == "revoke":
        return _revoke_assignment(request, actor, target)
    if action == "grant":
        return _grant_assignment(request, actor, target)
    raise PermissionDenied("Unsupported role assignment action.")


def _grant_assignment(request: HttpRequest, actor: User, target: User):
    form = RoleAssignmentGrantForm(request.POST, actor=actor)
    if not form.is_valid():
        return _render_administration(
            request, target, errors=form_errors(form), status=422
        )
    try:
        grant_role_assignment(
            actor=actor,
            target=target,
            role=form.cleaned_data["role"],
            scope_type=form.cleaned_data["scope_type"],
            scope_office=form.cleaned_data.get("scope_office"),
            starts_at=form.cleaned_data.get("starts_at"),
            ends_at=form.cleaned_data.get("ends_at"),
            business_reason=form.cleaned_data["business_reason"],
        )
    except ValidationError as exc:
        return _render_administration(
            request,
            target,
            errors={"fields": {}, "form": list(exc.messages)},
            status=422,
        )
    return redirect("user_administration", user_id=target.pk)


def _revoke_assignment(request: HttpRequest, actor: User, target: User):
    form = RoleAssignmentRevokeForm(request.POST)
    if not form.is_valid():
        return _render_administration(
            request, target, errors=form_errors(form), status=422
        )
    assignment = get_object_or_404(
        UserRoleAssignment.objects.select_related("scope_office", "user"),
        pk=form.cleaned_data["assignment"],
        user=target,
    )
    try:
        revoke_role_assignment_for_user(
            actor=actor,
            target=target,
            assignment=assignment,
            business_reason=form.cleaned_data["business_reason"],
        )
    except ValidationError as exc:
        return _render_administration(
            request,
            target,
            errors={"fields": {}, "form": list(exc.messages)},
            status=422,
        )
    return redirect("user_administration", user_id=target.pk)


class AccountStateReturn(StrEnum):
    """Where an account-state change goes back to. The record by default."""

    RECORD = "record"
    USERS = "users"


#: Query keys the Users list understands. A return query is rebuilt from these
#: alone, so the redirect can never carry anything the list would not accept.
USERS_LIST_KEYS = frozenset(
    {
        "q",
        "office",
        "region",
        "role",
        "status",
        "account",
        "onboarding",
        "contract",
        "lastLogin",
        "page",
        "pageSize",
        "sort",
        "direction",
    }
)


def _users_list_query(raw: str) -> dict[str, str]:
    return {
        key: value[:120]
        for key, value in parse_qsl((raw or "").lstrip("?")[:1000])
        if key in USERS_LIST_KEYS and value
    }


@enforce_policy("user_account_state")
@require_POST
def user_account_state(request: HttpRequest, user_id: int):
    """Disable or reactivate one account, once, with a reason on the record.

    Separate from ``user_administration_submit`` all the way down: its own
    policy, its own permission, its own form, and its own service. Nothing
    about somebody's access can ride along on a record edit, and nothing about
    their record can ride along on a lockout.

    Started from a Users row (``returnTo=users``), success and refusal both
    land back on that list with its filters intact rather than on a record the
    administrator never opened.
    """
    actor = cast(User, request.user)
    target = _target(request, user_id)
    ensure_view_authority(actor, target)
    from_list = request.POST.get("returnTo") == AccountStateReturn.USERS
    list_query = _users_list_query(request.POST.get("returnQuery") or "")

    def refused(errors: dict, status: int, *, fresh: bool = False) -> HttpResponse:
        if from_list:
            from .directory_views import directory_props

            response = render(
                request,
                "UserDirectory",
                directory_props(actor, list_query, errors=errors),
            )
            response.status_code = status
            return response
        return _render_administration(
            request,
            User.objects.get(pk=target.pk) if fresh else target,
            errors=errors,
            status=status,
        )

    form = AccountStateForm(request.POST)
    if not form.is_valid():
        return refused(form_errors(form), 422)

    try:
        set_account_state(
            actor=actor,
            target=target,
            enabled=form.enabled,
            business_reason=form.cleaned_data["business_reason"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleAdministrationVersion as exc:
        return refused({"fields": {}, "form": [exc.message]}, 409, fresh=True)
    except ValidationError as exc:
        return refused({"fields": {}, "form": list(exc.messages)}, 422)

    if from_list:
        url = reverse("admin_users")
        return redirect(f"{url}?{urlencode(list_query)}" if list_query else url)
    return redirect("user_administration", user_id=target.pk)
