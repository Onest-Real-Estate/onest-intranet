"""HTTP surface for recipient one-click contract signing (P1-042)."""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from inertia import inertia

from apps.contract.docuseal_client import authorize_docuseal_webhook
from apps.contract.lifecycle import StaleContractVersion, TransitionRefused
from apps.contract.services.signing_service import (
    RequestMeta,
    SigningCeremonyError,
    ceremony_page_payload,
    complete_signing_from_docuseal,
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
    """Ceremony page: disclosure + DocuSeal embed after consent POST."""
    actor = _actor(request)
    version_id = _version_param(request)

    if request.method == "GET":
        return ceremony_page_payload(actor, version_public_id=version_id)

    consent_raw = request.POST.get("consentAccepted") or request.POST.get(
        "consent_accepted"
    )
    if consent_raw is None and request.content_type and "json" in request.content_type:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        consent_raw = body.get("consentAccepted", body.get("consent_accepted"))
        expected_version = str(
            body.get("expectedVersion") or body.get("expected_version") or ""
        )
        disclosure_version = str(
            body.get("disclosureVersion") or body.get("disclosure_version") or ""
        )
        contract_raw = body.get("contractPublicId") or body.get("contract_public_id")
    else:
        expected_version = (
            request.POST.get("expectedVersion")
            or request.POST.get("expected_version")
            or ""
        )
        disclosure_version = (
            request.POST.get("disclosureVersion")
            or request.POST.get("disclosure_version")
            or ""
        )
        contract_raw = (
            request.POST.get("contractPublicId")
            or request.POST.get("contract_public_id")
            or ""
        )

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


@csrf_exempt
@enforce_policy("docuseal_contract_webhook")
@require_POST
def docuseal_contract_webhook(request: HttpRequest) -> HttpResponse:
    """DocuSeal form.completed / submission.completed → durable signature."""
    signature = request.headers.get("X-Docuseal-Signature") or request.META.get(
        "HTTP_X_DOCUSEAL_SIGNATURE", ""
    )
    raw = request.body or b""
    url_token = (
        request.GET.get("token")
        or request.GET.get("secret")
        or request.headers.get("X-Docuseal-Token")
        or ""
    )
    if not authorize_docuseal_webhook(
        raw_body=raw,
        signature_header=signature,
        url_token=url_token,
    ):
        return HttpResponse(status=403)

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)

    event_type = str(payload.get("event_type") or payload.get("event") or "")
    if event_type not in {"form.completed", "submission.completed"}:
        return JsonResponse({"ok": True, "ignored": True})

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    submission_id = data.get("submission_id")
    if submission_id is None and isinstance(data.get("submission"), dict):
        submission_id = data["submission"].get("id")
    if submission_id is None:
        submission_id = data.get("id")
    try:
        submission_id_int = int(submission_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": True, "ignored": True})

    try:
        result = complete_signing_from_docuseal(
            submission_id=submission_id_int,
            event_payload=payload if isinstance(payload, dict) else {},
        )
    except (TransitionRefused, PermissionDenied, ValidationError) as exc:
        # 409 so DocuSeal retries transient races; permanent mismatches still
        # return 200 after logging when intent unknown (handled inside).
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)

    return JsonResponse(result)
