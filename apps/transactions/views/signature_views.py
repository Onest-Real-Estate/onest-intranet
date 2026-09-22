"""HTTP surface for transaction signature packages.

Three audiences, three doors, one service layer:

* **Authoring** — a manager builds, sends, cancels, and nudges from the deal
  workspace. Scope, manage rights, and the ``expectedVersion`` guard are
  enforced by :mod:`apps.transactions.signing.authoring`, not here.
* **Hub ceremony** — an authenticated signer is matched to their own signer row
  by user FK. The route carries a package id, never a signer id, so there is
  nothing in it to tamper with.
* **Magic-link ceremony** — an external signer arrives with a one-time token
  that resolves to exactly one signer. The token is the whole gate; no login is
  required and none is offered.

Both ceremony doors render the same Inertia page with the same props, and both
bind the signing intent to the browser session, so a link opened in one browser
cannot be completed from another.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from inertia import render

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.transactions.concurrency import (
    StaleTransactionVersion,
    can_manage_workspace,
    load_workspace_transaction,
)
from apps.transactions.models import (
    SignatureAccessToken,
    SignatureArtifact,
    SignaturePackage,
    SignaturePackageDocument,
    SignaturePackageSigner,
    Transaction,
)
from apps.transactions.services import scoped_transaction_queryset
from apps.transactions.signing import (
    RequestMeta,
    cancel_package,
    ceremony_payload,
    complete_signing,
    create_draft_package,
    decline_signing,
    load_package_for_reader,
    remind_signer,
    replace_package_contents,
    resolve_signer_from_hub_user,
    resolve_signer_from_token,
    start_intent,
    validate_and_send,
)
from apps.transactions.taxonomy import SignaturePackageStatus, WorkspaceSection
from apps.transactions.workspace import workspace_payload
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.flash import set_flash

CEREMONY_PAGE = "TransactionSignatureCeremony"
WORKSPACE_PAGE = "TransactionWorkspace"
SECTION = WorkspaceSection.SIGNATURES

#: Query parameter carrying a magic-link token on the ceremony preview route.
PREVIEW_TOKEN_PARAM = "t"

#: A resolved ceremony door: the package, the one signer, and the link that
#: proved it — ``None`` when an authenticated Hub session did.
CeremonyContext = tuple[
    SignaturePackage, SignaturePackageSigner, SignatureAccessToken | None
]


# --------------------------------------------------------------------------- #
# Request plumbing (mirrors document_views and contract signing_views)
# --------------------------------------------------------------------------- #


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _wants_json(request: HttpRequest) -> bool:
    accept = request.headers.get("Accept", "")
    return (
        "application/json" in accept
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


def _json_body(request: HttpRequest) -> dict[str, Any]:
    if request.content_type and "json" in request.content_type:
        try:
            raw = json.loads(request.body.decode() or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}
    return {key: request.POST.get(key) for key in request.POST}


def _expected_version(body: dict[str, Any]) -> str:
    return str(body.get("expectedVersion") or body.get("expected_version") or "")


def _camel_or_snake(body: dict[str, Any], camel: str, snake: str) -> Any:
    if camel in body:
        return body.get(camel)
    return body.get(snake)


def _flag(body: dict[str, Any], camel: str, snake: str) -> bool:
    raw = _camel_or_snake(body, camel, snake)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _request_meta(request: HttpRequest) -> RequestMeta:
    """Bind the ceremony to this browser session, creating one if needed.

    An external signer arrives with no session at all. Saving one here gives
    the intent something to bind to and lets ``CsrfViewMiddleware`` issue a
    cookie for the POSTs that follow. ``modified`` is set explicitly because
    ``SessionMiddleware`` only writes the cookie for a session it saw change.
    """
    session_key = ""
    if hasattr(request, "session"):
        if not request.session.session_key:
            request.session.save()
            request.session.modified = True
        session_key = request.session.session_key or ""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return RequestMeta(
        session_key=session_key,
        ip_address=forwarded or (request.META.get("REMOTE_ADDR") or ""),
        user_agent=request.META.get("HTTP_USER_AGENT") or "",
    )


def _validation_errors(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict") and exc.message_dict:
        fields: dict[str, list[str]] = {}
        form: list[str] = []
        for key, messages in exc.message_dict.items():
            texts = [str(message) for message in messages]
            if key in {"__all__", "form"}:
                form.extend(texts)
            else:
                fields[key] = texts
        return {"fields": fields, "form": form}
    messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
    return {"fields": {}, "form": [str(message) for message in messages]}


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, StaleTransactionVersion):
        return {"fields": {}, "form": [str(exc.messages[0] if exc.messages else exc)]}
    if isinstance(exc, ValidationError):
        return _validation_errors(exc)
    return {"fields": {}, "form": [str(exc)]}


def _error_status(exc: Exception) -> int:
    if isinstance(exc, StaleTransactionVersion):
        return 409
    if isinstance(exc, PermissionDenied):
        return 403
    return 422


def _json_error(exc: Exception) -> JsonResponse:
    """Authoring JSON contract: the transactions ``validation`` envelope."""
    return JsonResponse({"validation": _error_payload(exc)}, status=_error_status(exc))


def _ceremony_json_error(exc: Exception) -> JsonResponse:
    """Ceremony JSON contract: ``ok`` plus the same ``validation`` envelope.

    The ceremony is one page driven by ``fetch`` rather than Inertia visits, so
    it needs an explicit success flag; the error body stays the repository's
    ``fields`` / ``form`` pair so one renderer covers every transaction surface.
    """
    return JsonResponse(
        {"ok": False, "validation": _error_payload(exc)},
        status=_error_status(exc),
    )


# --------------------------------------------------------------------------- #
# Authoring
# --------------------------------------------------------------------------- #


def _workspace_redirect(public_id: UUID | str) -> HttpResponse:
    url = reverse("transaction_workspace", kwargs={"public_id": public_id})
    return redirect(f"{url}?section={SECTION}")


def _workspace_error(
    request: HttpRequest, public_id: uuid.UUID, exc: Exception
) -> HttpResponse:
    """Re-render the Signatures section carrying the service's own error shape."""
    actor = _actor(request)
    try:
        tx = load_workspace_transaction(actor, public_id)
    except Transaction.DoesNotExist as missing:
        raise Http404(_("Transaction not found.")) from missing
    props = {
        **workspace_payload(actor, tx, section=SECTION),
        "errors": _error_payload(exc),
    }
    response = render(request, WORKSPACE_PAGE, props)
    response.status_code = _error_status(exc)
    return response


