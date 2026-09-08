"""Scoped room administration surfaces.

Every view here resolves its target through the hierarchy-scoped queryset in
``apps.reservations.queries`` before it touches a service. A public id that the
signed-in administrator cannot reach returns 404 rather than 403, so the
workspace never confirms the existence of a room outside their scope.
"""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from inertia import render

from apps.reservations.administration import (
    ImpactReport,
    ImpactRequiresAcknowledgement,
    cancel_reservation_as_admin,
    future_bookings,
    move_reservation,
    remove_availability_exception,
    replace_weekly_schedule,
    set_space_activation,
    update_availability_exception,
    update_space,
)
from apps.reservations.booking import ReservationConflict
from apps.reservations.forms import (
    AvailabilityBlockForm,
    ReservationCancelForm,
    ReservationMoveForm,
    ScheduleIntervalForm,
    SpaceActivationForm,
    SpaceAdminFilterForm,
    SpaceCreateForm,
    SpaceEditForm,
    SpaceRetireForm,
)
from apps.reservations.models import Amenity, Reservation, Space
from apps.reservations.queries import manager_spaces, space_for_manager
from apps.reservations.services import create_availability_exception, create_space
from apps.reservations.taxonomy import (
    ExceptionKind,
    ExceptionVisibility,
    ReservationPermission,
    ReservationStatus,
    SpacePermission,
    SpaceStatus,
    SpaceType,
)
from apps.user.models import Office, User
from apps.user.services.role_assignments import get_effective_access
from apps.web.authorization import enforce_policy, scope_queryset_for_offices
from apps.web.capability import evaluate_permission, has_capability
from apps.web.contracts import empty_validation_errors
from apps.web.flash import set_flash

INDEX_PAGE = "SpaceAdministration"
WORKSPACE_PAGE = "SpaceAdministrationWorkspace"
PAGE_SIZE = 20

ERROR_FIELD_NAMES = {
    "access_instructions": "accessInstructions",
    "booking_horizon_days": "bookingHorizonDays",
    "buffer_after_minutes": "bufferAfterMinutes",
    "buffer_before_minutes": "bufferBeforeMinutes",
    "cancellation_cutoff_minutes": "cancellationCutoffMinutes",
    "display_order": "displayOrder",
    "ends_at": "endsAt",
    "maximum_duration_minutes": "maximumDurationMinutes",
    "minimum_duration_minutes": "minimumDurationMinutes",
    "minimum_notice_minutes": "minimumNoticeMinutes",
    "owner_office": "office",
    "space_type": "spaceType",
    "starts_at": "startsAt",
}


def _validation_payload(error: ValidationError) -> dict[str, Any]:
    if hasattr(error, "message_dict"):
        values = dict(error.message_dict)
        form = values.pop("form", [])
        return {
            "fields": {
                ERROR_FIELD_NAMES.get(key, key): [str(item) for item in messages]
                for key, messages in values.items()
            },
            "form": [str(item) for item in form],
        }
    return {"fields": {}, "form": [str(item) for item in error.messages]}


def _form_errors(form) -> dict[str, Any]:
    return {
        "fields": {
            ERROR_FIELD_NAMES.get(key, key): [str(item) for item in messages]
            for key, messages in form.errors.items()
        },
        "form": [],
    }


def _impact_payload(report: ImpactReport) -> dict[str, Any]:
    return {
        "total": report.total,
        "bookings": [
            {
                "reference": item.reference,
                "publicId": item.public_id,
                "ownerName": item.owner_name,
                "startsAt": item.starts_at.isoformat(),
                "endsAt": item.ends_at.isoformat(),
                "reason": item.reason,
            }
            for item in report.bookings
        ],
    }


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _office_options(user: User, *, access) -> list[Office]:
    queryset = Office.objects.filter(is_active=True, is_assignable=True).select_related(
        "region"
    )
    if not has_capability(user, SpacePermission.VIEW, access=access):
        return []
    return list(
        scope_queryset_for_offices(user, queryset).order_by(
            "region__name", "name", "pk"
        )
    )


