"""Agent inventory reservation HTTP surface."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.inventory import reservations as reservation_services
from apps.inventory.models import InventoryReservation
from apps.inventory.reservation_payloads import (
    build_mine_page,
    build_new_reservation_page,
    serialize_reservation_detail,
)
from apps.inventory.reservations import (
    ActorContext,
    AvailabilityConflict,
    CancelNotAllowed,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors
from apps.web.flash import set_flash

NEW_PAGE = "InventoryReservationNew"
DETAIL_PAGE = "InventoryReservationDetail"
MINE_PAGE = "InventoryReservations"


def _actor(request: HttpRequest) -> ActorContext:
    user = cast(User, request.user)
    return ActorContext(user=user, permissions=frozenset(user.get_all_permissions()))


def _errors(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        data = dict(exc.message_dict)
        form = data.pop("form", [])
        fields: dict[str, list[str]] = {}
        for key, messages in data.items():
            if isinstance(messages, (list, tuple)):
                fields[key] = [str(m) for m in messages]
            else:
                fields[key] = [str(messages)]
        return {"fields": fields, "form": [str(m) for m in form]}
    return {"fields": {}, "form": [str(m) for m in exc.messages]}


def _load_own(request: HttpRequest, public_id: str) -> InventoryReservation:
    try:
        uid = UUID(str(public_id))
    except ValueError as exc:
        raise Http404 from exc
    reservation = (
        InventoryReservation.objects.for_owner(request.user)
        .select_related("item", "office")
        .filter(public_id=uid)
        .first()
    )
    if reservation is None:
        raise Http404("No reservation matches that reference.")
    return reservation


@enforce_policy("inventory_reservations_mine")
@require_GET
@inertia(MINE_PAGE)
def inventory_reservations_mine(request: HttpRequest):
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    return build_mine_page(cast(User, request.user), page=page)


@enforce_policy("inventory_reservation_new")
@require_GET
@inertia(NEW_PAGE)
def inventory_reservation_new(request: HttpRequest):
    review = (request.GET.get("review") or "").lower() in {"1", "true", "yes"}
    return build_new_reservation_page(
        cast(User, request.user),
        params=request.GET,
        review=review,
    )


@enforce_policy("inventory_reservation_create")
@require_POST
def inventory_reservation_create(request: HttpRequest):
    actor = _actor(request)
    try:
        quantity = int(request.POST.get("quantity") or "1")
    except (TypeError, ValueError):
        quantity = 0

    try:
        reservation, created = reservation_services.create_reservation(
            actor=actor,
            item_public_id=(request.POST.get("item") or "").strip(),
            pickup=(request.POST.get("pickup") or "").strip(),
            return_date=(request.POST.get("return") or "").strip(),
            quantity=quantity,
            purpose=request.POST.get("purpose") or "",
            submission_key=request.POST.get("submissionKey")
            or request.POST.get("submission_key")
            or "",
        )
    except AvailabilityConflict as exc:
        props = build_new_reservation_page(
            cast(User, request.user),
            params=request.POST,
            errors=_errors(exc),
            review=True,
        )
        response = render(request, NEW_PAGE, props)
        response.status_code = 409
        return response
    except ValidationError as exc:
        props = build_new_reservation_page(
            cast(User, request.user),
            params=request.POST,
            errors=_errors(exc),
            review=True,
        )
        response = render(request, NEW_PAGE, props)
        response.status_code = 422
        return response

    if created:
        set_flash(
            request,
            level="success",
            message=f"Reservation {reservation.reference} confirmed",
        )
    return redirect(
        reverse("inventory_reservation_detail", args=[str(reservation.public_id)])
    )


@enforce_policy("inventory_reservation_detail")
@require_GET
@inertia(DETAIL_PAGE)
def inventory_reservation_detail(request: HttpRequest, public_id: str):
    reservation = _load_own(request, public_id)
    return {
        "reservation": serialize_reservation_detail(
            reservation, viewer=cast(User, request.user)
        ),
        "errors": empty_validation_errors(),
        "justCreated": (request.GET.get("created") or "") == "1",
    }


@enforce_policy("inventory_reservation_cancel")
@require_POST
def inventory_reservation_cancel(request: HttpRequest, public_id: str):
    reservation = _load_own(request, public_id)
    try:
        reservation_services.cancel_reservation(
            actor=_actor(request),
            reservation=reservation,
            reason=request.POST.get("reason") or "",
        )
    except CancelNotAllowed as exc:
        props = {
            "reservation": serialize_reservation_detail(
                reservation, viewer=cast(User, request.user)
            ),
            "errors": _errors(exc),
            "justCreated": False,
        }
        response = render(request, DETAIL_PAGE, props)
        response.status_code = 422
        return response
    except PermissionDenied:
        raise
    except ValidationError as exc:
        props = {
            "reservation": serialize_reservation_detail(
                reservation, viewer=cast(User, request.user)
            ),
            "errors": _errors(exc),
            "justCreated": False,
        }
        response = render(request, DETAIL_PAGE, props)
        response.status_code = 422
        return response

    set_flash(request, level="success", message="Reservation cancelled")
    return redirect(
        reverse("inventory_reservation_detail", args=[str(reservation.public_id)])
    )
