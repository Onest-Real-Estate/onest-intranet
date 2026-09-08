"""Training library surfaces and learner progress mutations."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.training.audience import assert_visible
from apps.training.certificate_service import stream_certificate
from apps.training.media_service import assert_readable, stream_media
from apps.training.models import TrainingContent, TrainingMedia
from apps.training.progress_service import learner_update_progress
from apps.training.quiz_service import submit_attempt
from apps.training.services import (
    build_library,
    category_filter_options,
    completion_filter_options,
    content_type_filter_options,
    detail_payload,
    tool_filter_options,
)
from apps.training.session_service import cancel_registration, register
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors

DETAIL_PAGE = "TrainingDetail"


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _load_visible(request: HttpRequest, content_id: int) -> TrainingContent:
    actor = _actor(request)
    content = get_object_or_404(
        TrainingContent.objects.select_related(
            "category", "owner_office", "embed", "transcription"
        ),
        pk=content_id,
    )
    assert_visible(actor, content, reason="detail_out_of_audience")
    return content


def _errors(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        return {"fields": dict(exc.message_dict), "form": []}
    return {"fields": {}, "form": list(exc.messages)}


def _detail_422(
    request: HttpRequest, content: TrainingContent, exc: ValidationError
) -> HttpResponse:
    actor = _actor(request)
    response = render(
        request,
        DETAIL_PAGE,
        {
            "content": detail_payload(content, user=actor),
            "errors": _errors(exc),
        },
    )
    response.status_code = 422
    return response


def _detail_redirect(content: TrainingContent) -> HttpResponse:
    return redirect("training_detail", content_id=content.pk)


@enforce_policy("training_library")
@require_GET
@inertia("TrainingLearning")
def training_learning(request: HttpRequest):
    actor = _actor(request)
    library = build_library(actor, params=request.GET, page=_page_param(request))
    selected_category = library["filters"]["category"]
    return {
        "library": library,
        "requiredSummary": library.get("requiredSummary"),
        "filterOptions": {
            "categories": category_filter_options(include_codes=(selected_category,)),
            "contentTypes": content_type_filter_options(),
            "tools": tool_filter_options(),
            "completions": completion_filter_options(),
        },
    }


@enforce_policy("training_detail")
@require_GET
@inertia("TrainingDetail")
def training_detail(request: HttpRequest, content_id: int):
    actor = _actor(request)
    content = _load_visible(request, content_id)
    return {
        "content": detail_payload(content, user=actor),
        "errors": empty_validation_errors(),
    }


@enforce_policy("training_media")
@require_GET
def training_media(request: HttpRequest, media_id: int):
    actor = _actor(request)
    media = get_object_or_404(
        TrainingMedia.objects.select_related("content"),
        pk=media_id,
    )
    assert_readable(actor, media)
    return stream_media(request, media)


@enforce_policy("training_progress")
@require_POST
def training_progress(request: HttpRequest, content_id: int):
    actor = _actor(request)
    content = _load_visible(request, content_id)
    action = (request.POST.get("action") or "").strip()
    raw_percent = request.POST.get("progressPercent")
    progress_percent = None
    if raw_percent not in (None, ""):
        try:
            progress_percent = int(raw_percent)
        except (TypeError, ValueError):
            return _detail_422(
                request,
                content,
                ValidationError({"progressPercent": ["Enter a whole number."]}),
            )
    try:
        learner_update_progress(
            actor,
            content,
            action=action,
            progress_percent=progress_percent,
        )
    except ValidationError as exc:
        return _detail_422(request, content, exc)
    return _detail_redirect(content)


@enforce_policy("training_quiz_submit")
@require_POST
def training_quiz_submit(request: HttpRequest, content_id: int):
    import json

    actor = _actor(request)
    content = _load_visible(request, content_id)
    answers: dict[str, str] = {}
    raw = request.POST.get("answers")
    if raw:
        if isinstance(raw, dict):
            answers = {str(k): str(v) for k, v in raw.items()}
        else:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict):
                answers = {str(k): str(v) for k, v in parsed.items()}
    for key in request.POST:
        if key.startswith("answers[") and key.endswith("]"):
            question_id = key[len("answers[") : -1]
            answers[question_id] = str(request.POST.get(key) or "")

    try:
        submit_attempt(actor, content, answers)
    except ValidationError as exc:
        return _detail_422(request, content, exc)
    return _detail_redirect(content)


@enforce_policy("training_session_register")
@require_POST
def training_session_register(request: HttpRequest, content_id: int):
    actor = _actor(request)
    content = _load_visible(request, content_id)
    action = (request.POST.get("action") or "register").strip().lower()
    try:
        if action == "cancel":
            cancel_registration(actor, content)
        else:
            register(actor, content)
    except ValidationError as exc:
        return _detail_422(request, content, exc)
    return _detail_redirect(content)


@enforce_policy("training_certificate")
@require_GET
def training_certificate(request: HttpRequest, content_id: int):
    actor = _actor(request)
    content = _load_visible(request, content_id)
    return stream_certificate(actor, content)
