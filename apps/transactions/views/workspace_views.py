"""Transaction workspace shell and section mutation views."""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from inertia import inertia, render

from apps.transactions.concurrency import StaleTransactionVersion
from apps.transactions.key_dates import end_key_date, save_key_date
from apps.transactions.listing import build_transaction_list
from apps.transactions.models import Transaction
from apps.transactions.notes import end_note, save_note
from apps.transactions.parties import end_party, save_party
from apps.transactions.property_data import save_property
from apps.transactions.services import upsert_assignment
from apps.transactions.taxonomy import AssignmentRole
from apps.transactions.workspace import (
    load_workspace_transaction,
    resolve_section,
    workspace_payload,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.flash import set_flash

WORKSPACE_PAGE = "TransactionWorkspace"
MY_LIST_PAGE = "MyTransactions"
ADMIN_LIST_PAGE = "AdminTransactions"


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _json_body(request: HttpRequest) -> dict[str, Any]:
    if request.content_type and "application/json" in request.content_type:
        try:
            raw = json.loads(request.body.decode() or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}
    return {k: request.POST.get(k) for k in request.POST}


def _expected_version(body: dict[str, Any]) -> str:
    return str(body.get("expectedVersion") or body.get("expected_version") or "")


def _validation_errors(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        fields = {
            str(k): [str(m) for m in (v if isinstance(v, list) else [v])]
            for k, v in exc.message_dict.items()
        }
        return {"fields": fields, "form": []}
    messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
    return {"fields": {}, "form": [str(m) for m in messages]}


def _workspace_error(
    request: HttpRequest,
    tx: Transaction | None,
    public_id: UUID,
    exc: Exception,
    *,
    section: str | None = None,
) -> HttpResponse:
    actor = _actor(request)
    if tx is None:
        try:
            tx = load_workspace_transaction(actor, public_id)
        except Transaction.DoesNotExist as missing:
            raise Http404("Transaction not found.") from missing
    errors = (
        _validation_errors(exc)
        if isinstance(exc, ValidationError)
        else {
            "fields": {},
            "form": [str(exc)],
        }
    )
    if isinstance(exc, StaleTransactionVersion):
        errors = {"fields": {}, "form": [str(exc.messages[0] if exc.messages else exc)]}
    props = {
        **workspace_payload(actor, tx, section=section),
        "errors": errors,
    }
    response = render(request, WORKSPACE_PAGE, props)
    response.status_code = 409 if isinstance(exc, StaleTransactionVersion) else 422
    return response


def _workspace_redirect(public_id: UUID, *, section: str, flash: str | None = None):
    url = reverse("transaction_workspace", kwargs={"public_id": public_id})
    url = f"{url}?section={section}"
    response = redirect(url)
    return response


@enforce_policy("my_transactions")
@require_GET
@inertia(MY_LIST_PAGE)
def my_transactions(request: HttpRequest):
    actor = _actor(request)
    page = int(request.GET.get("page") or 1)
    return build_transaction_list(
        actor,
        q=request.GET.get("q") or "",
        status=request.GET.get("status") or "",
        transaction_type=request.GET.get("transactionType")
        or request.GET.get("transaction_type")
        or "",
        page=page,
        mine_only=True,
    )


@enforce_policy("operations_admin_transactions")
@require_GET
@inertia(ADMIN_LIST_PAGE)
def admin_transactions(request: HttpRequest):
    actor = _actor(request)
    page = int(request.GET.get("page") or 1)
    return build_transaction_list(
        actor,
        q=request.GET.get("q") or "",
        status=request.GET.get("status") or "",
        transaction_type=request.GET.get("transactionType")
        or request.GET.get("transaction_type")
        or "",
        page=page,
        mine_only=False,
    )


@enforce_policy("transaction_workspace")
@require_GET
@inertia(WORKSPACE_PAGE)
def transaction_workspace(request: HttpRequest, public_id: uuid.UUID):
    try:
        tx = load_workspace_transaction(_actor(request), public_id)
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    section = resolve_section(request.GET.get("section"))
    return workspace_payload(_actor(request), tx, section=section)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_party_save(request: HttpRequest, public_id: uuid.UUID):
    body = _json_body(request)
    party_id = body.get("partyPublicId") or body.get("party_public_id")
    try:
        tx, _party = save_party(
            actor=_actor(request),
            public_id=public_id,
            expected_version=_expected_version(body),
            payload=body,
            party_public_id=UUID(str(party_id)) if party_id else None,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc, section="parties")
    set_flash(request, level="success", message="Party saved.")
    return _workspace_redirect(tx.public_id, section="parties")


@enforce_policy("transaction_workspace_write")
@require_http_methods(["POST", "DELETE"])
def transaction_party_end(request: HttpRequest, public_id: uuid.UUID):
    body = _json_body(request)
    party_id = body.get("partyPublicId") or body.get("party_public_id")
    if not party_id:
        return _workspace_error(
            request,
            None,
            public_id,
            ValidationError({"partyPublicId": ["Required."]}),
            section="parties",
        )
    try:
        tx = end_party(
            actor=_actor(request),
            public_id=public_id,
            expected_version=_expected_version(body),
            party_public_id=UUID(str(party_id)),
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc, section="parties")
    set_flash(request, level="success", message="Party removed.")
    return _workspace_redirect(tx.public_id, section="parties")


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_property_save(request: HttpRequest, public_id: uuid.UUID):
    body = _json_body(request)
    try:
        tx = save_property(
            actor=_actor(request),
            public_id=public_id,
            expected_version=_expected_version(body),
            payload=body,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc, section="property")
    set_flash(request, level="success", message="Property updated.")
    return _workspace_redirect(tx.public_id, section="property")


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_key_date_save(request: HttpRequest, public_id: uuid.UUID):
    body = _json_body(request)
    key_id = body.get("keyDatePublicId") or body.get("key_date_public_id")
    try:
        tx, _row = save_key_date(
            actor=_actor(request),
            public_id=public_id,
            expected_version=_expected_version(body),
            payload=body,
            key_date_public_id=UUID(str(key_id)) if key_id else None,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc, section="dates")
    set_flash(request, level="success", message="Key date saved.")
    return _workspace_redirect(tx.public_id, section="dates")


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_key_date_end(request: HttpRequest, public_id: uuid.UUID):
    body = _json_body(request)
    key_id = body.get("keyDatePublicId") or body.get("key_date_public_id")
    if not key_id:
        return _workspace_error(
            request,
            None,
            public_id,
            ValidationError({"keyDatePublicId": ["Required."]}),
            section="dates",
        )
    try:
        tx = end_key_date(
            actor=_actor(request),
            public_id=public_id,
            expected_version=_expected_version(body),
            key_date_public_id=UUID(str(key_id)),
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc, section="dates")
    set_flash(request, level="success", message="Key date removed.")
    return _workspace_redirect(tx.public_id, section="dates")


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_note_save(request: HttpRequest, public_id: uuid.UUID):
    body = _json_body(request)
    note_id = body.get("notePublicId") or body.get("note_public_id")
    try:
        tx, _note = save_note(
            actor=_actor(request),
            public_id=public_id,
            expected_version=_expected_version(body),
            payload=body,
            note_public_id=UUID(str(note_id)) if note_id else None,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc, section="notes")
    set_flash(request, level="success", message="Note saved.")
    return _workspace_redirect(tx.public_id, section="notes")


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_note_end(request: HttpRequest, public_id: uuid.UUID):
    body = _json_body(request)
    note_id = body.get("notePublicId") or body.get("note_public_id")
    if not note_id:
        return _workspace_error(
            request,
            None,
            public_id,
            ValidationError({"notePublicId": ["Required."]}),
            section="notes",
        )
    try:
        tx = end_note(
            actor=_actor(request),
            public_id=public_id,
            expected_version=_expected_version(body),
            note_public_id=UUID(str(note_id)),
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc, section="notes")
    set_flash(request, level="success", message="Note removed.")
    return _workspace_redirect(tx.public_id, section="notes")


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_assignment_save(request: HttpRequest, public_id: uuid.UUID):
    from django.db import transaction as db_transaction

    from apps.transactions.concurrency import (
        assert_fresh,
        can_manage_workspace,
        lock_transaction,
    )
    from apps.transactions.services import ActorContext
    from apps.user.services.role_assignments import get_effective_access

    body = _json_body(request)
    actor = _actor(request)
    role = str(body.get("role") or AssignmentRole.CO_AGENT).strip()
    user_id = body.get("userId") or body.get("user_id")
    try:
        tx = load_workspace_transaction(actor, public_id)
        if not can_manage_workspace(actor, tx):
            raise PermissionDenied("You cannot edit this transaction.")
        with db_transaction.atomic():
            locked = lock_transaction(tx.pk)
            assert_fresh(locked, _expected_version(body))
            if not user_id:
                raise ValidationError({"userId": ["Select a person."]})
            assignee = User.objects.filter(pk=int(user_id)).first()
            if assignee is None:
                raise ValidationError({"userId": ["Person not found."]})
            access = get_effective_access(actor)
            ctx = ActorContext(
                user=actor,
                permissions=frozenset(access.permissions),
            )
            upsert_assignment(
                actor=ctx,
                tx=locked,
                user=assignee,
                role=role,
            )
            locked.refresh_from_db(fields=["updated_at"])
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc, section="assignments")
    set_flash(request, level="success", message="Assignment saved.")
    return _workspace_redirect(public_id, section="assignments")
