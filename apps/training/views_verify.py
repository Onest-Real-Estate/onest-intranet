"""Public training certificate verification."""

from __future__ import annotations

from uuid import UUID

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from inertia import render

from apps.training.certificate_crypto import verification_result
from apps.web.authorization import enforce_policy

VERIFY_PAGE = "TrainingCertificateVerify"


def _wants_json(request: HttpRequest) -> bool:
    if request.GET.get("format") == "json":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept and "text/html" not in accept


@enforce_policy("training_certificate_verify")
@require_GET
def training_certificate_verify(request: HttpRequest, public_id: UUID) -> HttpResponse:
    result = verification_result(public_id)
    if _wants_json(request):
        status = 404 if result.get("status") == "not_found" else 200
        return JsonResponse(result, status=status)
    return render(request, VERIFY_PAGE, {"verification": result})