def _capabilities(user: User, *, access, office: Office | None) -> dict[str, bool]:
    def allowed(permission) -> bool:
        if office is None:
            return has_capability(user, permission, access=access)
        return evaluate_permission(
            user, permission, office=office, access=access
        ).allowed

    return {
        "canManageSpaces": allowed(SpacePermission.MANAGE),
        "canManageSchedules": allowed(SpacePermission.MANAGE_SCHEDULE),
        "canManageReservations": allowed(ReservationPermission.MANAGE),
        "canOverride": allowed(ReservationPermission.OVERRIDE),
        "canViewSensitive": allowed(SpacePermission.VIEW_SENSITIVE),
    }


def _space_row(space: Space) -> dict[str, Any]:
    return {
        "publicId": str(space.public_id),
        "name": space.name,
        "officeKey": space.owner_office.stable_key,
        "officeName": space.owner_office.name,
        "spaceType": space.space_type,
        "spaceTypeLabel": str(SpaceType(space.space_type).label),
        "capacity": space.capacity,
        "location": space.location,
        "status": space.status,
        "statusLabel": str(SpaceStatus(space.status).label),
        "isReservable": space.is_reservable,
        "displayOrder": space.display_order,
        "amenities": [
            {"code": amenity.code, "name": amenity.name}
            for amenity in space.amenities.all()
        ],
    }


@enforce_policy("space_administration")
@require_GET
def space_administration(request: HttpRequest):
    """Scoped, filterable list of every room the administrator governs."""
    user = _actor(request)
    access = get_effective_access(user)
    form = SpaceAdminFilterForm(request.GET)
    errors = empty_validation_errors()
    filters: dict[str, Any] = {}
    if form.is_valid():
        filters = form.cleaned_data
    else:
        errors = _form_errors(form)

    queryset = manager_spaces(user, access=access, include_retired=True)
    search = (filters.get("q") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(location__icontains=search)
        )
    if filters.get("office"):
        queryset = queryset.filter(owner_office__slug=filters["office"])
    if filters.get("type"):
        queryset = queryset.filter(space_type=filters["type"])
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    if filters.get("capacity"):
        queryset = queryset.filter(capacity__gte=filters["capacity"])
    for code in filters.get("amenities") or ():
        queryset = queryset.filter(amenities__code=code)

    paginator = Paginator(
        queryset.distinct().order_by("owner_office__name", "display_order", "name"),
        PAGE_SIZE,
    )
    page = paginator.get_page(filters.get("page") or 1)
    offices = _office_options(user, access=access)

    return render(
        request,
        INDEX_PAGE,
        {
            "spaces": [_space_row(space) for space in page.object_list],
            # Matches the shared ``PaginationMeta`` contract the design-system
            # ``Pagination`` component reads.
            "pagination": {
                "page": page.number,
                "pageSize": PAGE_SIZE,
                "totalItems": paginator.count,
                "totalPages": paginator.num_pages,
                "hasNext": page.has_next(),
                "hasPrevious": page.has_previous(),
            },
            "filters": {
                "q": search,
                "office": filters.get("office") or "",
                "type": filters.get("type") or "",
                "status": filters.get("status") or "",
                "capacity": str(filters.get("capacity") or ""),
                "amenities": list(filters.get("amenities") or ()),
            },
            "filterOptions": {
                "offices": [
                    {
                        "value": item.slug,
                        "label": item.name,
                        "regionName": item.region_name(),
                    }
                    for item in offices
                ],
                "spaceTypes": [
                    {"value": value, "label": str(label)}
                    for value, label in SpaceType.choices
                ],
                "statuses": [
                    {"value": value, "label": str(label)}
                    for value, label in SpaceStatus.choices
                ],
                "amenities": [
                    {"value": amenity.code, "label": amenity.name}
                    for amenity in Amenity.objects.filter(is_active=True).order_by(
                        "display_order", "name", "pk"
                    )
                ],
            },
            "capabilities": _capabilities(user, access=access, office=None),
            "errors": errors,
        },
    )


