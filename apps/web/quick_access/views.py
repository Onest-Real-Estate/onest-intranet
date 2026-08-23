"""Quick Access endpoints: administration, plus the dashboard's click beacon.

Every administrative entry point re-derives the actor's authority and scope
before it reads or writes: a link is always loaded through
``manageable_link_queryset``, never by bare id, so a link outside the actor's
scope is a 404 rather than a 403 — confirming that an id exists is itself a
disclosure across a scope boundary.

:func:`quick_access_click` is the one endpoint here that is not administrative.
It belongs to the dashboard panel and answers ``204`` unconditionally; see
:mod:`apps.web.quick_access.analytics` for why it declines to say more.
"""

from __future__ import annotations

from typing import cast

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import validation_errors
from apps.web.models import QuickAccessLink
from apps.web.quick_access.administration import (
    BroadExposureNotAcknowledged,
    StaleQuickAccessVersion,
    create_link,
    ensure_can_create,
    ensure_manage_authority,
    manageable_link_queryset,
    reorder_links,
    set_link_state,
    update_link,
)
from apps.web.quick_access.analytics import record_click
from apps.web.quick_access.forms import (
    QuickAccessLinkForm,
    QuickAccessReorderForm,
    QuickAccessStateForm,
)
from apps.web.quick_access.payloads import form_props, index_props

__all__ = [
    "quick_access_index",
    "quick_access_new",
    "quick_access_edit",
    "quick_access_create",
    "quick_access_update",
    "quick_access_state",
    "quick_access_reorder",
    "quick_access_click",
]

INDEX_ROUTE = "admin_quick_access"


def _int_param(request: HttpRequest, name: str) -> int | None:
    raw = request.GET.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _target(request: HttpRequest, link_id: int) -> QuickAccessLink:
    actor = cast(User, request.user)
    return get_object_or_404(manageable_link_queryset(actor), pk=link_id)


def _render_form(
    request: HttpRequest,
    *,
    link: QuickAccessLink | None,
    errors: dict,
    posted,
    status: int,
    pending_confirmation: list[dict[str, str]] | None = None,
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        "QuickAccessLinkForm",
        form_props(
            actor,
            link=link,
            errors=errors,
            posted=posted,
            pending_confirmation=pending_confirmation,
        ),
    )
    response.status_code = status
    return response


@enforce_policy("operations_admin_quick_access")
@require_GET
@inertia("QuickAccessAdministration")
def quick_access_index(request: HttpRequest):
    actor = cast(User, request.user)
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    # ``?create=1`` is how Quick Create opens the drawer here rather than
    # sending the administrator to the standalone form. It opens a drawer and
    # nothing else — the create endpoint applies every check on submit.
    return index_props(
        actor,
        query=request.GET.get("q", "").strip(),
        status=request.GET.get("status", "").strip(),
        page=page,
        preview_role=request.GET.get("previewRole", "").strip(),
        preview_office=_int_param(request, "previewOffice"),
        create_sheet=(
            {"open": True, "draft": {}, "pendingConfirmation": []}
            if request.GET.get("create") == "1"
            else None
        ),
    )


@enforce_policy("quick_access_new")
@require_GET
@inertia("QuickAccessLinkForm")
def quick_access_new(request: HttpRequest):
    actor = cast(User, request.user)
    ensure_can_create(actor)
    return form_props(actor)


@enforce_policy("quick_access_edit")
@require_GET
@inertia("QuickAccessLinkForm")
def quick_access_edit(request: HttpRequest, link_id: int):
    actor = cast(User, request.user)
    link = _target(request, link_id)
    ensure_manage_authority(actor, link)
    return form_props(actor, link=link)