def _authoring_failure(
    request: HttpRequest, public_id: uuid.UUID, exc: Exception
) -> HttpResponse:
    if _wants_json(request):
        return _json_error(exc)
    return _workspace_error(request, public_id, exc)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_signature_package_create(request: HttpRequest, public_id: uuid.UUID):
    """Open an empty draft package on a deal the caller can manage."""
    body = _json_body(request)
    try:
        package = create_draft_package(
            _actor(request),
            public_id,
            title=str(body.get("title") or ""),
            routing_mode=_camel_or_snake(body, "routingMode", "routing_mode") or "",
            expires_at=_camel_or_snake(body, "expiresAt", "expires_at"),
            expected_version=_expected_version(body),
        )
    except Transaction.DoesNotExist as exc:
        raise Http404(_("Transaction not found.")) from exc
    except (ValidationError, PermissionDenied) as exc:
        return _authoring_failure(request, public_id, exc)
    if _wants_json(request):
        return JsonResponse(
            {"package": {"publicId": str(package.public_id), "title": package.title}},
            status=201,
        )
    set_flash(request, level="success", message="Signature package drafted.")
    return _workspace_redirect(public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_signature_package_save(
    request: HttpRequest, public_id: uuid.UUID, package_id: uuid.UUID
):
    """Replace a draft package's settings, documents, signers, and fields."""
    body = _json_body(request)
    documents = body.get("documents")
    signers = body.get("signers")
    fields = body.get("fields")
    try:
        replace_package_contents(
            _actor(request),
            package_id,
            documents=documents if isinstance(documents, list) else [],
            signers=signers if isinstance(signers, list) else [],
            fields=fields if isinstance(fields, list) else [],
            title=body.get("title"),
            routing_mode=_camel_or_snake(body, "routingMode", "routing_mode"),
            expires_at=_camel_or_snake(body, "expiresAt", "expires_at"),
            expected_version=_expected_version(body),
        )
    except (SignaturePackage.DoesNotExist, Transaction.DoesNotExist) as exc:
        raise Http404(_("Signature package not found.")) from exc
    except (ValidationError, PermissionDenied) as exc:
        return _authoring_failure(request, public_id, exc)
    if _wants_json(request):
        return JsonResponse({"ok": True})
    set_flash(request, level="success", message="Signature package saved.")
    return _workspace_redirect(public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_signature_package_send(
    request: HttpRequest, public_id: uuid.UUID, package_id: uuid.UUID
):
    """Validate a draft, freeze the disclosure, and invite the first signers."""
    body = _json_body(request)
    try:
        package = validate_and_send(
            _actor(request), package_id, expected_version=_expected_version(body)
        )
    except (SignaturePackage.DoesNotExist, Transaction.DoesNotExist) as exc:
        raise Http404(_("Signature package not found.")) from exc
    except (ValidationError, PermissionDenied) as exc:
        return _authoring_failure(request, public_id, exc)
    if _wants_json(request):
        return JsonResponse({"ok": True, "status": package.status})
    set_flash(request, level="success", message="Signature package sent.")
    return _workspace_redirect(public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_signature_package_cancel(
    request: HttpRequest, public_id: uuid.UUID, package_id: uuid.UUID
):
    """Withdraw a package that has not completed; links stop working at once."""
    body = _json_body(request)
    try:
        package = cancel_package(
            _actor(request), package_id, expected_version=_expected_version(body)
        )
    except (SignaturePackage.DoesNotExist, Transaction.DoesNotExist) as exc:
        raise Http404(_("Signature package not found.")) from exc
    except (ValidationError, PermissionDenied) as exc:
        return _authoring_failure(request, public_id, exc)
    if _wants_json(request):
        return JsonResponse({"ok": True, "status": package.status})
    set_flash(request, level="success", message="Signature package cancelled.")
    return _workspace_redirect(public_id)


@enforce_policy("transaction_workspace_write")
@require_POST
def transaction_signature_signer_remind(
    request: HttpRequest,
    public_id: uuid.UUID,
    package_id: uuid.UUID,
    signer_id: uuid.UUID,
):
    """Nudge one signer who is still holding up an open package.

    ``remind_signer`` is a scheduling primitive with no authorization of its
    own, so scope and manage rights are established here before calling it.
    """
    actor = _actor(request)
    try:
        package = load_package_for_reader(actor, package_id)
    except SignaturePackage.DoesNotExist as exc:
        raise Http404(_("Signature package not found.")) from exc
    if not can_manage_workspace(actor, package.transaction):
        raise PermissionDenied(_("You cannot edit this transaction."))

    signer = (
        SignaturePackageSigner.objects.select_related("package", "package__transaction")
        .filter(public_id=signer_id, package_id=package.pk)
        .first()
    )
    if signer is None:
        raise Http404(_("Signer not found."))

    reminded = remind_signer(signer)
    if _wants_json(request):
        return JsonResponse({"ok": True, "reminded": reminded})
    if reminded:
        set_flash(request, level="success", message="Reminder sent.")
    else:
        set_flash(
            request,
            level="warning",
            message="That signer is not waiting on a signature right now.",
        )
    return _workspace_redirect(public_id)


# --------------------------------------------------------------------------- #
# Ceremony — one body, two doors
# --------------------------------------------------------------------------- #


def _hub_context(request: HttpRequest, public_id: uuid.UUID) -> CeremonyContext:
    package = (
        SignaturePackage.objects.select_related("transaction")
        .filter(public_id=public_id)
        .first()
    )
    if package is None:
        raise Http404(_("No signature package matches that id."))
    signer = resolve_signer_from_hub_user(_actor(request), package)
    return package, signer, None


def _token_context(token: str) -> CeremonyContext:
    package, signer, access_token = resolve_signer_from_token(token)
    return package, signer, access_token


def _hub_endpoints(package: SignaturePackage) -> dict[str, str]:
    kwargs = {"public_id": package.public_id}
    return {
        "mode": "hub",
        "startUrl": reverse("transaction_signature_ceremony", kwargs=kwargs),
        "completeUrl": reverse(
            "transaction_signature_ceremony_complete", kwargs=kwargs
        ),
        "declineUrl": reverse("transaction_signature_ceremony_decline", kwargs=kwargs),
        "previewTokenParam": "",
        "previewToken": "",
    }


def _magic_link_endpoints(token: str) -> dict[str, str]:
    kwargs = {"token": token}
    return {
        "mode": "magicLink",
        "startUrl": reverse("transaction_signature_magic_link", kwargs=kwargs),
        "completeUrl": reverse(
            "transaction_signature_magic_link_complete", kwargs=kwargs
        ),
        "declineUrl": reverse(
            "transaction_signature_magic_link_decline", kwargs=kwargs
        ),
        # A document preview is the one GET an external signer makes that has
        # to prove who they are; the page appends the link they arrived on.
        "previewTokenParam": PREVIEW_TOKEN_PARAM,
        "previewToken": token,
    }


def _ceremony_props(
    context: CeremonyContext,
    *,
    endpoints: dict[str, str],
    intent=None,
    errors: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package, signer, _token = context
    payload = ceremony_payload(package, signer, intent=intent)
    payload["endpoints"] = endpoints
    if errors is not None:
        payload["errors"] = errors
    return payload


def _ceremony_page(
    request: HttpRequest, context: CeremonyContext, *, endpoints: dict[str, str]
) -> dict[str, Any]:
    """GET shows the disclosure; POST records consent and opens an intent."""
    package, signer, token = context
    if request.method == "GET":
        return _ceremony_props(context, endpoints=endpoints)

    body = _json_body(request)
    try:
        payload = start_intent(
            package=package,
            signer=signer,
            consent_accepted=_flag(body, "consentAccepted", "consent_accepted"),
            disclosure_version=str(
                _camel_or_snake(body, "disclosureVersion", "disclosure_version") or ""
            ),
            request_meta=_request_meta(request),
            actor=signer.user if signer.user_id else None,
            access_token=token,
        )
    except ValidationError as exc:
        return _ceremony_props(context, endpoints=endpoints, errors=_error_payload(exc))
    payload["endpoints"] = endpoints
    return payload


def _complete(request: HttpRequest, context: CeremonyContext) -> JsonResponse:
    _package, signer, token = context
    body = _json_body(request)
    raw_intent = _camel_or_snake(body, "intentPublicId", "intent_public_id") or ""
    try:
        intent_id = uuid.UUID(str(raw_intent))
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "ok": False,
                "validation": {
                    "fields": {},
                    "form": [str(_("Start the signing step again."))],
                },
            },
            status=422,
        )

    raw_values = _camel_or_snake(body, "textValues", "text_values") or {}
    text_values = (
        {str(key): str(value) for key, value in raw_values.items()}
        if isinstance(raw_values, dict)
        else {}
    )
    try:
        result = complete_signing(
            intent_public_id=intent_id,
            signer=signer,
            signature_data_url=str(
                _camel_or_snake(body, "signatureDataUrl", "signature_data_url") or ""
            ),
            signed_date=str(_camel_or_snake(body, "signedDate", "signed_date") or ""),
            initials_data_url=str(
                _camel_or_snake(body, "initialsDataUrl", "initials_data_url") or ""
            ),
            text_values=text_values,
            request_meta=_request_meta(request),
            access_token=token,
        )
    except (ValidationError, PermissionDenied) as exc:
        return _ceremony_json_error(exc)
    return JsonResponse(result)


def _decline(request: HttpRequest, context: CeremonyContext) -> JsonResponse:
    package, signer, token = context
    body = _json_body(request)
    try:
        result = decline_signing(
            package=package,
            signer=signer,
            reason=str(body.get("reason") or ""),
            request_meta=_request_meta(request),
            access_token=token,
        )
    except (ValidationError, PermissionDenied) as exc:
        return _ceremony_json_error(exc)
    return JsonResponse(result)


# --------------------------------------------------------------------------- #
# Ceremony — Hub signer
# --------------------------------------------------------------------------- #


@enforce_policy("transaction_signature_ceremony")
@require_http_methods(["GET", "POST"])
def transaction_signature_ceremony(request: HttpRequest, public_id: uuid.UUID):
    """Ceremony for an authenticated signer, on their own signer row only."""
    context = _hub_context(request, public_id)
    props = _ceremony_page(request, context, endpoints=_hub_endpoints(context[0]))
    return render(request, CEREMONY_PAGE, props)


@enforce_policy("transaction_signature_ceremony")
@require_POST
def transaction_signature_ceremony_complete(request: HttpRequest, public_id: uuid.UUID):
    return _complete(request, _hub_context(request, public_id))


@enforce_policy("transaction_signature_ceremony")
@require_POST
def transaction_signature_ceremony_decline(request: HttpRequest, public_id: uuid.UUID):
    return _decline(request, _hub_context(request, public_id))


# --------------------------------------------------------------------------- #
# Ceremony — magic link (public; the token is the gate)
# --------------------------------------------------------------------------- #


@enforce_policy("transaction_signature_magic_link")
@require_http_methods(["GET", "POST"])
def transaction_signature_magic_link(request: HttpRequest, token: str):
    """Public ceremony for an external signer holding a one-time link."""
    context = _token_context(token)
    props = _ceremony_page(request, context, endpoints=_magic_link_endpoints(token))
    return render(request, CEREMONY_PAGE, props)


@enforce_policy("transaction_signature_magic_link")
@require_POST
def transaction_signature_magic_link_complete(request: HttpRequest, token: str):
    return _complete(request, _token_context(token))


@enforce_policy("transaction_signature_magic_link")
@require_POST
def transaction_signature_magic_link_decline(request: HttpRequest, token: str):
    return _decline(request, _token_context(token))


# --------------------------------------------------------------------------- #
# File delivery
# --------------------------------------------------------------------------- #


def _log_file_denial(request: HttpRequest, target_id: str, *, reason: str) -> None:
    user = request.user
    log_event(
        "security.transaction.document_denied",
        actor=actor_from_user(user if user.is_authenticated else None),
        target=AuditTarget(
            target_type="transaction.signature_package",
            target_id=target_id,
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def _stream(field, *, filename: str, media_type: str, as_attachment: bool):
    storage = field.storage
    key = field.name
    if not key or not storage.exists(key):
        raise Http404(_("That file is no longer stored."))
    response: FileResponse = FileResponse(
        storage.open(key, "rb"),
        as_attachment=as_attachment,
        filename=filename,
        content_type=media_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    if not as_attachment:
        response["X-Frame-Options"] = "SAMEORIGIN"
    return response


def _may_preview(request: HttpRequest, package: SignaturePackage) -> bool:
    """A live link for this package, a signer row on it, or workspace scope.

    The caller turns ``False`` into a 404, so probing cannot tell "not yours"
    apart from "does not exist".
    """
    raw_token = (request.GET.get(PREVIEW_TOKEN_PARAM) or "").strip()
    if raw_token:
        try:
            token_package, _signer, _token = resolve_signer_from_token(raw_token)
        except PermissionDenied:
            return False
        return token_package.pk == package.pk

    if not request.user.is_authenticated:
        return False
    actor = _actor(request)
    try:
        resolve_signer_from_hub_user(actor, package)
        return True
    except PermissionDenied:
        pass
    try:
        load_package_for_reader(actor, package.public_id)
    except SignaturePackage.DoesNotExist:
        return False
    return True


@enforce_policy("transaction_signature_document_preview")
@require_GET
def transaction_signature_document_preview(
    request: HttpRequest, public_id: uuid.UUID, document_id: uuid.UUID
):
    """Inline source PDF for the ceremony and the authoring field placer.

    The route is public because an external signer has no account. Every
    caller still proves itself: the magic-link token in ``?t=``, or a Hub
    session that is a signer on the package or a scoped workspace reader.
    """
    document = (
        SignaturePackageDocument.objects.select_related(
            "package", "package__transaction", "version", "version__document"
        )
        .filter(public_id=document_id, package__public_id=public_id)
        .first()
    )
    if document is None:
        raise Http404(_("No document matches that id."))
    if not _may_preview(request, document.package):
        _log_file_denial(request, str(public_id), reason="preview_not_permitted")
        raise Http404(_("No document matches that id."))
    version = document.version
    return _stream(
        version.file,
        filename=version.display_name or version.original_name,
        media_type=version.media_type,
        as_attachment=False,
    )


@enforce_policy("transaction_signature_artifact_download")
@require_GET
def transaction_signature_artifact_download(request: HttpRequest, public_id: uuid.UUID):
    """Sealed signed PDF or certificate of completion for a completed package.

    Artifacts stay inside the Hub: an external signer is told by the completion
    email to ask the brokerage, rather than handed a durable public link to the
    executed agreement.
    """
    actor = _actor(request)
    artifact = (
        SignatureArtifact.objects.select_related("package", "package__transaction")
        .filter(
            public_id=public_id,
            package__status=SignaturePackageStatus.COMPLETED,
            package__transaction__in=scoped_transaction_queryset(actor),
        )
        .first()
    )
    if artifact is None:
        _log_file_denial(request, str(public_id), reason="out_of_scope")
        raise Http404(_("No artifact matches that id."))
    return _stream(
        artifact.file,
        filename=artifact.display_name,
        media_type=artifact.media_type,
        as_attachment=True,
    )


__all__ = [
    "transaction_signature_artifact_download",
    "transaction_signature_ceremony",
    "transaction_signature_ceremony_complete",
    "transaction_signature_ceremony_decline",
    "transaction_signature_document_preview",
    "transaction_signature_magic_link",
    "transaction_signature_magic_link_complete",
    "transaction_signature_magic_link_decline",
    "transaction_signature_package_cancel",
    "transaction_signature_package_create",
    "transaction_signature_package_save",
    "transaction_signature_package_send",
    "transaction_signature_signer_remind",
]