def _require_space(request: HttpRequest, public_id) -> Space:
    user = _actor(request)
    access = get_effective_access(user)
    space = space_for_manager(
        user, access=access, public_id=public_id, include_retired=True
    )
    if space is None:
        raise Http404("No room matches that reference within your scope.")
    return space


def _workspace_props(
    request: HttpRequest,
    space: Space,
    *,
    errors: dict[str, Any] | None = None,
    impact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user = _actor(request)
    access = get_effective_access(user)
    capabilities = _capabilities(user, access=access, office=space.owner_office)
    sensitive = capabilities["canViewSensitive"]
    upcoming = list(future_bookings(space)[:50])
    blocks = space.availability_exceptions.filter(ends_at__gte=timezone.now()).order_by(
        "starts_at"
    )
    if not sensitive:
        blocks = blocks.filter(visibility=ExceptionVisibility.PUBLIC)

    return {
        "space": {
            **_space_row(space),
            "description": space.description,
            "accessInstructions": space.access_instructions if sensitive else "",
            "updatedAt": space.updated_at.isoformat(),
            "retiredAt": space.retired_at.isoformat() if space.retired_at else None,
            "policy": {
                "minimumDurationMinutes": space.minimum_duration_minutes,
                "maximumDurationMinutes": space.maximum_duration_minutes,
                "bookingHorizonDays": space.booking_horizon_days,
                "minimumNoticeMinutes": space.minimum_notice_minutes,
                "bufferBeforeMinutes": space.buffer_before_minutes,
                "bufferAfterMinutes": space.buffer_after_minutes,
                "cancellationCutoffMinutes": space.cancellation_cutoff_minutes,
                "requiresApproval": space.requires_approval,
                "isReservable": space.is_reservable,
            },
        },
        "schedule": [
            {
                "weekday": item.weekday,
                "startsAt": item.starts_at.isoformat(),
                "endsAt": item.ends_at.isoformat(),
            }
            for item in space.weekly_availability.order_by("weekday", "starts_at")
        ],
        "blocks": [
            {
                "publicId": str(item.public_id),
                "kind": item.kind,
                "kindLabel": str(ExceptionKind(item.kind).label),
                "startsAt": item.starts_at.isoformat(),
                "endsAt": item.ends_at.isoformat(),
                "reason": item.reason,
                "visibility": item.visibility,
            }
            for item in blocks
        ],
        "upcomingBookings": [
            {
                "publicId": str(item.public_id),
                "reference": item.reference,
                "ownerName": item.owner.display_name or item.owner.email,
                "startsAt": item.starts_at.isoformat(),
                "endsAt": item.ends_at.isoformat(),
                "status": item.status,
                "statusLabel": str(ReservationStatus(item.status).label),
                "attendeeCount": item.attendee_count,
            }
            for item in upcoming
        ],
        "moveTargets": [
            {
                "value": str(item.public_id),
                "label": item.name,
                "capacity": item.capacity,
            }
            for item in manager_spaces(user, access=access)
            .filter(owner_office_id=space.owner_office_id, status=SpaceStatus.ACTIVE)
            .exclude(pk=space.pk)
            .order_by("display_order", "name")
        ],
        "options": {
            "spaceTypes": [
                {"value": value, "label": str(label)}
                for value, label in SpaceType.choices
            ],
            "blockKinds": [
                {"value": value, "label": str(label)}
                for value, label in ExceptionKind.choices
            ],
            "visibilities": [
                {"value": value, "label": str(label)}
                for value, label in ExceptionVisibility.choices
            ],
        },
        "capabilities": capabilities,
        "impact": impact,
        "errors": errors or empty_validation_errors(),
        "links": {"indexHref": reverse("space_administration")},
    }


@enforce_policy("space_administration_workspace")
@require_GET
def space_administration_workspace(request: HttpRequest, public_id):
    space = _require_space(request, public_id)
    return render(request, WORKSPACE_PAGE, _workspace_props(request, space))


def _workspace_error(
    request: HttpRequest,
    space: Space,
    *,
    errors: dict[str, Any],
    impact: dict[str, Any] | None = None,
    status: int = 422,
):
    response = render(
        request,
        WORKSPACE_PAGE,
        _workspace_props(request, space, errors=errors, impact=impact),
    )
    response.status_code = status
    return response


def _workspace_redirect(space: Space):
    return redirect(reverse("space_administration_workspace", args=[space.public_id]))


@enforce_policy("space_administration_create")
@require_POST
def space_administration_create(request: HttpRequest):
    user = _actor(request)
    access = get_effective_access(user)
    form = SpaceCreateForm(request.POST)
    if not form.is_valid():
        return redirect(reverse("space_administration"))
    values = form.cleaned_data
    office = next(
        (
            item
            for item in _office_options(user, access=access)
            if item.slug == values["office"]
        ),
        None,
    )
    if office is None:
        raise PermissionDenied
    try:
        space = create_space(
            actor=user,
            owner_office=office,
            name=values["name"],
            space_type=values["spaceType"],
            capacity=values["capacity"],
            description=values.get("description", ""),
            location=values.get("location", ""),
            access_instructions=values.get("accessInstructions", ""),
            display_order=values.get("displayOrder") or 0,
        )
    except ValidationError:
        return redirect(reverse("space_administration"))
    set_flash(request, level="success", message=f"{space.name} created")
    return _workspace_redirect(space)


@enforce_policy("space_administration_update")
@require_POST
def space_administration_update(request: HttpRequest, public_id):
    space = _require_space(request, public_id)
    form = SpaceEditForm(request.POST)
    if not form.is_valid():
        return _workspace_error(request, space, errors=_form_errors(form))
    values = form.cleaned_data
    try:
        updated, _ = update_space(
            actor=_actor(request),
            space=space,
            expected_updated_at=values.get("expectedUpdatedAt"),
            acknowledge_impact=values.get("acknowledgeImpact", False),
            name=values["name"],
            space_type=values["spaceType"],
            capacity=values["capacity"],
            description=values.get("description", ""),
            location=values.get("location", ""),
            access_instructions=values.get("accessInstructions", ""),
            display_order=values.get("displayOrder") or 0,
            minimum_duration_minutes=values["minimumDurationMinutes"],
            maximum_duration_minutes=values["maximumDurationMinutes"],
            booking_horizon_days=values["bookingHorizonDays"],
            minimum_notice_minutes=values["minimumNoticeMinutes"],
            buffer_before_minutes=values["bufferBeforeMinutes"],
            buffer_after_minutes=values["bufferAfterMinutes"],
            cancellation_cutoff_minutes=values["cancellationCutoffMinutes"],
            requires_approval=values.get("requiresApproval", False),
            is_reservable=values.get("isReservable", False),
        )
    except ImpactRequiresAcknowledgement as error:
        return _workspace_error(
            request,
            space,
            errors=_validation_payload(error),
            impact=_impact_payload(error.report),
            status=409,
        )
    except ValidationError as error:
        return _workspace_error(request, space, errors=_validation_payload(error))
    set_flash(request, level="success", message=f"{updated.name} saved")
    return _workspace_redirect(updated)


@enforce_policy("space_administration_activation")
@require_POST
def space_administration_activation(request: HttpRequest, public_id):
    space = _require_space(request, public_id)
    form = SpaceActivationForm(request.POST)
    if not form.is_valid():
        return _workspace_error(request, space, errors=_form_errors(form))
    values = form.cleaned_data
    try:
        updated, _ = set_space_activation(
            actor=_actor(request),
            space=space,
            active=values.get("active", False),
            reason=values.get("reason", ""),
            acknowledge_impact=values.get("acknowledgeImpact", False),
        )
    except ImpactRequiresAcknowledgement as error:
        return _workspace_error(
            request,
            space,
            errors=_validation_payload(error),
            impact=_impact_payload(error.report),
            status=409,
        )
    except ValidationError as error:
        return _workspace_error(request, space, errors=_validation_payload(error))
    state = "activated" if updated.is_reservable else "deactivated"
    set_flash(request, level="success", message=f"{updated.name} {state}")
    return _workspace_redirect(updated)


@enforce_policy("space_administration_retire")
@require_POST
def space_administration_retire(request: HttpRequest, public_id):
    from apps.reservations.services import retire_space

    space = _require_space(request, public_id)
    form = SpaceRetireForm(request.POST)
    if not form.is_valid():
        return _workspace_error(request, space, errors=_form_errors(form))
    try:
        retired = retire_space(
            actor=_actor(request), space=space, reason=form.cleaned_data["reason"]
        )
    except ValidationError as error:
        return _workspace_error(request, space, errors=_validation_payload(error))
    set_flash(request, level="success", message=f"{retired.name} retired")
    return _workspace_redirect(retired)


@enforce_policy("space_administration_schedule")
@require_POST
def space_administration_schedule(request: HttpRequest, public_id):
    space = _require_space(request, public_id)
    intervals: list[tuple[int, Any, Any]] = []
    parsed = _parse_intervals(request.POST.getlist("intervals"))
    if parsed is None:
        return _workspace_error(
            request,
            space,
            errors={
                "fields": {"schedule": ["Send a valid interval list."]},
                "form": [],
            },
        )
    for item in parsed:
        form = ScheduleIntervalForm(item)
        if not form.is_valid():
            return _workspace_error(request, space, errors=_form_errors(form))
        intervals.append(
            (
                form.cleaned_data["weekday"],
                form.cleaned_data["startsAt"],
                form.cleaned_data["endsAt"],
            )
        )
    try:
        updated, _ = replace_weekly_schedule(
            actor=_actor(request),
            space=space,
            intervals=intervals,
            acknowledge_impact=request.POST.get("acknowledgeImpact") in {"true", "on"},
        )
    except ImpactRequiresAcknowledgement as error:
        return _workspace_error(
            request,
            space,
            errors=_validation_payload(error),
            impact=_impact_payload(error.report),
            status=409,
        )
    except ValidationError as error:
        return _workspace_error(request, space, errors=_validation_payload(error))
    set_flash(request, level="success", message=f"{updated.name} hours updated")
    return _workspace_redirect(updated)


def _parse_intervals(raw: Any) -> list[dict[str, Any]] | None:
    """Read the interval list back out of a ``QueryDict``.

    ``InertiaJsonPostMiddleware`` flattens a JSON array into repeated values and
    re-encodes each nested object as a JSON string, so the list arrives as
    ``getlist("intervals") == ['{"weekday": 1, ...}', ...]``. A single
    JSON-encoded array is also accepted, which is what a form-encoded caller
    would send.
    """
    import json

    if not isinstance(raw, list):
        return None
    if len(raw) == 1 and isinstance(raw[0], str):
        try:
            single = json.loads(raw[0])
        except ValueError:
            return None
        if isinstance(single, list):
            return single
        if isinstance(single, dict):
            return [single]
        return None
    items: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict):
            items.append(entry)
            continue
        if not isinstance(entry, str):
            return None
        try:
            value = json.loads(entry)
        except ValueError:
            return None
        if not isinstance(value, dict):
            return None
        items.append(value)
    return items


