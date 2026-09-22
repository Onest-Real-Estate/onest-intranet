"""Transaction document upload, classify, lock, review, and delivery views."""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from inertia import render

from apps.transactions.concurrency import StaleTransactionVersion
from apps.transactions.deal_documents import (
    classify_document,
    lock_version,
    retire_document,
    retry_version_processing,
    serialize_version,
    upload_document,
    upload_revision,
)
from apps.transactions.document_delivery import resolve_and_stream
from apps.transactions.document_reviews import (
    end_review_comment,
    resolve_review_comment,
    save_review_comment,
)
from apps.transactions.models import Transaction, TransactionDocumentVersion
from apps.transactions.workspace import load_workspace_transaction, workspace_payload
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.flash import set_flash

WORKSPACE_PAGE = "TransactionWorkspace"
SECTION = "documents"


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _wants_json(request: HttpRequest) -> bool:
    accept = request.headers.get("Accept", "")
    return (
        "application/json" in accept
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


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


def _json_error(exc: Exception) -> JsonResponse:
    if isinstance(exc, StaleTransactionVersion):
        return JsonResponse(
            {
                "validation": {
                    "fields": {},
                    "form": [str(exc.messages[0] if exc.messages else exc)],
                }
            },
            status=409,
        )
    if isinstance(exc, ValidationError):
        return JsonResponse({"validation": _validation_errors(exc)}, status=422)
    if isinstance(exc, PermissionDenied):
        return JsonResponse(
            {"validation": {"fields": {}, "form": [str(exc)]}},
            status=403,
        )
    return JsonResponse(
        {"validation": {"fields": {}, "form": [str(exc)]}},
        status=422,
    )


def _workspace_error(
    request: HttpRequest,
    tx: Transaction | None,
    public_id: UUID,
    exc: Exception,
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
        else {"fields": {}, "form": [str(exc)]}
    )
    if isinstance(exc, StaleTransactionVersion):
        errors = {
            "fields": {},
            "form": [str(exc.messages[0] if exc.messages else exc)],
        }
    props = {
        **workspace_payload(actor, tx, section=SECTION),
        "errors": errors,
    }
    response = render(request, WORKSPACE_PAGE, props)
    response.status_code = 409 if isinstance(exc, StaleTransactionVersion) else 422
    return response


def _workspace_redirect(public_id: UUID):
    url = reverse("transaction_workspace", kwargs={"public_id": public_id})
    return redirect(f"{url}?section={SECTION}")


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_upload(request: HttpRequest, public_id: uuid.UUID):
    body = _json_body(request)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        exc = ValidationError({"file": ["A file is required."]})
        if _wants_json(request):
            return _json_error(exc)
        return _workspace_error(request, None, public_id, exc)
    try:
        package = upload_document(
            actor=_actor(request),
            public_id=public_id,
            expected_version=_expected_version(body),
            uploaded=uploaded,
            payload=body,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        if _wants_json(request):
            return _json_error(exc)
        return _workspace_error(request, None, public_id, exc)
    if _wants_json(request):
        version = (
            TransactionDocumentVersion.objects.filter(document=package)
            .order_by("-version_number", "-pk")
            .first()
        )
        return JsonResponse(
            {
                "document": {
                    "publicId": str(package.public_id),
                    "title": package.title,
                },
                "version": serialize_version(version, can_manage=True, is_current=False)
                if version
                else None,
            },
            status=201,
        )
    set_flash(request, level="success", message="Document uploaded.")
    return _workspace_redirect(package.transaction.public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_revision(
    request: HttpRequest, public_id: uuid.UUID, document_id: uuid.UUID
):
    body = _json_body(request)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        exc = ValidationError({"file": ["A file is required."]})
        if _wants_json(request):
            return _json_error(exc)
        return _workspace_error(request, None, public_id, exc)
    try:
        version = upload_revision(
            actor=_actor(request),
            public_id=public_id,
            document_public_id=document_id,
            expected_version=_expected_version(body),
            uploaded=uploaded,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        if _wants_json(request):
            return _json_error(exc)
        return _workspace_error(request, None, public_id, exc)
    if _wants_json(request):
        return JsonResponse(
            {"version": serialize_version(version, can_manage=True, is_current=False)},
            status=201,
        )
    set_flash(request, level="success", message="New document version uploaded.")
    return _workspace_redirect(version.document.transaction.public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_classify(
    request: HttpRequest, public_id: uuid.UUID, document_id: uuid.UUID
):
    body = _json_body(request)
    try:
        package = classify_document(
            actor=_actor(request),
            public_id=public_id,
            document_public_id=document_id,
            expected_version=_expected_version(body),
            payload=body,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc)
    set_flash(request, level="success", message="Document classification saved.")
    return _workspace_redirect(package.transaction.public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_retire(
    request: HttpRequest, public_id: uuid.UUID, document_id: uuid.UUID
):
    body = _json_body(request)
    try:
        package = retire_document(
            actor=_actor(request),
            public_id=public_id,
            document_public_id=document_id,
            expected_version=_expected_version(body),
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc)
    set_flash(request, level="success", message="Document retired.")
    return _workspace_redirect(package.transaction.public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_retry(
    request: HttpRequest, public_id: uuid.UUID, version_id: uuid.UUID
):
    body = _json_body(request)
    try:
        version = retry_version_processing(
            actor=_actor(request),
            public_id=public_id,
            version_public_id=version_id,
            expected_version=_expected_version(body),
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc)
    set_flash(request, level="success", message="Document processing queued again.")
    return _workspace_redirect(version.document.transaction.public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_lock(
    request: HttpRequest, public_id: uuid.UUID, version_id: uuid.UUID
):
    body = _json_body(request)
    try:
        version = lock_version(
            actor=_actor(request),
            public_id=public_id,
            version_public_id=version_id,
            expected_version=_expected_version(body),
            payload=body,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc)
    set_flash(request, level="success", message="Document version locked.")
    return _workspace_redirect(version.document.transaction.public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_comment_save(
    request: HttpRequest, public_id: uuid.UUID, version_id: uuid.UUID
):
    body = _json_body(request)
    try:
        row = save_review_comment(
            actor=_actor(request),
            public_id=public_id,
            version_public_id=version_id,
            expected_version=_expected_version(body),
            payload=body,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc)
    set_flash(request, level="success", message="Review comment saved.")
    return _workspace_redirect(row.version.document.transaction.public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_comment_resolve(
    request: HttpRequest, public_id: uuid.UUID, comment_id: uuid.UUID
):
    body = _json_body(request)
    try:
        row = resolve_review_comment(
            actor=_actor(request),
            public_id=public_id,
            comment_public_id=comment_id,
            expected_version=_expected_version(body),
            payload=body,
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc)
    set_flash(request, level="success", message="Review comment updated.")
    return _workspace_redirect(row.version.document.transaction.public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_document_comment_end(
    request: HttpRequest, public_id: uuid.UUID, comment_id: uuid.UUID
):
    body = _json_body(request)
    try:
        row = end_review_comment(
            actor=_actor(request),
            public_id=public_id,
            comment_public_id=comment_id,
            expected_version=_expected_version(body),
        )
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    except (ValidationError, PermissionDenied, StaleTransactionVersion) as exc:
        return _workspace_error(request, None, public_id, exc)
    set_flash(request, level="success", message="Review comment removed.")
    return _workspace_redirect(row.version.document.transaction.public_id)


@enforce_policy("transaction_document_file")
@require_GET
def transaction_document_download(request: HttpRequest, public_id: uuid.UUID):
    return resolve_and_stream(
        request,
        version_public_id=public_id,
        as_attachment=True,
        allow_historical=True,
    )


@enforce_policy("transaction_document_file")
@require_GET
def transaction_document_preview(request: HttpRequest, public_id: uuid.UUID):
    return resolve_and_stream(
        request,
        version_public_id=public_id,
        as_attachment=False,
        allow_historical=True,
    )
