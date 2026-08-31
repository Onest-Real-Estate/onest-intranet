"""Inventory administration HTTP surface."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.inventory.administration import (
    StaleItemVersion,
    build_inventory_list,
    detail_payload,
    ensure_manage_authority,
    load_item,
    parse_admin_filters,
    parse_sort,
    writable_offices,
)
from apps.inventory.forms import (
    InventoryItemCreateForm,
    InventoryItemTransferForm,
    InventoryItemTransitionForm,
    InventoryItemUpdateForm,
    InventoryPhotoForm,
    form_errors,
)
from apps.inventory.services import (
    ActorContext,
    create_item,
    transfer_item_with_version,
    transition_item_state,
    update_item_with_version,
    upload_photo,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors
from apps.web.operations import operations_scope_payload

__all__ = [
    "inventory_admin_index",
    "inventory_item_create",
    "inventory_item_detail",
    "inventory_item_update",
    "inventory_item_transition",
    "inventory_item_transfer",
    "inventory_item_photo",
]

_STALE = {
    "fields": {},
    "form": ["This item changed since you opened it. Reload and try again."],
}

_SHEET_DRAFT_FIELDS = {
    "name": "name",
    "owner_office": "ownerId",
    "category": "category",
    "tracking_mode": "trackingMode",
    "condition": "condition",
    "asset_id": "assetId",
    "serial_number": "serialNumber",
    "total_quantity": "totalQuantity",
    "storage_location": "storageLocation",
    "notes": "notes",
    "internal_notes": "internalNotes",
    "replacement_value": "replacementValue",
    "replacement_currency": "replacementCurrency",
}


def _actor(request: HttpRequest) -> ActorContext:
    user = cast(User, request.user)
    return ActorContext(
        user=user,
        permissions=frozenset(user.get_all_permissions()),
    )


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _sheet_draft(request: HttpRequest) -> dict[str, str]:
    draft: dict[str, str] = {}
    for source, target in _SHEET_DRAFT_FIELDS.items():
        value = request.POST.get(source, "")
        if value:
            draft[target] = value
    return draft


def _validation_error_payload(exc: ValidationError) -> dict:
    if hasattr(exc, "message_dict"):
        fields = {
            field: [str(message) for message in messages]
            for field, messages in exc.message_dict.items()
            if field != "__all__"
        }
        form_msgs = [str(m) for m in exc.message_dict.get("__all__", [])]
        return {"fields": fields, "form": form_msgs or list(exc.messages)}
    return {"fields": {}, "form": list(exc.messages)}


def _detail_props(
    actor: User,
    item,
    *,
    request: HttpRequest,
    errors: dict | None = None,
) -> dict:
    props = detail_payload(
        actor,
        item,
        availability_start=request.GET.get("availability_start", ""),
        availability_end=request.GET.get("availability_end", ""),
    )
    props["scope"] = operations_scope_payload(actor)
    props["validation"] = errors or empty_validation_errors()
    return props


def _render_detail(
    request: HttpRequest,
    actor: User,
    item,
    *,
    errors: dict,
    status: int,
) -> HttpResponse:
    response = render(
        request,
        "InventoryItemWorkspace",
        _detail_props(actor, item, request=request, errors=errors),
    )
    response.status_code = status
    return response


def _render_index_with_sheet_errors(
    request: HttpRequest,
    actor: User,
    *,
    errors: dict,
) -> HttpResponse:
    filters = parse_admin_filters(request.POST)
    payload = build_inventory_list(actor, filters=filters)
    response = render(
        request,
        "InventoryAdministration",
        {
            **payload,
            "scope": operations_scope_payload(actor),
            "validation": errors,
            "createSheet": {"open": True, "draft": _sheet_draft(request)},
        },
    )
    response.status_code = 422
    return response


def _load_or_404(actor: User, public_id: UUID | str):
    if not isinstance(public_id, UUID):
        try:
            public_id = UUID(str(public_id))
        except ValueError as exc:
            raise Http404 from exc
    item = load_item(actor, public_id)
    if item is None:
        raise Http404
    return item


@enforce_policy("operations_admin_inventory")
@require_GET
@inertia("InventoryAdministration")
def inventory_admin_index(request: HttpRequest):
    actor = cast(User, request.user)
    filters = parse_admin_filters(request.GET)
    sort_key, sort_direction = parse_sort(request.GET)
    payload = build_inventory_list(
        actor,
        filters=filters,
        page=_page_param(request),
        sort_key=sort_key,
        sort_direction=sort_direction,
    )
    create_open = request.GET.get("create") == "1"
    return {
        **payload,
        "scope": operations_scope_payload(actor),
        "validation": empty_validation_errors(),
        "createSheet": {"open": create_open, "draft": {}} if create_open else None,
    }


@enforce_policy("admin_inventory_create")
@require_POST
def inventory_item_create(request: HttpRequest):
    actor = cast(User, request.user)
    sheet_mode = request.POST.get("context") == "sheet"
    scope_offices = writable_offices(actor)
    form = InventoryItemCreateForm(request.POST, owner_queryset=scope_offices)
    if not form.is_valid():
        if sheet_mode:
            return _render_index_with_sheet_errors(
                request, actor, errors=form_errors(form)
            )
        return _render_detail(
            request, actor, None, errors=form_errors(form), status=422
        )

    owner = form.cleaned_data["owner_office"]
    try:
        ensure_manage_authority(actor, owner)
    except PermissionDenied:
        if sheet_mode:
            return _render_index_with_sheet_errors(
                request,
                actor,
                errors={"fields": {}, "form": ["Permission denied."]},
            )
        return _render_detail(
            request,
            actor,
            None,
            errors={"fields": {}, "form": ["Permission denied."]},
            status=403,
        )

    ctx = _actor(request)
    sensitive = ctx.holds("inventory.view_inventory_sensitive")
    item = create_item(
        actor=ctx,
        owner_office=owner,
        name=form.cleaned_data["name"],
        category=form.cleaned_data["category"],
        tracking_mode=form.cleaned_data["tracking_mode"],
        condition=form.cleaned_data["condition"],
        asset_id=form.cleaned_data.get("asset_id", ""),
        serial_number=form.cleaned_data.get("serial_number", "") if sensitive else "",
        total_quantity=form.cleaned_data["total_quantity"],
        storage_location=form.cleaned_data.get("storage_location", ""),
        notes=form.cleaned_data.get("notes", ""),
        internal_notes=form.cleaned_data.get("internal_notes", "") if sensitive else "",
        replacement_value=form.cleaned_data.get("replacement_value")
        if sensitive
        else None,
        replacement_currency=form.cleaned_data.get("replacement_currency", "USD"),
        requires_approval=form.cleaned_data.get("requires_approval", False),
    )
    return redirect(reverse("admin_inventory_item", args=[item.public_id]))


@enforce_policy("admin_inventory_item")
@require_GET
@inertia("InventoryItemWorkspace")
def inventory_item_detail(request: HttpRequest, public_id: str):
    actor = cast(User, request.user)
    item = _load_or_404(actor, public_id)
    return _detail_props(actor, item, request=request)


@enforce_policy("admin_inventory_update")
@require_POST
def inventory_item_update(request: HttpRequest, public_id: str):
    actor = cast(User, request.user)
    item = _load_or_404(actor, public_id)
    form = InventoryItemUpdateForm(request.POST)
    if not form.is_valid():
        return _render_detail(
            request, actor, item, errors=form_errors(form), status=422
        )

    ctx = _actor(request)
    sensitive = ctx.holds("inventory.view_inventory_sensitive")
    fields = {
        "name": form.cleaned_data["name"],
        "category": form.cleaned_data["category"],
        "condition": form.cleaned_data["condition"],
        "storage_location": form.cleaned_data.get("storage_location", ""),
        "notes": form.cleaned_data.get("notes", ""),
        "photo_is_public": form.cleaned_data.get("photo_is_public", False),
        "requires_approval": form.cleaned_data.get("requires_approval", False),
    }
    if sensitive:
        fields["internal_notes"] = form.cleaned_data.get("internal_notes", "")
        fields["replacement_value"] = form.cleaned_data.get("replacement_value")
        fields["replacement_currency"] = form.cleaned_data.get("replacement_currency")
    if form.cleaned_data.get("total_quantity") is not None:
        fields["total_quantity"] = form.cleaned_data["total_quantity"]

    try:
        update_item_with_version(
            actor=ctx,
            item=item,
            expected_version=form.cleaned_data["expected_version"],
            **fields,
        )
    except StaleItemVersion:
        return _render_detail(request, actor, item, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request, actor, item, errors=_validation_error_payload(exc), status=422
        )
    return redirect(reverse("admin_inventory_item", args=[item.public_id]))


@enforce_policy("admin_inventory_transition")
@require_POST
def inventory_item_transition(request: HttpRequest, public_id: str):
    actor = cast(User, request.user)
    item = _load_or_404(actor, public_id)
    form = InventoryItemTransitionForm(request.POST)
    if not form.is_valid():
        return _render_detail(
            request, actor, item, errors=form_errors(form), status=422
        )
    try:
        transition_item_state(
            actor=_actor(request),
            item=item,
            action=form.cleaned_data["action"],
            expected_version=form.cleaned_data["expected_version"],
            reason=form.cleaned_data.get("reason", ""),
        )
    except StaleItemVersion:
        return _render_detail(request, actor, item, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request, actor, item, errors=_validation_error_payload(exc), status=422
        )
    return redirect(reverse("admin_inventory_item", args=[item.public_id]))


@enforce_policy("admin_inventory_transfer")
@require_POST
def inventory_item_transfer(request: HttpRequest, public_id: str):
    actor = cast(User, request.user)
    item = _load_or_404(actor, public_id)
    scope_offices = writable_offices(actor).exclude(pk=item.owner_office.pk)
    form = InventoryItemTransferForm(request.POST, owner_queryset=scope_offices)
    if not form.is_valid():
        return _render_detail(
            request, actor, item, errors=form_errors(form), status=422
        )
    destination = form.cleaned_data["to_office"]
    try:
        ensure_manage_authority(actor, destination)
        transfer_item_with_version(
            actor=_actor(request),
            item=item,
            to_office=destination,
            expected_version=form.cleaned_data["expected_version"],
            reason=form.cleaned_data.get("reason", ""),
        )
    except StaleItemVersion:
        return _render_detail(request, actor, item, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request, actor, item, errors=_validation_error_payload(exc), status=422
        )
    return redirect(reverse("admin_inventory_item", args=[item.public_id]))


@enforce_policy("admin_inventory_photo")
@require_POST
def inventory_item_photo(request: HttpRequest, public_id: str):
    actor = cast(User, request.user)
    item = _load_or_404(actor, public_id)
    form = InventoryPhotoForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_detail(
            request, actor, item, errors=form_errors(form), status=422
        )
    try:
        upload_photo(
            actor=_actor(request),
            item=item,
            expected_version=form.cleaned_data["expected_version"],
            uploaded_file=form.cleaned_data["photo"],
        )
    except StaleItemVersion:
        return _render_detail(request, actor, item, errors=_STALE, status=409)
    except ValidationError as exc:
        return _render_detail(
            request, actor, item, errors=_validation_error_payload(exc), status=422
        )
    return redirect(reverse("admin_inventory_item", args=[item.public_id]))