@enforce_policy("space_administration_block_create")
@require_POST
def space_administration_block_create(request: HttpRequest, public_id):
    space = _require_space(request, public_id)
    form = AvailabilityBlockForm(request.POST)
    if not form.is_valid():
        return _workspace_error(request, space, errors=_form_errors(form))
    values = form.cleaned_data
    try:
        create_availability_exception(
            actor=_actor(request),
            space=space,
            kind=values["kind"],
            starts_at=values["startsAt"],
            ends_at=values["endsAt"],
            reason=values["reason"],
            visibility=values["visibility"],
        )
    except (ReservationConflict, ValidationError) as error:
        status = 409 if isinstance(error, ReservationConflict) else 422
        return _workspace_error(
            request, space, errors=_validation_payload(error), status=status
        )
    set_flash(request, level="success", message="Block added")
    return _workspace_redirect(space)


def _require_block(request: HttpRequest, public_id):
    user = _actor(request)
    access = get_effective_access(user)
    scoped = manager_spaces(user, access=access, include_retired=True)
    from apps.reservations.models import SpaceAvailabilityException

    block = (
        SpaceAvailabilityException.objects.filter(public_id=public_id)
        .filter(space__in=scoped.values("pk"))
        .select_related("space", "space__owner_office", "occupancy")
        .first()
    )
    if block is None:
        raise Http404("No block matches that reference within your scope.")
    return block


