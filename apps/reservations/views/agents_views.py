"""Agent-facing room availability and reservation surfaces."""

from __future__ import annotations

from typing import Any, cast
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.reservations.booking import ReservationConflict, create_reservation
from apps.reservations.calendar import CalendarFilters, build_calendar
from apps.reservations.forms import (
    AvailabilityQueryForm,
    RoomReservationForm,
    RoomReservationSelectionForm,
)
from apps.reservations.models import Space
from apps.reservations.queries import agent_spaces, manager_spaces
from apps.reservations.taxonomy import CalendarView, SpaceType
from apps.user.models import User
from apps.user.services.role_assignments import get_effective_access
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors
from apps.web.flash import set_flash

CALENDAR_PAGE = "RoomAvailability"
NEW_PAGE = "RoomReservationNew"
ERROR_FIELD_NAMES = {
    "attendee_count": "attendeeCount",
    "ends_at": "endsAt",
    "override_reason": "overrideReason",
    "starts_at": "startsAt",
    "submission_key": "submissionKey",
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


def _calendar_filters(request: HttpRequest) -> tuple[CalendarFilters, dict]:
    user = cast(User, request.user)
    user_office = user.office
    zone = ZoneInfo(user_office.timezone) if user_office else ZoneInfo("UTC")
    today = timezone.now().astimezone(zone).date()
    form = AvailabilityQueryForm(request.GET)
    if not form.is_valid():
        return (
            CalendarFilters(view=CalendarView.WEEK, start_date=today),
            {
                "fields": {
                    key: [str(item) for item in messages]
                    for key, messages in form.errors.items()
                },
                "form": [],
            },
        )
    cleaned = form.cleaned_data
    return (
        CalendarFilters(
            view=CalendarView(cleaned.get("view") or CalendarView.WEEK.value),
            start_date=cleaned.get("date") or today,
            office_key=cleaned.get("office") or "",
            space_type=cleaned.get("type") or "",
            minimum_capacity=cleaned.get("capacity"),
            amenity_codes=cleaned.get("amenities") or (),
            space_public_id=cleaned.get("space"),
        ),
        empty_validation_errors(),
    )


def _space_for_booking(user: User, public_id) -> Space:
    space = agent_spaces(user).filter(public_id=public_id).first()
    if space is not None:
        return space
    access = get_effective_access(user)
    space = manager_spaces(user, access=access).filter(public_id=public_id).first()
    if space is None:
        raise Http404("No reservable space matches that reference.")
    return space


def _no_store(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@enforce_policy("room_availability")
@require_GET
def room_availability(request: HttpRequest):
    filters, errors = _calendar_filters(request)
    applied_filters = filters
    try:
        props = build_calendar(user=cast(User, request.user), filters=filters)
    except ValidationError as error:
        user = cast(User, request.user)
        user_office = user.office
        zone = ZoneInfo(user_office.timezone) if user_office else ZoneInfo("UTC")
        applied_filters = CalendarFilters(
            view=filters.view,
            start_date=timezone.now().astimezone(zone).date(),
            office_key=filters.office_key,
        )
        props = build_calendar(
            user=cast(User, request.user),
            filters=applied_filters,
        )
        errors = _validation_payload(error)
    props["filters"] = {
        "date": applied_filters.start_date.isoformat(),
        "view": applied_filters.view.value,
        "office": applied_filters.office_key,
        "type": applied_filters.space_type,
        "capacity": str(applied_filters.minimum_capacity or ""),
        "amenities": list(applied_filters.amenity_codes),
        "space": str(applied_filters.space_public_id or ""),
    }
    props["errors"] = errors
    return _no_store(render(request, CALENDAR_PAGE, props))


def _new_page_props(request: HttpRequest, *, errors=None) -> dict:
    data = request.GET if request.method == "GET" else request.POST
    selection = RoomReservationSelectionForm(data)
    space = None
    starts_at = None
    ends_at = None
    if selection.is_valid():
        space = _space_for_booking(
            cast(User, request.user), selection.cleaned_data["space"]
        )
        starts_at = selection.cleaned_data["startsAt"]
        ends_at = selection.cleaned_data["endsAt"]
    elif request.GET.get("space"):
        try:
            space = _space_for_booking(cast(User, request.user), request.GET["space"])
        except (ValidationError, Http404):
            space = None
    return {
        "space": (
            {
                "publicId": str(space.public_id),
                "name": space.name,
                "typeLabel": str(SpaceType(space.space_type).label),
                "capacity": space.capacity,
                "location": space.location,
                "requiresApproval": space.requires_approval,
                "minimumDurationMinutes": space.minimum_duration_minutes,
                "maximumDurationMinutes": space.maximum_duration_minutes,
            }
            if space
            else None
        ),
        "draft": {
            "startsAt": starts_at.isoformat()
            if starts_at
            else request.GET.get("startsAt", ""),
            "endsAt": ends_at.isoformat() if ends_at else request.GET.get("endsAt", ""),
            "purpose": request.POST.get("purpose", ""),
            "attendeeCount": request.POST.get("attendeeCount", ""),
        },
        "office": (
            {
                "name": space.owner_office.name,
                "timezone": space.owner_office.timezone,
            }
            if space
            else None
        ),
        "errors": errors
        or (
            empty_validation_errors()
            if selection.is_valid() or not request.GET
            else {
                "fields": {
                    key: [str(item) for item in messages]
                    for key, messages in selection.errors.items()
                },
                "form": [],
            }
        ),
        "links": {"calendarHref": reverse("room_availability")},
    }


@enforce_policy("room_reservation_new")
@require_GET
@inertia(NEW_PAGE)
def room_reservation_new(request: HttpRequest):
    return _new_page_props(request)


@enforce_policy("room_reservation_create")
@require_POST
def room_reservation_create(request: HttpRequest):
    form = RoomReservationForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            NEW_PAGE,
            _new_page_props(
                request,
                errors={
                    "fields": {
                        key: [str(item) for item in messages]
                        for key, messages in form.errors.items()
                    },
                    "form": [],
                },
            ),
        )
        response.status_code = 422
        return response
    values = form.cleaned_data
    space = _space_for_booking(cast(User, request.user), values["space"])
    try:
        reservation, created = create_reservation(
            actor=cast(User, request.user),
            space=space,
            starts_at=values["startsAt"],
            ends_at=values["endsAt"],
            purpose=values["purpose"],
            attendee_count=values.get("attendeeCount"),
            submission_key=values["submissionKey"],
        )
    except (ValidationError, ReservationConflict) as error:
        response = render(
            request,
            NEW_PAGE,
            _new_page_props(request, errors=_validation_payload(error)),
        )
        response.status_code = 409 if isinstance(error, ReservationConflict) else 422
        return response
    if created:
        set_flash(
            request,
            level="success",
            message=f"Room reservation {reservation.reference} created",
        )
    local_date = reservation.starts_at.astimezone(
        ZoneInfo(reservation.office.timezone)
    ).date()
    return redirect(
        f"{reverse('room_availability')}?date={local_date.isoformat()}&view=day"
    )
