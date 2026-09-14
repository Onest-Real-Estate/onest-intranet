"""Documents & forms consumer surfaces and protected downloads."""

from __future__ import annotations

from typing import cast

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.documents.media_service import assert_readable_document, stream_file
from apps.documents.models import DocumentFile
from apps.documents.services import (
    build_library,
    category_filter_options,
    detail_payload,
    office_filter_options,
    resolve_consumer_document,
    role_filter_options,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


@enforce_policy("documents_forms")
@require_GET
@inertia("DocumentsForms")
def documents_forms(request: HttpRequest):
    actor = _actor(request)
    library = build_library(actor, params=request.GET, page=_page_param(request))
    selected_category = library["filters"]["category"]
    return {
        "library": library,
        "filterOptions": {
            "categories": category_filter_options(include_codes=(selected_category,)),
            "offices": office_filter_options(actor),
            "roles": role_filter_options(),
        },
    }


@enforce_policy("document_detail")
@require_GET
@inertia("DocumentDetail")
def document_detail(request: HttpRequest, document_id: int):
    actor = _actor(request)
    outcome, version = resolve_consumer_document(actor, document_id)
    if outcome == "redirect":
        target = reverse("document_detail", args=[version.pk])
        return redirect(f"{target}?superseded=1")
    return {
        "document": detail_payload(
            version, superseded=request.GET.get("superseded") == "1"
        ),
    }


@enforce_policy("document_file")
@require_GET
def document_file(request: HttpRequest, file_id: int) -> HttpResponse:
    actor = _actor(request)
    row = get_object_or_404(
        DocumentFile.objects.select_related(
            "document_version",
            "document_version__family",
            "document_version__family__owner_office",
        ),
        pk=file_id,
    )
    assert_readable_document(actor, row)
    log_event(
        "document.downloaded",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=DocumentFile._meta.label_lower,
            target_id=str(row.pk),
            target_label=row.display_name,
        ),
        metadata={"document_version_id": row.document_version.pk},
    )
    return stream_file(request, row, as_attachment=True)
