"""Inertia and download views for the operational reporting framework."""

from __future__ import annotations

from typing import cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia

from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.reporting.exports import create_export_job, download_export
from apps.web.reporting.service import (
    export_status_payload,
    report_catalog_payload,
    report_page_payload,
)

__all__ = [
    "report_catalog",
    "report_detail",
    "report_export_create",
    "report_export_status",
    "report_export_download",
]


@enforce_policy("report_catalog")
@require_GET
@inertia("Reports")
def report_catalog(request: HttpRequest):
    actor = cast(User, request.user)
    return report_catalog_payload(actor)


@enforce_policy("report_detail")
@require_GET
@inertia("ReportDetail")
def report_detail(request: HttpRequest, report_key: str):
    actor = cast(User, request.user)
    try:
        return report_page_payload(actor, report_key, params=request.GET)
    except LookupError as exc:
        raise Http404 from exc
    except PermissionError as exc:
        raise PermissionDenied("You do not have access to this report.") from exc


@enforce_policy("report_export_create")
@require_POST
def report_export_create(request: HttpRequest, report_key: str) -> JsonResponse:
    actor = cast(User, request.user)
    export_format = (request.POST.get("format") or "csv").strip().lower()
    # Filters travel as the same query keys used on the interactive page.
    filters = {
        key: value
        for key, value in request.POST.items()
        if key not in {"format", "csrfmiddlewaretoken"}
    }
    try:
        job = create_export_job(
            actor,
            report_key,
            filters=filters,
            export_format=export_format,
        )
    except Http404:
        raise
    except PermissionDenied:
        raise
    except ValidationError as exc:
        return JsonResponse({"errors": exc.message_dict}, status=400)
    return JsonResponse(export_status_payload(actor, job.pk))


@enforce_policy("report_export_status")
@require_GET
def report_export_status(request: HttpRequest, job_id: int) -> JsonResponse:
    actor = cast(User, request.user)
    try:
        return JsonResponse(export_status_payload(actor, job_id))
    except LookupError as exc:
        raise Http404 from exc


@enforce_policy("report_export_download")
@require_GET
def report_export_download(request: HttpRequest, job_id: int) -> FileResponse:
    actor = cast(User, request.user)
    return download_export(actor, job_id)
