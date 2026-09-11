"""HTTP surface for named company-signatory ceremony (Hub-native)."""

from __future__ import annotations

import json
import uuid
from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from inertia import inertia

from apps.contract.lifecycle import StaleContractVersion, TransitionRefused
from apps.contract.models import AgentContract
from apps.contract.services.signing_service import (
    RequestMeta,
    SigningCeremonyError,
    company_ceremony_page_payload,
    complete_company_signing,
    start_company_signing,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy

PAGE = "CompanyContractSign"


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _request_meta(request: HttpRequest) -> RequestMeta:
    session_key = ""
    if hasattr(request, "session"):
        if not request.session.session_key:
            request.session.save()
        session_key = request.session.session_key or ""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    ip = forwarded or (request.META.get("REMOTE_ADDR") or "")
    ua = request.META.get("HTTP_USER_AGENT") or ""
    return RequestMeta(session_key=session_key, ip_address=ip, user_agent=ua)


def _json_body(request: HttpRequest) -> dict[str, Any]:
    if request.content_type and "json" in request.content_type:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return body if isinstance(body, dict) else {}
    return {key: request.POST.get(key) for key in request.POST}


def _validation_payload(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict") and exc.message_dict:
        fields: dict[str, list[str]] = {}
        form: list[str] = []
        for key, messages in exc.message_dict.items():
            texts = [str(m) for m in messages]
            if key in {"__all__", "form"}:
                form.extend(texts)
            else:
                fields[key] = texts
        return {"fields": fields, "form": form}
    messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
    return {"fields": {}, "form": [str(m) for m in messages]}


def _load_for_signatory(request: HttpRequest, public_id: uuid.UUID) -> AgentContract:
    actor = _actor(request)
    contract = (
        AgentContract.objects.select_related("generated_pdf", "company_signatory")
        .filter(public_id=public_id)
        .first()
    )
    if contract is None:
        raise PermissionDenied("Contract is not available.")
    if actor.pk != contract.company_signatory_id and not getattr(
        actor, "is_superuser", False
    ):
        raise PermissionDenied("Only the named company signatory can access this.")
    return contract


@enforce_policy("agent_contract_company_sign")
@require_http_methods(["GET", "POST"])
@inertia(PAGE)
def agent_contract_company_sign(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    if request.method == "GET":
        return company_ceremony_page_payload(actor, contract_public_id=public_id)

    body = _json_body(request)
    consent_raw = body.get("consentAccepted", body.get("consent_accepted"))
    expected_version = str(
        body.get("expectedVersion") or body.get("expected_version") or ""
    )
    disclosure_version = str(
        body.get("disclosureVersion") or body.get("disclosure_version") or ""
    )
    consent_accepted = consent_raw in {True, "1", "true", "on", "yes"}
    try:
        return start_company_signing(
            actor,
            contract_public_id=public_id,
            expected_version=expected_version,
            consent_accepted=consent_accepted,
            disclosure_version=disclosure_version,
            request_meta=_request_meta(request),
        )
    except (SigningCeremonyError, ValidationError, StaleContractVersion) as exc:
        props = company_ceremony_page_payload(actor, contract_public_id=public_id)
        props["errors"] = _validation_payload(exc)
        return props
    except PermissionDenied as exc:
        props = company_ceremony_page_payload(actor, contract_public_id=public_id)
        props["errors"] = {"fields": {}, "form": [str(exc)]}
        return props


@enforce_policy("agent_contract_company_sign")
@require_POST
def agent_contract_company_sign_complete(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    _load_for_signatory(request, public_id)
    body = _json_body(request)
    intent_raw = body.get("intentPublicId") or body.get("intent_public_id") or ""
    try:
        intent_id = uuid.UUID(str(intent_raw))
    except ValueError:
        return JsonResponse(
            {"ok": False, "errors": {"form": ["Invalid signing intent."]}},
            status=400,
        )
    try:
        result = complete_company_signing(
            actor,
            intent_public_id=intent_id,
            signature_data_url=str(
                body.get("signatureDataUrl") or body.get("signature_data_url") or ""
            ),
            signed_date=str(body.get("signedDate") or body.get("signed_date") or ""),
            initials_data_url=str(
                body.get("initialsDataUrl") or body.get("initials_data_url") or ""
            ),
            text_values=body.get("textValues") or body.get("text_values") or {},
            request_meta=_request_meta(request),
        )
        return JsonResponse(result)
    except (
        SigningCeremonyError,
        ValidationError,
        TransitionRefused,
        StaleContractVersion,
        PermissionDenied,
    ) as exc:
        payload = (
            _validation_payload(exc)
            if isinstance(exc, ValidationError)
            else {
                "fields": {},
                "form": [str(exc)],
            }
        )
        return JsonResponse({"ok": False, "errors": payload}, status=400)


@enforce_policy("agent_contract_company_sign")
@require_GET
def agent_contract_company_sign_preview(
    request: HttpRequest, public_id: uuid.UUID
) -> HttpResponse:
    """Session-auth PDF stream of the review PDF for the company pad."""
    contract = _load_for_signatory(request, public_id)
    artifact = contract.generated_pdf
    if artifact is None or not artifact.file:
        return HttpResponse(status=404)
    artifact.file.open("rb")
    try:
        data = artifact.file.read()
    finally:
        artifact.file.close()
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="contract-review.pdf"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    # Same-origin iframe on the company pad; default middleware is DENY.
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response