@enforce_policy("space_administration_block_update")
@require_POST
def space_administration_block_update(request: HttpRequest, public_id):
    block = _require_block(request, public_id)
    form = AvailabilityBlockForm(request.POST)
    if not form.is_valid():
        return _workspace_error(request, block.space, errors=_form_errors(form))
    values = form.cleaned_data
    try:
        update_availability_exception(
            actor=_actor(request),
            exception=block,
            starts_at=values["startsAt"],
            ends_at=values["endsAt"],
            kind=values["kind"],
            reason=values["reason"],
            visibility=values["visibility"],
        )
    except (ReservationConflict, ValidationError) as error:
        status = 409 if isinstance(error, ReservationConflict) else 422
        return _workspace_error(
            request, block.space, errors=_validation_payload(error), status=status
        )
    set_flash(request, level="success", message="Block updated")
    return _workspace_redirect(block.space)


@enforce_policy("space_administration_block_delete")
@require_POST
def space_administration_block_delete(request: HttpRequest, public_id):
    block = _require_block(request, public_id)
    space = block.space
    try:
        remove_availability_exception(actor=_actor(request), exception=block)
    except ValidationError as error:
        return _workspace_error(request, space, errors=_validation_payload(error))
    set_flash(request, level="success", message="Block removed")
    return _workspace_redirect(space)


