"""Policy library consumer surfaces and protected document downloads."""

from __future__ import annotations

from typing import cast

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.compliance.acknowledgements import acknowledge
from apps.compliance.media_service import assert_readable_document, stream_file
from apps.compliance.models import PolicyFile
from apps.compliance.services import (
    build_library,
    category_filter_options,
    detail_payload,
    resolve_consumer_policy,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


@enforce_policy("policies_compliance")
@require_GET
@inertia("PoliciesCompliance")
def policies_compliance(request: HttpRequest):
    actor = _actor(request)
    library = build_library(actor, params=request.GET, page=_page_param(request))
    selected_category = library["filters"]["category"]
    return {
        "library": library,
        "filterOptions": {
            "categories": category_filter_options(include_codes=(selected_category,)),
        },
        "errors": empty_validation_errors(),
    }


@enforce_policy("policy_detail")
@require_GET
@inertia("PolicyDetail")
def policy_detail(request: HttpRequest, policy_id: int):
    actor = _actor(request)
    outcome, version = resolve_consumer_policy(actor, policy_id)
    if outcome == "redirect":
        return redirect("policy_detail", policy_id=version.pk)
    return {
        "policy": detail_payload(version, actor=actor),
        "errors": empty_validation_errors(),
    }


@enforce_policy("policy_acknowledge")
@require_POST
def policy_acknowledge(request: HttpRequest, policy_id: int):
    actor = _actor(request)
    try:
        acknowledge(
            actor,
            policy_id,
            expected_checksum=(request.POST.get("expectedChecksum") or "").strip(),
            disclosure_version=int(request.POST.get("disclosureVersion") or "0"),
            request=request,
        )
    except ValidationError as exc:
        outcome, version = resolve_consumer_policy(actor, policy_id)
        if outcome == "redirect":
            return redirect("policy_detail", policy_id=version.pk)
        payload = {
            "fields": {},
            "form": [str(m) for m in getattr(exc, "messages", [exc])],
        }
        if hasattr(exc, "message_dict"):
            payload = {
                "fields": {
                    field: [str(message) for message in messages]
                    for field, messages in exc.message_dict.items()
                    if field != "__all__"
                },
                "form": [
                    str(message) for message in exc.message_dict.get("__all__", [])
                ],
            }
        response = render(
            request,
            "PolicyDetail",
            {
                "policy": detail_payload(version, actor=actor),
                "errors": payload,
            },
        )
        response.status_code = 422
        return response
    except ValueError:
        return redirect("policy_detail", policy_id=policy_id)
    return redirect("policy_detail", policy_id=policy_id)


@enforce_policy("policy_document_file")
@require_GET
def policy_document_file(request: HttpRequest, file_id: int) -> HttpResponse:
    actor = _actor(request)
    row = get_object_or_404(
        PolicyFile.objects.select_related(
            "policy_version", "policy_version__owner_office"
        ),
        pk=file_id,
    )
    assert_readable_document(actor, row)
    return stream_file(request, row, as_attachment=True)
