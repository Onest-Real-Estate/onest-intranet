"""HTTP surface for recipient one-click contract signing (Hub-native)."""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from inertia import inertia

from apps.contract.lifecycle import StaleContractVersion, TransitionRefused
from apps.contract.services.signing_service import (
    RequestMeta,
    SigningCeremonyError,
    ceremony_page_payload,
    complete_signing,
    signing_status_payload,
    start_signing,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy

PAGE = "MyContractSign"


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _version_param(request: HttpRequest) -> UUID | None:
    raw = (request.GET.get("v") or request.POST.get("v") or "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


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


@enforce_policy("my_contract_sign")
@require_http_methods(["GET", "POST"])
@inertia(PAGE)
def my_contract_sign(request: HttpRequest):
    """Ceremony page: disclosure + Hub signature pad after consent POST."""
    actor = _actor(request)
    version_id = _version_param(request)

    if request.method == "GET":
        return ceremony_page_payload(actor, version_public_id=version_id)

    body = _json_body(request)
    consent_raw = body.get("consentAccepted", body.get("consent_accepted"))
    expected_version = str(
        body.get("expectedVersion") or body.get("expected_version") or ""
    )
    disclosure_version = str(
        body.get("disclosureVersion") or body.get("disclosure_version") or ""
    )
    contract_raw = body.get("contractPublicId") or body.get("contract_public_id") or ""

    consent_accepted = str(consent_raw).lower() in {"1", "true", "yes", "on"}
    try:
        contract_public_id = uuid.UUID(str(contract_raw))
    except (ValueError, TypeError):
        payload = ceremony_page_payload(actor, version_public_id=version_id)
        payload["errors"] = {
            "fields": {"contractPublicId": ["Choose a valid contract version."]},
            "form": [],
        }
        return payload

    try:
        return start_signing(
            actor,
            contract_public_id=contract_public_id,
            expected_version=str(expected_version),
            consent_accepted=consent_accepted,
            disclosure_version=str(disclosure_version),
            request_meta=_request_meta(request),
        )
    except PermissionDenied:
        raise
    except StaleContractVersion as exc:
        payload = ceremony_page_payload(actor, version_public_id=contract_public_id)
        payload["errors"] = {"fields": {}, "form": [exc.message]}
        return payload
    except (SigningCeremonyError, ValidationError) as exc:
        payload = ceremony_page_payload(actor, version_public_id=contract_public_id)
        payload["errors"] = _validation_payload(exc)
        return payload


@enforce_policy("my_contract_sign_complete")
@require_POST
def my_contract_sign_complete(request: HttpRequest) -> JsonResponse:
    """Stamp signature appearance and commit the durable signature record."""
    actor = _actor(request)
    body = _json_body(request)
    intent_raw = body.get("intentPublicId") or body.get("intent_public_id") or ""
    try:
        intent_id = uuid.UUID(str(intent_raw))
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "invalid_intent"}, status=400)

    signature_data_url = str(
        body.get("signatureDataUrl") or body.get("signature_data_url") or ""
    )
    signed_date = str(body.get("signedDate") or body.get("signed_date") or "")
    initials_data_url = str(
        body.get("initialsDataUrl") or body.get("initials_data_url") or ""
    )
    raw_text = body.get("textValues") or body.get("text_values") or {}
    text_values = (
        {str(k): str(v) for k, v in raw_text.items()}
        if isinstance(raw_text, dict)
        else {}
    )

    try:
        result = complete_signing(
            actor,
            intent_public_id=intent_id,
            signature_data_url=signature_data_url,
            signed_date=signed_date,
            initials_data_url=initials_data_url,
            text_values=text_values,
            request_meta=_request_meta(request),
        )
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=403)
    except (SigningCeremonyError, ValidationError) as exc:
        return JsonResponse(
            {"ok": False, "errors": _validation_payload(exc)}, status=400
        )
    except TransitionRefused as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    return JsonResponse(result)


@enforce_policy("my_contract_sign_status")
@require_GET
def my_contract_sign_status(request: HttpRequest) -> JsonResponse:
    """JSON poll: durable signature committed?"""
    actor = _actor(request)
    contract_id = None
    intent_id = None
    raw_c = (request.GET.get("contract") or "").strip()
    raw_i = (request.GET.get("intent") or "").strip()
    if raw_c:
        try:
            contract_id = uuid.UUID(raw_c)
        except ValueError:
            return JsonResponse({"error": "invalid_contract"}, status=400)
    if raw_i:
        try:
            intent_id = uuid.UUID(raw_i)
        except ValueError:
            return JsonResponse({"error": "invalid_intent"}, status=400)
    return JsonResponse(
        signing_status_payload(
            actor,
            contract_public_id=contract_id,
            intent_public_id=intent_id,
        )
    )