def _require_reservation(request: HttpRequest, public_id) -> Reservation:
    user = _actor(request)
    access = get_effective_access(user)
    scoped = manager_spaces(user, access=access, include_retired=True)
    reservation = (
        Reservation.objects.filter(public_id=public_id)
        .filter(space__in=scoped.values("pk"))
        .select_related("space", "space__owner_office", "office", "owner", "occupancy")
        .first()
    )
    if reservation is None:
        raise Http404("No booking matches that reference within your scope.")
    return reservation


@enforce_policy("space_administration_booking_move")
@require_POST
def space_administration_booking_move(request: HttpRequest, public_id):
    reservation = _require_reservation(request, public_id)
    space = reservation.space
    form = ReservationMoveForm(request.POST)
    if not form.is_valid():
        return _workspace_error(request, space, errors=_form_errors(form))
    user = _actor(request)
    access = get_effective_access(user)
    # The destination is resolved through the actor's own scoped queryset, never
    # taken on trust from the posted identifier.
    destination = space_for_manager(
        user, access=access, public_id=form.cleaned_data["destination"]
    )
    if destination is None:
        raise Http404("No destination room matches that reference within your scope.")
    try:
        move_reservation(
            actor=user,
            reservation=reservation,
            destination=destination,
            reason=form.cleaned_data["reason"],
        )
    except (ReservationConflict, ValidationError) as error:
        status = 409 if isinstance(error, ReservationConflict) else 422
        return _workspace_error(
            request, space, errors=_validation_payload(error), status=status
        )
    set_flash(
        request,
        level="success",
        message=f"{reservation.reference} moved to {destination.name}",
    )
    return _workspace_redirect(destination)


@enforce_policy("space_administration_booking_cancel")
@require_POST
def space_administration_booking_cancel(request: HttpRequest, public_id):
    reservation = _require_reservation(request, public_id)
    space = reservation.space
    form = ReservationCancelForm(request.POST)
    if not form.is_valid():
        return _workspace_error(request, space, errors=_form_errors(form))
    try:
        cancel_reservation_as_admin(
            actor=_actor(request),
            reservation=reservation,
            reason=form.cleaned_data["reason"],
        )
    except ValidationError as error:
        return _workspace_error(request, space, errors=_validation_payload(error))
    set_flash(request, level="success", message=f"{reservation.reference} cancelled")
    return _workspace_redirect(space)
