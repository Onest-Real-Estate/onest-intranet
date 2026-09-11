"""Marketing workspace HTTP surface."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.marketing.administration import (
    PAGE_SIZE,
    StaleMarketingVersion,
    TransitionRefused,
    WorkspaceFilters,
    admin_row,
    apply_workspace_filters,
    asset_version,
    audience_choice_payload,
    capabilities,
    category_options,
    create_asset,
    detail_payload,
    duplicate_version,
    manageable_queryset,
    order_for_workspace,
    preview_payload,
    publishable_office_queryset,
    transition,
    update_asset,
)
from apps.marketing.audience import search_recipients
from apps.marketing.forms import (
    MarketingAssetForm,
    MarketingDuplicateForm,
    MarketingTransitionForm,
)
from apps.marketing.media_service import (
    admin_files_payload,
    allowed_matrix_payload,
    assert_can_manage_media,
    attach_file,
    file_payload,
    remove_file,
    reorder_files,
    replace_file,
)
from apps.marketing.models import MarketingAsset, MarketingFile
from apps.marketing.services import asset_type_filter_options
from apps.user.models import Office, User
from apps.user.services.role_assignments import has_effective_permission
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response, validation_errors

INDEX_PAGE = "MarketingAdministration"
WORKSPACE_PAGE = "MarketingWorkspace"

MANAGE_PERMISSION = "web.manage_marketing_resources"

_SHEET_DRAFT_FIELDS: tuple[str, ...] = (
    "owner_office",
    "title",
    "description",
    "usage_instructions",
    "category",
    "asset_type",
    "publish_at",
    "expires_at",
    "jurisdiction_state_codes",
    "brand_codes",
    "display_order",
)

_SHEET_DRAFT_LISTS: tuple[str, ...] = (
    "audience_roles",
    "audience_regions",
    "audience_offices",
    "audience_users",
)


def _require_manage(actor: User) -> None:
    from django.core.exceptions import PermissionDenied

    if not has_effective_permission(actor, MANAGE_PERMISSION):
        raise PermissionDenied("You cannot manage marketing resources.")


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _target(request: HttpRequest, asset_id: int) -> MarketingAsset:
    actor = cast(User, request.user)
    return get_object_or_404(manageable_queryset(actor), pk=asset_id)


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
    return draft


def index_props(
    actor: User,
    *,
    params,
    page: int = 1,
    create_sheet: dict[str, Any] | None = None,
    errors: dict | None = None,
) -> dict[str, Any]:
    from apps.marketing.models import MarketingCategory

    known_categories = list(MarketingCategory.objects.values_list("code", flat=True))
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
        "assets": list_response(
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
            "assetTypes": asset_type_filter_options(),
            "offices": offices,
        },
        "createOptions": {
            "offices": offices,
            "categories": category_options(),
            "assetTypes": asset_type_filter_options(),
            "audience": audience_choice_payload(actor),
        },
        "createSheet": create_sheet,
        "capabilities": capabilities(actor).payload(),
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("operations_admin_marketing_resources")
@require_GET
@inertia(INDEX_PAGE)
def marketing_administration_index(request: HttpRequest):
    actor = cast(User, request.user)
    _require_manage(actor)
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
    asset: MarketingAsset | None = None,
    errors: dict | None = None,
    posted=None,
    preview_office: str = "",
    preview_role: str = "",
) -> dict[str, Any]:
    office = _preview_office(actor, preview_office) if asset else None
    role = (
        preview_role
        if preview_role
        in {option["value"] for option in audience_choice_payload(actor)["roles"]}
        else ""
    )
    return {
        "asset": detail_payload(asset, actor=actor) if asset else None,
        "officeOptions": [
            {"value": office_row.pk, "label": office_row.name}
            for office_row in publishable_office_queryset(actor)
        ],
        "categoryOptions": category_options(
            include_codes=((asset.category.code,) if asset and asset.category else ())
        ),
        "assetTypeOptions": asset_type_filter_options(),
        "audienceOptions": audience_choice_payload(actor),
        "capabilities": capabilities(actor).payload(),
        "preview": (
            {
                **preview_payload(asset, actor=actor, office=office, role_code=role),
                "roleCode": role,
                "officeId": office.pk if office else None,
            }
            if asset
            else None
        ),
        "errors": errors or empty_validation_errors(),
        "posted": _posted_payload(posted),
    }


def _posted_payload(posted) -> dict[str, list[str]] | None:
    if posted is None:
        return None
    return {key: posted.getlist(key) for key in posted}


@enforce_policy("marketing_new")
@require_GET
@inertia(WORKSPACE_PAGE)
def marketing_new(request: HttpRequest):
    actor = cast(User, request.user)
    _require_manage(actor)
    return workspace_props(actor)


@enforce_policy("marketing_edit")
@require_GET
@inertia(WORKSPACE_PAGE)
def marketing_edit(request: HttpRequest, asset_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    return workspace_props(
        actor,
        asset=_target(request, asset_id),
        preview_office=request.GET.get("previewOffice", "").strip(),
        preview_role=request.GET.get("previewRole", "").strip(),
    )


def _render_workspace(
    request: HttpRequest,
    *,
    asset: MarketingAsset | None,
    errors: dict,
    status: int,
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(
            actor,
            asset=asset,
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


def _submit(request: HttpRequest, asset: MarketingAsset | None) -> HttpResponse:
    actor = cast(User, request.user)
    from_sheet = asset is None and request.POST.get("context") == "sheet"
    form = MarketingAssetForm(
        request.POST, instance=asset or MarketingAsset(), actor=actor
    )
    if not form.is_valid():
        errors = validation_errors(form)
        if from_sheet:
            return _render_index_with_sheet_errors(request, errors=errors)
        return _render_workspace(request, asset=asset, errors=errors, status=422)
    try:
        if asset is None:
            saved = create_asset(
                actor=actor,
                office=form.cleaned_data["owner_office"],
                cleaned=form.field_values,
                selectors=form.selectors,
            )
        else:
            saved = update_asset(
                actor=actor,
                asset=asset,
                cleaned=form.field_values,
                selectors=form.selectors,
                expected_version=form.cleaned_data.get("expected_version", ""),
            )
    except StaleMarketingVersion as exc:
        return _render_workspace(
            request,
            asset=MarketingAsset.objects.get(pk=asset.pk) if asset else None,
            errors={"fields": {}, "form": [exc.message]},
            status=409,
        )
    except ValidationError as exc:
        errors = _validation_payload(exc)
        if from_sheet:
            return _render_index_with_sheet_errors(request, errors=errors)
        return _render_workspace(request, asset=asset, errors=errors, status=422)
    return redirect("marketing_edit", asset_id=saved.pk)


@enforce_policy("marketing_create")
@require_POST
def marketing_create(request: HttpRequest):
    _require_manage(cast(User, request.user))
    return _submit(request, None)


@enforce_policy("marketing_update")
@require_POST
def marketing_update(request: HttpRequest, asset_id: int):
    _require_manage(cast(User, request.user))
    return _submit(request, _target(request, asset_id))


def _lifecycle_failure(
    request: HttpRequest, asset: MarketingAsset, message: str, status: int
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(
            actor,
            asset=MarketingAsset.objects.get(pk=asset.pk),
            errors={"fields": {}, "form": [message]},
        ),
    )
    response.status_code = status
    return response


@enforce_policy("marketing_lifecycle")
@require_POST
def marketing_lifecycle(request: HttpRequest, asset_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    asset = _target(request, asset_id)
    form = MarketingTransitionForm(request.POST)
    if not form.is_valid():
        return _lifecycle_failure(
            request, asset, "That is not a marketing action.", 422
        )
    try:
        transition(
            actor=actor,
            asset=asset,
            action=form.cleaned_data["action"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleMarketingVersion as exc:
        return _lifecycle_failure(request, asset, exc.message, 409)
    except TransitionRefused as exc:
        return _lifecycle_failure(request, asset, exc.message, 422)
    except ValidationError as exc:
        response = render(
            request,
            WORKSPACE_PAGE,
            workspace_props(
                actor,
                asset=MarketingAsset.objects.get(pk=asset.pk),
                errors=_validation_payload(exc),
            ),
        )
        response.status_code = 422
        return response
    return redirect("marketing_edit", asset_id=asset.pk)


@enforce_policy("marketing_duplicate_version")
@require_POST
def marketing_duplicate_version(request: HttpRequest, asset_id: int):
    actor = cast(User, request.user)
    _require_manage(actor)
    asset = _target(request, asset_id)
    form = MarketingDuplicateForm(request.POST)
    if not form.is_valid():
        return _lifecycle_failure(request, asset, "Send the current version.", 422)
    try:
        draft = duplicate_version(
            actor=actor,
            asset=asset,
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleMarketingVersion as exc:
        return _lifecycle_failure(request, asset, exc.message, 409)
    except ValidationError as exc:
        return _lifecycle_failure(
            request, asset, "; ".join(str(m) for m in exc.messages), 422
        )
    return redirect("marketing_edit", asset_id=draft.pk)


@enforce_policy("marketing_recipient_search")
@require_GET
def marketing_recipient_search(request: HttpRequest):
    actor = cast(User, request.user)
    return JsonResponse({"results": search_recipients(actor, request.GET.get("q", ""))})


def _managed_asset(actor: User, asset_id: int) -> MarketingAsset:
    asset = get_object_or_404(
        MarketingAsset.objects.select_related("owner_office", "category"),
        pk=asset_id,
    )
    assert_can_manage_media(actor, asset)
    return asset


@enforce_policy("marketing_media_manager")
@require_GET
@inertia("MarketingMediaManager")
def marketing_media_manager(request: HttpRequest, asset_id: int):
    actor = cast(User, request.user)
    asset = _managed_asset(actor, asset_id)
    return {
        "asset": {
            "id": asset.pk,
            "title": asset.title,
            "status": asset.status,
            "version": asset_version(asset),
        },
        "files": admin_files_payload(asset, actor=actor),
        "limits": allowed_matrix_payload(),
        "capabilities": capabilities(actor).payload(),
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


@enforce_policy("marketing_media_upload")
@require_POST
def marketing_media_upload(request: HttpRequest, asset_id: int):
    actor = cast(User, request.user)
    asset = _managed_asset(actor, asset_id)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _media_error(ValidationError({"file": "Choose a file to upload."}))
    role = (request.POST.get("role") or MarketingFile.Role.EXPORT).strip()
    if role not in {MarketingFile.Role.EXPORT, MarketingFile.Role.SOURCE}:
        role = MarketingFile.Role.EXPORT
    try:
        row = attach_file(actor, asset, uploaded, role=role)
    except ValidationError as exc:
        return _media_error(exc)
    return JsonResponse(
        {"file": file_payload(row, for_admin=True, actor=actor)}, status=201
    )


@enforce_policy("marketing_media_replace")
@require_POST
def marketing_media_replace(request: HttpRequest, file_id: int):
    actor = cast(User, request.user)
    row = get_object_or_404(
        MarketingFile.objects.select_related("asset", "asset__owner_office"),
        pk=file_id,
    )
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _media_error(ValidationError({"file": "Choose a replacement file."}))
    try:
        replacement = replace_file(actor, row, uploaded)
    except ValidationError as exc:
        return _media_error(exc)
    return JsonResponse(
        {"file": file_payload(replacement, for_admin=True, actor=actor)}
    )


@enforce_policy("marketing_media_remove")
@require_POST
def marketing_media_remove(request: HttpRequest, file_id: int):
    actor = cast(User, request.user)
    row = get_object_or_404(
        MarketingFile.objects.select_related("asset", "asset__owner_office"),
        pk=file_id,
    )
    asset_id = row.asset.pk
    try:
        remove_file(actor, row)
    except ValidationError as exc:
        return _media_error(exc)
    return redirect("marketing_media_manager", asset_id=asset_id)


@enforce_policy("marketing_media_reorder")
@require_POST
def marketing_media_reorder(request: HttpRequest, asset_id: int):
    actor = cast(User, request.user)
    asset = _managed_asset(actor, asset_id)
    raw = request.POST.getlist("order") or request.POST.getlist("ordered_ids")
    ordered_ids = [int(value) for value in raw if str(value).isdigit()]
    role = (request.POST.get("role") or MarketingFile.Role.EXPORT).strip()
    if role not in {MarketingFile.Role.EXPORT, MarketingFile.Role.SOURCE}:
        role = MarketingFile.Role.EXPORT
    try:
        reorder_files(actor, asset, ordered_ids, role=role)
    except ValidationError as exc:
        return _media_error(exc)
    return redirect("marketing_media_manager", asset_id=asset.pk)
