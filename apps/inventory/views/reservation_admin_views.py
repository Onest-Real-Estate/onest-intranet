"""Office inventory reservation administration HTTP surface."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.inventory import reservation_lifecycle as lifecycle_services
from apps.inventory.reservation_administration import (
    build_admin_list,
    can_approve_reservations,
    can_override_reservations,
    load_reservation,
)
from apps.inventory.reservation_payloads import serialize_reservation_detail
from apps.inventory.reservations import ActorContext, AvailabilityConflict
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors
from apps.web.flash import set_flash
from apps.web.operations import operations_scope_payload

INDEX_PAGE = "AdminReservations"
DETAIL_PAGE = "AdminReservationDetail"


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


def _load(request: HttpRequest, public_id: str):
    try:
        uid = UUID(str(public_id))
    except ValueError as exc:
        raise Http404 from exc
    reservation = load_reservation(cast(User, request.user), uid)
    if reservation is None:
        raise Http404("No reservation matches that reference.")
    return reservation


@enforce_policy("operations_admin_reservations")
@require_GET
@inertia(INDEX_PAGE)
def admin_reservations_index(request: HttpRequest):
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    payload = build_admin_list(cast(User, request.user), params=request.GET, page=page)
    payload["scope"] = operations_scope_payload(request.user)
    payload["errors"] = empty_validation_errors()
    return payload


@enforce_policy("admin_reservation_detail")
@require_GET
@inertia(DETAIL_PAGE)
def admin_reservation_detail(request: HttpRequest, public_id: str):
    actor = _actor(request)
    reservation = _load(request, public_id)
    lifecycle_services.sync_overdue_reservations()
    reservation.refresh_from_db()
    return {
        "reservation": serialize_reservation_detail(
            reservation, viewer=actor.user, actor=actor, admin=True
        ),
        "can": {
            "approve": can_approve_reservations(actor.user),
            "override": can_override_reservations(actor.user),
        },
        "scope": operations_scope_payload(request.user),
        "errors": empty_validation_errors(),
    }


@enforce_policy("admin_reservation_transition")
@require_POST
def admin_reservation_transition(request: HttpRequest, public_id: str):
    actor = _actor(request)
    reservation = _load(request, public_id)
    action = (request.POST.get("action") or "").strip()
    expected_version = (
        request.POST.get("expectedVersion")
        or request.POST.get("expected_version")
        or ""
    )
    expected_status = (request.POST.get("expectedStatus") or "").strip() or None
    reason = request.POST.get("reason") or ""
    notes = request.POST.get("notes") or ""
    override = (request.POST.get("override") or "").lower() in {"1", "true", "yes"}

    try:
        checkout_quantity = int(request.POST.get("checkoutQuantity") or "0") or None
    except (TypeError, ValueError):
        checkout_quantity = None
    try:
        return_quantity = int(request.POST.get("returnQuantity") or "0") or None
    except (TypeError, ValueError):
        return_quantity = None

    try:
        reservation = lifecycle_services.transition(
            actor=actor,
            reservation=reservation,
            action=action,
            expected_version=expected_version,
            expected_status=expected_status,
            reason=reason,
            notes=notes,
            checkout_quantity=checkout_quantity,
            return_quantity=return_quantity,
            override=override,
        )
    except AvailabilityConflict as exc:
        response = render(
            request,
            DETAIL_PAGE,
            {
                "reservation": serialize_reservation_detail(
                    _load(request, public_id),
                    viewer=actor.user,
                    actor=actor,
                    admin=True,
                ),
                "can": {
                    "approve": can_approve_reservations(actor.user),
                    "override": can_override_reservations(actor.user),
                },
                "scope": operations_scope_payload(request.user),
                "errors": _errors(exc),
            },
        )
        response.status_code = 409
        return response
    except PermissionDenied:
        raise
    except ValidationError as exc:
        response = render(
            request,
            DETAIL_PAGE,
            {
                "reservation": serialize_reservation_detail(
                    _load(request, public_id),
                    viewer=actor.user,
                    actor=actor,
                    admin=True,
                ),
                "can": {
                    "approve": can_approve_reservations(actor.user),
                    "override": can_override_reservations(actor.user),
                },
                "scope": operations_scope_payload(request.user),
                "errors": _errors(exc),
            },
        )
        response.status_code = 422
        return response

    set_flash(request, level="success", message="Reservation updated")
    return redirect(
        reverse("admin_reservation_detail", args=[str(reservation.public_id)])
    )
