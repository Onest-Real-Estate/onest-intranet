"""Training workspace HTTP surface."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.training.administration import (
    PAGE_SIZE,
    StaleTrainingVersion,
    TransitionRefused,
    WorkspaceFilters,
    admin_row,
    apply_workspace_filters,
    audience_choice_payload,
    capabilities,
    category_options,
    content_version,
    create_content,
    detail_payload,
    duplicate_version,
    manageable_queryset,
    order_for_workspace,
    preview_payload,
    publishable_office_queryset,
    transition,
    update_content,
)
from apps.training.audience import search_recipients
from apps.training.forms import (
    TrainingContentForm,
    TrainingDuplicateForm,
    TrainingTransitionForm,
)
from apps.training.media_service import (
    admin_media_payload,
    assert_can_manage_media,
    attach_media,
    media_payload,
    remove_media,
    reorder_attachments,
    replace_media,
)
from apps.training.models import TrainingContent, TrainingMedia
from apps.training.services import content_type_filter_options, tool_filter_options
from apps.user.models import Office, User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response, validation_errors

INDEX_PAGE = "TrainingAdministration"
WORKSPACE_PAGE = "TrainingWorkspace"

_SHEET_DRAFT_FIELDS: tuple[str, ...] = (
    "owner_office",
    "title",
    "summary",
    "body",
    "category",
    "content_type",
    "publish_at",
    "expires_at",
    "tool_code",
    "external_url",
    "estimated_minutes",
    "embed_url",
)

_SHEET_DRAFT_LISTS: tuple[str, ...] = (
    "audience_roles",
    "audience_regions",
    "audience_offices",
    "audience_users",
)


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _target(request: HttpRequest, content_id: int) -> TrainingContent:
    actor = cast(User, request.user)
    return get_object_or_404(manageable_queryset(actor), pk=content_id)


def _sheet_draft(params) -> dict[str, Any]:
    draft: dict[str, Any] = {
        name: value for name in _SHEET_DRAFT_FIELDS if (value := params.get(name, ""))
    }
    for name in _SHEET_DRAFT_LISTS:
        values = params.getlist(name)
        if values:
            draft[name] = values
    if params.get("audience_company") in {"on", "true", "True"}:
        draft["audience_company"] = "on"
    if params.get("is_required") in {"on", "true", "True"}:
        draft["is_required"] = "on"
    return draft


def index_props(
    actor: User,
    *,
    params,
    page: int = 1,
    create_sheet: dict[str, Any] | None = None,
    errors: dict | None = None,
) -> dict[str, Any]:
    from apps.training.models import TrainingCategory

    known_categories = list(TrainingCategory.objects.values_list("code", flat=True))
    filters = WorkspaceFilters.from_params(params, known_categories=known_categories)
    rows = order_for_workspace(
        apply_workspace_filters(manageable_queryset(actor), filters)
    )
    total = rows.count()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * PAGE_SIZE
    items = [admin_row(row) for row in rows[start : start + PAGE_SIZE]]
    offices = [
        {"value": office.pk, "label": office.name}
        for office in publishable_office_queryset(actor)
    ]
    return {
        "trainings": list_response(
            items,
            page=current,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters.as_payload(),
            sort_key="updatedAt",
            sort_direction="desc",
        ),
        "filterOptions": {
            "categories": category_options(include_codes=(filters.category,)),
            "contentTypes": content_type_filter_options(),
            "offices": offices,
        },
        "createOptions": {
            "offices": offices,
            "categories": category_options(),
            "contentTypes": content_type_filter_options(),
            "tools": tool_filter_options(),
            "audience": audience_choice_payload(actor),
        },
        "createSheet": create_sheet,
        "capabilities": capabilities(actor).payload(),
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("operations_admin_training")
@require_GET
@inertia(INDEX_PAGE)
def training_administration_index(request: HttpRequest):
    actor = cast(User, request.user)
    opening = request.GET.get("create") == "1"
    return index_props(
        actor,
        params=request.GET,
        page=_page_param(request),
        create_sheet={"open": True, "draft": {}} if opening else None,
    )


def _render_index_with_sheet_errors(
    request: HttpRequest, *, errors: dict
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        INDEX_PAGE,
        index_props(
            actor,
            params=request.POST,
            create_sheet={"open": True, "draft": _sheet_draft(request.POST)},
            errors=errors,
        ),
    )
    response.status_code = 422
    return response


def _preview_office(actor: User, raw: str) -> Office | None:
    if not raw.isdigit():
        return None
    return publishable_office_queryset(actor).filter(pk=int(raw)).first()


def workspace_props(
    actor: User,
    *,
    content: TrainingContent | None = None,
    errors: dict | None = None,
    posted=None,
    preview_office: str = "",
    preview_role: str = "",
) -> dict[str, Any]:
    office = _preview_office(actor, preview_office) if content else None
    role = (
        preview_role
        if preview_role
        in {option["value"] for option in audience_choice_payload(actor)["roles"]}
        else ""
    )
    return {
        "content": detail_payload(content, actor=actor) if content else None,
        "officeOptions": [
            {"value": office_row.pk, "label": office_row.name}
            for office_row in publishable_office_queryset(actor)
        ],
        "categoryOptions": category_options(
            include_codes=(
                (content.category.code,) if content and content.category else ()
            )
        ),
        "contentTypeOptions": content_type_filter_options(),
        "toolOptions": tool_filter_options(),
        "audienceOptions": audience_choice_payload(actor),
        "capabilities": capabilities(actor).payload(),
        "preview": (
            {
                **preview_payload(content, actor=actor, office=office, role_code=role),
                "roleCode": role,
                "officeId": office.pk if office else None,
            }
            if content
            else None
        ),
        "errors": errors or empty_validation_errors(),
        "posted": _posted_payload(posted),
    }


def _posted_payload(posted) -> dict[str, list[str]] | None:
    if posted is None:
        return None
    return {key: posted.getlist(key) for key in posted}


@enforce_policy("training_new")
@require_GET
@inertia(WORKSPACE_PAGE)
def training_new(request: HttpRequest):
    return workspace_props(cast(User, request.user))


@enforce_policy("training_edit")
@require_GET
@inertia(WORKSPACE_PAGE)
def training_edit(request: HttpRequest, content_id: int):
    actor = cast(User, request.user)
    return workspace_props(
        actor,
        content=_target(request, content_id),
        preview_office=request.GET.get("previewOffice", "").strip(),
        preview_role=request.GET.get("previewRole", "").strip(),
    )


def _render_workspace(
    request: HttpRequest,
    *,
    content: TrainingContent | None,
    errors: dict,
    status: int,
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(
            actor,
            content=content,
            errors=errors,
            posted=request.POST,
        ),
    )
    response.status_code = status
    return response


def _validation_payload(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        data = exc.message_dict
        return {
            "fields": {
                field: [str(message) for message in messages]
                for field, messages in data.items()
                if field != "__all__"
            },
            "form": [str(message) for message in data.get("__all__", [])],
        }
    return {"fields": {}, "form": [str(message) for message in exc.messages]}


def _submit(request: HttpRequest, content: TrainingContent | None) -> HttpResponse:
    actor = cast(User, request.user)
    from_sheet = content is None and request.POST.get("context") == "sheet"
    form = TrainingContentForm(
        request.POST, instance=content or TrainingContent(), actor=actor
    )
    if not form.is_valid():
        errors = validation_errors(form)
        if from_sheet:
            return _render_index_with_sheet_errors(request, errors=errors)
        return _render_workspace(request, content=content, errors=errors, status=422)
    try:
        if content is None:
            saved = create_content(
                actor=actor,
                office=form.cleaned_data["owner_office"],
                cleaned=form.field_values,
                selectors=form.selectors,
                embed_url=form.cleaned_data.get("embed_url", ""),
            )
        else:
            saved = update_content(
                actor=actor,
                content=content,
                cleaned=form.field_values,
                selectors=form.selectors,
                expected_version=form.cleaned_data.get("expected_version", ""),
                embed_url=form.cleaned_data.get("embed_url"),
            )
    except StaleTrainingVersion as exc:
        return _render_workspace(
            request,
            content=TrainingContent.objects.get(pk=content.pk) if content else None,
            errors={"fields": {}, "form": [exc.message]},
            status=409,
        )
    except ValidationError as exc:
        errors = _validation_payload(exc)
        if from_sheet:
            return _render_index_with_sheet_errors(request, errors=errors)
        return _render_workspace(request, content=content, errors=errors, status=422)
    return redirect("training_edit", content_id=saved.pk)


@enforce_policy("training_create")
@require_POST
def training_create(request: HttpRequest):
    return _submit(request, None)


@enforce_policy("training_update")
@require_POST
def training_update(request: HttpRequest, content_id: int):
    return _submit(request, _target(request, content_id))


def _lifecycle_failure(
    request: HttpRequest, content: TrainingContent, message: str, status: int
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(
            actor,
            content=TrainingContent.objects.get(pk=content.pk),
            errors={"fields": {}, "form": [message]},
        ),
    )
    response.status_code = status
    return response


@enforce_policy("training_lifecycle")
@require_POST
def training_lifecycle(request: HttpRequest, content_id: int):
    actor = cast(User, request.user)
    content = _target(request, content_id)
    form = TrainingTransitionForm(request.POST)
    if not form.is_valid():
        return _lifecycle_failure(
            request, content, "That is not a training action.", 422
        )
    try:
        transition(
            actor=actor,
            content=content,
            action=form.cleaned_data["action"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleTrainingVersion as exc:
        return _lifecycle_failure(request, content, exc.message, 409)
    except TransitionRefused as exc:
        return _lifecycle_failure(request, content, exc.message, 422)
    except ValidationError as exc:
        response = render(
            request,
            WORKSPACE_PAGE,
            workspace_props(
                actor,
                content=TrainingContent.objects.get(pk=content.pk),
                errors=_validation_payload(exc),
            ),
        )
        response.status_code = 422
        return response
    return redirect("training_edit", content_id=content.pk)


@enforce_policy("training_duplicate_version")
@require_POST
def training_duplicate_version(request: HttpRequest, content_id: int):
    actor = cast(User, request.user)
    content = _target(request, content_id)
    form = TrainingDuplicateForm(request.POST)
    if not form.is_valid():
        return _lifecycle_failure(request, content, "Send the current version.", 422)
    try:
        draft = duplicate_version(
            actor=actor,
            content=content,
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleTrainingVersion as exc:
        return _lifecycle_failure(request, content, exc.message, 409)
    except ValidationError as exc:
        return _lifecycle_failure(
            request, content, "; ".join(str(m) for m in exc.messages), 422
        )
    return redirect("training_edit", content_id=draft.pk)


@enforce_policy("training_recipient_search")
@require_GET
def training_recipient_search(request: HttpRequest):
    actor = cast(User, request.user)
    return JsonResponse({"results": search_recipients(actor, request.GET.get("q", ""))})


def _managed_content(actor: User, content_id: int) -> TrainingContent:
    content = get_object_or_404(
        TrainingContent.objects.select_related("owner_office", "category"),
        pk=content_id,
    )
    assert_can_manage_media(actor, content)
    return content


def _allowed_matrix_payload() -> dict[str, Any]:
    from apps.training.media import MAX_ATTACHMENTS, TRAINING_ALLOWED_MEDIA

    extensions = sorted(TRAINING_ALLOWED_MEDIA.keys())
    max_bytes = max(rule.max_bytes for rule in TRAINING_ALLOWED_MEDIA.values())
    return {
        "primary": {"extensions": extensions, "maxBytes": max_bytes},
        "attachment": {
            "extensions": extensions,
            "maxBytes": max_bytes,
            "maxCount": MAX_ATTACHMENTS,
        },
    }


@enforce_policy("training_media_manager")
@require_GET
@inertia("TrainingMediaManager")
def training_media_manager(request: HttpRequest, content_id: int):
    actor = cast(User, request.user)
    content = _managed_content(actor, content_id)
    return {
        "content": {
            "id": content.pk,
            "title": content.title,
            "status": content.status,
            "version": content_version(content),
        },
        "media": admin_media_payload(content),
        "limits": _allowed_matrix_payload(),
        "validation": empty_validation_errors(),
    }


def _media_error(exc: ValidationError, status: int = 422) -> JsonResponse:
    if hasattr(exc, "message_dict"):
        data = exc.message_dict
        return JsonResponse(
            {
                "validation": {
                    "fields": {
                        field: [str(message) for message in messages]
                        for field, messages in data.items()
                        if field != "__all__"
                    },
                    "form": [str(message) for message in data.get("__all__", [])],
                }
            },
            status=status,
        )
    return JsonResponse(
        {
            "validation": {
                "fields": {},
                "form": [str(message) for message in exc.messages],
            }
        },
        status=status,
    )


@enforce_policy("training_media_upload")
@require_POST
def training_media_upload(request: HttpRequest, content_id: int):
    actor = cast(User, request.user)
    content = _managed_content(actor, content_id)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _media_error(ValidationError({"file": "Choose a file to upload."}))
    role = (
        TrainingMedia.Role.PRIMARY
        if request.POST.get("role") == TrainingMedia.Role.PRIMARY
        else TrainingMedia.Role.ATTACHMENT
    )
    try:
        media = attach_media(actor, content, uploaded, role=role)
    except ValidationError as exc:
        return _media_error(exc)
    return JsonResponse({"media": media_payload(media, for_admin=True)}, status=201)


@enforce_policy("training_media_replace")
@require_POST
def training_media_replace(request: HttpRequest, media_id: int):
    actor = cast(User, request.user)
    media = get_object_or_404(
        TrainingMedia.objects.select_related("content", "content__owner_office"),
        pk=media_id,
    )
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _media_error(ValidationError({"file": "Choose a replacement file."}))
    try:
        replacement = replace_media(actor, media, uploaded)
    except ValidationError as exc:
        return _media_error(exc)
    return JsonResponse({"media": media_payload(replacement, for_admin=True)})


@enforce_policy("training_media_remove")
@require_POST
def training_media_remove(request: HttpRequest, media_id: int):
    actor = cast(User, request.user)
    media = get_object_or_404(
        TrainingMedia.objects.select_related("content", "content__owner_office"),
        pk=media_id,
    )
    content_id = media.content.pk
    try:
        remove_media(actor, media)
    except ValidationError as exc:
        return _media_error(exc)
    return redirect("training_media_manager", content_id=content_id)


@enforce_policy("training_media_reorder")
@require_POST
def training_media_reorder(request: HttpRequest, content_id: int):
    actor = cast(User, request.user)
    content = _managed_content(actor, content_id)
    raw = request.POST.getlist("order") or request.POST.getlist("ordered_ids")
    ordered_ids = [int(value) for value in raw if str(value).isdigit()]
    try:
        reorder_attachments(actor, content, ordered_ids)
    except ValidationError as exc:
        return _media_error(exc)
    return redirect("training_media_manager", content_id=content.pk)


def _parse_json_list(raw: str | None) -> list:
    import json

    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


@enforce_policy("training_quiz_save")
@require_POST
def training_quiz_save(request: HttpRequest, content_id: int):
    from apps.training.quiz_service import save_quiz_definition

    actor = cast(User, request.user)
    content = _target(request, content_id)
    raw_max = (request.POST.get("maxAttempts") or "").strip()
    max_attempts = int(raw_max) if raw_max.isdigit() else None
    try:
        threshold = int(request.POST.get("passThresholdPercent") or "80")
    except (TypeError, ValueError):
        threshold = 80
    questions = _parse_json_list(request.POST.get("questions"))
    try:
        save_quiz_definition(
            actor=actor,
            content=content,
            pass_threshold_percent=threshold,
            max_attempts=max_attempts,
            feedback_policy=(
                request.POST.get("feedbackPolicy") or "score_only"
            ).strip(),
            questions=questions,
        )
    except ValidationError as exc:
        return _render_workspace(
            request, content=content, errors=_validation_payload(exc), status=422
        )
    return redirect("training_edit", content_id=content.pk)


@enforce_policy("training_session_save")
@require_POST
def training_session_save(request: HttpRequest, content_id: int):
    from apps.training.session_service import save_session_definition

    actor = cast(User, request.user)
    content = _target(request, content_id)
    raw_capacity = (request.POST.get("capacity") or "").strip()
    capacity = int(raw_capacity) if raw_capacity.isdigit() else None
    try:
        duration = int(request.POST.get("durationMinutes") or "60")
    except (TypeError, ValueError):
        duration = 60
    try:
        save_session_definition(
            actor=actor,
            content=content,
            starts_at=request.POST.get("startsAt"),
            timezone_name=(request.POST.get("timezone") or "").strip(),
            duration_minutes=duration,
            capacity=capacity,
            meeting_url=request.POST.get("meetingUrl") or "",
            registration_opens_at=request.POST.get("registrationOpensAt") or None,
            registration_closes_at=request.POST.get("registrationClosesAt") or None,
        )
    except ValidationError as exc:
        return _render_workspace(
            request, content=content, errors=_validation_payload(exc), status=422
        )
    return redirect("training_edit", content_id=content.pk)


@enforce_policy("training_modules_save")
@require_POST
def training_modules_save(request: HttpRequest, content_id: int):
    from apps.training.course_service import save_modules

    actor = cast(User, request.user)
    content = _target(request, content_id)
    child_ids = [
        int(value)
        for value in (
            request.POST.getlist("childIds")
            or _parse_json_list(request.POST.get("childIds"))
        )
        if str(value).isdigit() or isinstance(value, int)
    ]
    try:
        save_modules(actor=actor, course=content, child_ids=child_ids)
    except ValidationError as exc:
        return _render_workspace(
            request, content=content, errors=_validation_payload(exc), status=422
        )
    return redirect("training_edit", content_id=content.pk)


@enforce_policy("training_progress_correct")
@require_POST
def training_progress_correct(request: HttpRequest, content_id: int):
    from apps.training.progress_service import correct_progress
    from apps.training.session_service import correct_attendance

    actor = cast(User, request.user)
    content = _target(request, content_id)
    raw_learner = (request.POST.get("learnerId") or "").strip()
    if not raw_learner.isdigit():
        return _render_workspace(
            request,
            content=content,
            errors={"fields": {"learnerId": ["Choose a learner."]}, "form": []},
            status=422,
        )
    learner = get_object_or_404(User, pk=int(raw_learner))
    kind = (request.POST.get("kind") or "progress").strip()
    reason = request.POST.get("reason") or ""
    status_value = (request.POST.get("status") or "").strip()
    try:
        if kind == "attendance":
            correct_attendance(
                actor=actor,
                learner=learner,
                content=content,
                status=status_value,
                reason=reason,
            )
        else:
            correct_progress(
                actor=actor,
                learner=learner,
                content=content,
                status=status_value,
                reason=reason,
            )
    except ValidationError as exc:
        return _render_workspace(
            request, content=content, errors=_validation_payload(exc), status=422
        )
    except PermissionDenied:
        raise
    return redirect("training_edit", content_id=content.pk)


@enforce_policy("training_certificate_issue")
@require_POST
def training_certificate_issue(request: HttpRequest, content_id: int):
    from apps.training.certificate_service import issue_certificate

    actor = cast(User, request.user)
    content = _target(request, content_id)
    raw_learner = (request.POST.get("learnerId") or "").strip()
    if not raw_learner.isdigit():
        return _render_workspace(
            request,
            content=content,
            errors={"fields": {"learnerId": ["Choose a learner."]}, "form": []},
            status=422,
        )
    learner = get_object_or_404(User, pk=int(raw_learner))
    force = (request.POST.get("force") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        issue_certificate(actor=actor, content=content, learner=learner, force=force)
    except ValidationError as exc:
        return _render_workspace(
            request, content=content, errors=_validation_payload(exc), status=422
        )
    except PermissionDenied:
        raise
    return redirect("training_edit", content_id=content.pk)


@enforce_policy("training_certificate_approve")
@require_POST
def training_certificate_approve(request: HttpRequest, certificate_id: int):
    from apps.training.certificate_service import approve_certificate
    from apps.training.models import TrainingCertificate

    actor = cast(User, request.user)
    certificate = get_object_or_404(
        TrainingCertificate.objects.select_related(
            "content", "content__owner_office", "user"
        ),
        pk=certificate_id,
    )
    try:
        approve_certificate(actor=actor, certificate=certificate)
    except ValidationError as exc:
        return _render_workspace(
            request,
            content=certificate.content,
            errors=_validation_payload(exc),
            status=422,
        )
    except PermissionDenied:
        raise
    return redirect("training_edit", content_id=certificate.content.pk)