def _submit(request: HttpRequest, link: QuickAccessLink | None) -> HttpResponse:
    actor = cast(User, request.user)
    # The drawer on the queue page posts here too. It differs only in where a
    # rejection renders, so validation and authorization stay one path.
    from_sheet = link is None and request.POST.get("context") == "sheet"
    form = QuickAccessLinkForm(
        request.POST, instance=link or QuickAccessLink(), actor=actor
    )
    if not form.is_valid():
        errors = validation_errors(form)
        if from_sheet:
            return _render_index_with_sheet(request, errors=errors)
        return _render_form(
            request,
            link=link,
            errors=errors,
            posted=request.POST,
            status=422,
        )
    acknowledged = bool(form.cleaned_data.get("acknowledge_exposure"))
    payload = {
        "actor": actor,
        "cleaned": {
            **form.field_values,
            "stable_key": form.cleaned_data["stable_key"],
            "is_active": form.cleaned_data.get("is_active", True),
        },
        "role_codes": form.cleaned_data.get("roles", []),
        "office_ids": form.office_ids,
        "company_wide": bool(form.cleaned_data.get("company_wide")),
        "acknowledged": acknowledged,
    }
    try:
        if link is None:
            create_link(**payload)
        else:
            update_link(
                link=link,
                expected_version=form.cleaned_data.get("expected_version", ""),
                **payload,
            )
    except BroadExposureNotAcknowledged as exc:
        # 422 with the diff attached: the page shows the confirmation dialog
        # and resubmits with the acknowledgement, so a widening change is never
        # applied by a single click.
        if from_sheet:
            return _render_index_with_sheet(
                request,
                errors={"fields": {}, "form": [str(exc.messages[0])]},
                pending_confirmation=exc.changes,
            )
        return _render_form(
            request,
            link=link,
            errors={"fields": {}, "form": [str(exc.messages[0])]},
            posted=request.POST,
            status=422,
            pending_confirmation=exc.changes,
        )
    except StaleQuickAccessVersion as exc:
        # 409, not 422: nothing typed is wrong — the record moved underneath.
        return _render_form(
            request,
            link=QuickAccessLink.objects.get(pk=link.pk) if link else None,
            errors={"fields": {}, "form": [exc.message]},
            posted=request.POST,
            status=409,
        )
    except ValidationError as exc:
        errors = {
            "fields": {
                key: [str(item) for item in value]
                for key, value in (exc.message_dict or {}).items()
                if key != "__all__"
            },
            "form": [str(item) for item in exc.messages]
            if not getattr(exc, "message_dict", None)
            else [str(item) for item in exc.message_dict.get("__all__", [])],
        }
        if from_sheet:
            return _render_index_with_sheet(request, errors=errors)
        return _render_form(
            request,
            link=link,
            errors=errors,
            posted=request.POST,
            status=422,
        )
    return redirect(INDEX_ROUTE)


@enforce_policy("quick_access_create")
@require_POST
def quick_access_create(request: HttpRequest):
    ensure_can_create(cast(User, request.user))
    return _submit(request, None)


@enforce_policy("quick_access_update")
@require_POST
def quick_access_update(request: HttpRequest, link_id: int):
    link = _target(request, link_id)
    ensure_manage_authority(cast(User, request.user), link)
    return _submit(request, link)


@enforce_policy("quick_access_state")
@require_POST
def quick_access_state(request: HttpRequest, link_id: int):
    actor = cast(User, request.user)
    link = _target(request, link_id)
    form = QuickAccessStateForm(request.POST)
    if not form.is_valid():
        return _render_index_with_error(request, "Unsupported action.")
    try:
        set_link_state(actor=actor, link=link, action=form.cleaned_data["action"])
    except ValidationError as exc:
        return _render_index_with_error(request, "; ".join(exc.messages))
    return redirect(INDEX_ROUTE)


@enforce_policy("quick_access_reorder")
@require_POST
def quick_access_reorder(request: HttpRequest):
    actor = cast(User, request.user)
    form = QuickAccessReorderForm(request.POST)
    if not form.is_valid():
        return _render_index_with_error(request, "Send the new order.")
    try:
        reorder_links(actor=actor, link_ids=form.cleaned_data["order"])
    except ValidationError as exc:
        return _render_index_with_error(request, "; ".join(exc.messages))
    return redirect(INDEX_ROUTE)


def _sheet_draft(posted) -> dict:
    return {key: posted.getlist(key) for key in posted}


def _render_index_with_sheet(
    request: HttpRequest,
    *,
    errors: dict,
    pending_confirmation: list[dict[str, str]] | None = None,
    status: int = 422,
) -> HttpResponse:
    """Re-render the queue with the create drawer reopened and repopulated.

    A rejected create comes back as the page the administrator was on, so they
    fix the field they were already looking at. The exposure confirmation rides
    the same path: the first submit returns the diff, the second carries the
    acknowledgement — a widening change is still never applied by one click.
    """
    actor = cast(User, request.user)
    response = render(
        request,
        "QuickAccessAdministration",
        index_props(
            actor,
            errors=errors,
            create_sheet={
                "open": True,
                "draft": _sheet_draft(request.POST),
                "pendingConfirmation": pending_confirmation or [],
            },
        ),
    )
    response.status_code = status
    return response


def _render_index_with_error(request: HttpRequest, message: str) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        "QuickAccessAdministration",
        {**index_props(actor), "errors": {"fields": {}, "form": [message]}},
    )
    response.status_code = 422
    return response


# --------------------------------------------------------------------------- #
# Dashboard panel
# --------------------------------------------------------------------------- #


@enforce_policy("quick_access_click")
@require_POST
def quick_access_click(request: HttpRequest) -> HttpResponse:
    """Record that the signed-in reader opened a launcher. Always ``204``.

    The response is deliberately uniform. Answering ``404`` for a key the
    reader may not see would let the dashboard be used to enumerate other
    offices' configuration, and answering ``400`` for a malformed one would
    tell a caller when it had guessed the shape right. Nothing here is worth
    that: the browser has already navigated by the time this returns.
    """
    record_click(cast(User, request.user), request.POST.get("key", ""))
    return HttpResponse(status=204)
