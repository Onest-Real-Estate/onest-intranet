"""Guided create / draft / prepare views for transactions."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.transactions.creation import (
    DuplicateWarning,
    build_new_transaction_page,
    prepare_transaction,
    save_draft,
    search_transaction_people,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.flash import set_flash

NEW_PAGE = "TransactionNew"


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _validation_payload(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        fields = {
            key: [str(message) for message in messages]
            for key, messages in exc.message_dict.items()
        }
        form_messages = fields.pop("__all__", [])
        if "form" in fields:
            form_messages = [*form_messages, *fields.pop("form")]
        return {"fields": fields, "form": form_messages}
    return {"fields": {}, "form": [str(message) for message in exc.messages]}


def _draft_from_request(request: HttpRequest) -> dict[str, Any]:
    return {key: request.POST.get(key) for key in request.POST}


def _render_new_error(
    request: HttpRequest,
    *,
    errors: dict[str, Any],
    draft: dict[str, Any],
    duplicates: list[dict[str, str]] | None = None,
    status: int = 422,
) -> HttpResponse:
    payload = build_new_transaction_page(
        _actor(request),
        draft=draft,
        errors=errors,
        duplicates=duplicates,
    )
    response = render(request, NEW_PAGE, payload)
    response.status_code = status
    return response


@enforce_policy("transaction_create")
@require_GET
@inertia(NEW_PAGE)
def transaction_new(request: HttpRequest):
    return build_new_transaction_page(_actor(request))


@enforce_policy("transaction_create")
@require_POST
def transaction_draft_save(request: HttpRequest):
    draft = _draft_from_request(request)
    try:
        tx = save_draft(user=_actor(request), data=draft)
    except PermissionDenied as exc:
        return _render_new_error(
            request,
            errors={"fields": {}, "form": [str(exc)]},
            draft=draft,
            status=403,
        )
    except ValidationError as exc:
        return _render_new_error(
            request,
            errors=_validation_payload(exc),
            draft=draft,
        )
    set_flash(request, level="success", message=f"Draft {tx.reference} saved.")
    draft = {**draft, "publicId": str(tx.public_id), "reference": tx.reference}
    response = render(
        request,
        NEW_PAGE,
        build_new_transaction_page(_actor(request), draft=draft),
    )
    return response


@enforce_policy("transaction_create")
@require_POST
def transaction_prepare(request: HttpRequest):
    draft = _draft_from_request(request)
    confirmed = (request.POST.get("confirmedDuplicate") or "").strip() in {
        "1",
        "true",
        "True",
        "yes",
    }
    try:
        tx = prepare_transaction(
            user=_actor(request),
            data=draft,
            confirmed_duplicate=confirmed,
        )
    except DuplicateWarning as exc:
        return _render_new_error(
            request,
            errors=_validation_payload(exc),
            draft=draft,
            duplicates=exc.matches,
            status=409,
        )
    except PermissionDenied as exc:
        return _render_new_error(
            request,
            errors={"fields": {}, "form": [str(exc)]},
            draft=draft,
            status=403,
        )
    except ValidationError as exc:
        return _render_new_error(
            request,
            errors=_validation_payload(exc),
            draft=draft,
        )
    set_flash(
        request,
        level="success",
        message=f"Transaction {tx.reference} is preparing.",
    )
    return redirect("transaction_workspace", public_id=tx.public_id)


@enforce_policy("transaction_create")
@require_GET
def transaction_people_search(request: HttpRequest):
    role = (request.GET.get("role") or "agent").strip()
    if role not in {"agent", "coordinator"}:
        role = "agent"
    results = search_transaction_people(
        _actor(request),
        q=request.GET.get("q") or "",
        role=role,
        office_key=request.GET.get("officeKey") or request.GET.get("office_key") or "",
    )
    return JsonResponse({"results": results})
