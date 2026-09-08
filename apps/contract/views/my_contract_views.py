"""HTTP surface for the agent self-service My Contract page (P1-041)."""

from __future__ import annotations

import uuid
from typing import cast
from uuid import UUID

from django.http import FileResponse, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.contract.artifact_delivery import stream_contract_artifact
from apps.contract.my_contract import (
    my_contract_page_payload,
    recipient_visible_queryset,
)
from apps.contract.signed_pdf_generation import integrity_payload
from apps.user.models import User
from apps.web.authorization import enforce_policy

PAGE = "MyContract"


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _version_param(request: HttpRequest) -> UUID | None:
    raw = (request.GET.get("v") or "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


@enforce_policy("my_contract")
@require_GET
@inertia(PAGE)
def my_contract(request: HttpRequest):
    """Self-service agreement status, summary, PDF, and family history.

    Recipient is derived solely from the authenticated user. Optional ``v``
    selects a visible version in the recipient's own family.
    """
    return my_contract_page_payload(
        _actor(request),
        version_public_id=_version_param(request),
        record_viewed=True,
    )


@enforce_policy("my_contract_artifact_preview")
@require_GET
def my_contract_artifact_preview(
    request: HttpRequest,
    public_id: uuid.UUID,
    artifact_public_id: uuid.UUID,
) -> FileResponse:
    """Inline PDF stream for embedded/new-tab preview (self-only scope)."""
    return stream_contract_artifact(
        _actor(request),
        contract_public_id=public_id,
        artifact_public_id=artifact_public_id,
        as_attachment=False,
        queryset=recipient_visible_queryset(_actor(request)),
    )


@enforce_policy("my_contract_signed_pdf_verify")
@require_GET
def my_contract_signed_pdf_verify(
    request: HttpRequest,
    public_id: uuid.UUID,
) -> JsonResponse:
    """Recipient integrity metadata for their own final signed PDF."""
    contract = get_object_or_404(
        recipient_visible_queryset(_actor(request)), public_id=public_id
    )
    payload = integrity_payload(contract)
    if payload is None:
        return JsonResponse({"error": "no_signature"}, status=404)
    return JsonResponse(payload)
