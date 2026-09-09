"""The unified self-service reservation destination.

Every query here is scoped to ``request.user`` and nothing else. There is no
owner or office parameter on any route in this module, and adding one would be
a bug: this is the surface a person uses to see their *own* bookings, and the
absence of a selector is what makes that guarantee cheap to verify.

Writes are delegated. This module resolves which domain owns a record, then
hands the request to that domain's service, which re-checks permission, cutoff,
capacity, and overlap for itself. The unified layer never mutates a status.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from inertia import render

from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors
from apps.web.flash import set_flash
from apps.web.my_reservations.contract import (
    DISPLAY_STATUS_LABELS,
    RESERVATION_BUCKETS,
    SOURCE_LABELS,
    ReservationBucket,
    ReservationSource,
    bucket_for,
)
from apps.web.my_reservations.payloads import serialize_summary
from apps.web.my_reservations.registry import collect_reservations

INDEX_PAGE = "MyReservations"
DETAIL_PAGE = "MyReservationDetail"

#: How far the calendar view reaches either side of the anchor date. Bounded so
#: the tab cannot become an unbounded scan of a person's whole history.
CALENDAR_WINDOW = timedelta(days=45)


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _feed(request: HttpRequest):
    return collect_reservations(_actor(request), now=timezone.now())


def _filters(request: HttpRequest) -> dict[str, str]:
    tab = request.GET.get("tab", "")
    if tab not in {*RESERVATION_BUCKETS, "calendar"}:
        tab = ReservationBucket.UPCOMING
    source = request.GET.get("source", "")
    if source not in SOURCE_LABELS:
        source = ""
    status = request.GET.get("status", "")
    if status not in DISPLAY_STATUS_LABELS:
        status = ""
    return {"tab": tab, "source": source, "status": status}


@enforce_policy("my_reservations")
@require_GET
def my_reservations(request: HttpRequest):
    filters = _filters(request)
    feed = _feed(request)
    now = timezone.now()

    rows = []
    for summary in feed.summaries:
        bucket = bucket_for(summary, now=now)
        if filters["tab"] == "calendar":
            # The calendar shows what is on the schedule, not what was refused.
            if bucket == ReservationBucket.CANCELLED:
                continue
            if not (
                now - CALENDAR_WINDOW <= summary.starts_at <= now + CALENDAR_WINDOW
            ):
                continue
        elif bucket != filters["tab"]:
            continue
        if filters["source"] and summary.source != filters["source"]:
            continue
        if filters["status"] and summary.display_status != filters["status"]:
            continue
        rows.append(serialize_summary(summary))

    return render(
        request,
        INDEX_PAGE,
        {
            "reservations": rows,
            "counts": feed.counts,
            "filters": filters,
            "filterOptions": {
                "sources": [
                    {"value": key, "label": str(label)}
                    for key, label in SOURCE_LABELS.items()
                ],
                "statuses": [
                    {"value": key, "label": str(label)}
                    for key, label in DISPLAY_STATUS_LABELS.items()
                ],
            },
            # Named rather than counted: "1 source unavailable" tells the reader
            # nothing about whether the half they came for is missing.
            "degraded": {
                "failedSources": [
                    str(SOURCE_LABELS[key]) for key in feed.failed_sources
                ],
            }
            if feed.is_degraded
            else None,
            "errors": empty_validation_errors(),
        },
    )


def _own_summary(request: HttpRequest, public_id: str):
    """Find one of the reader's own rows, or 404.

    Resolution runs through the same self-scoped feed the list uses, so a public
    id belonging to somebody else is indistinguishable from one that does not
    exist.
    """
    for summary in _feed(request).summaries:
        if summary.public_id == str(public_id):
            return summary
    raise Http404("No reservation of yours matches that reference.")


@enforce_policy("my_reservation_detail")
@require_GET
def my_reservation_detail(request: HttpRequest, public_id):
    summary = _own_summary(request, public_id)
    return render(
        request,
        DETAIL_PAGE,
        {
            "reservation": serialize_summary(summary),
            "links": {"indexHref": reverse("my_reservations")},
            "errors": empty_validation_errors(),
        },
    )


def _cancel_room(request: HttpRequest, public_id: str, *, expected_status: str):
    from apps.reservations.booking import cancel_reservation
    from apps.reservations.models import Reservation

    reservation = (
        Reservation.objects.for_owner(_actor(request))
        .filter(public_id=public_id)
        .first()
    )
    if reservation is None:
        raise Http404("No reservation of yours matches that reference.")
    if expected_status and reservation.status != expected_status:
        raise ValidationError(
            {"form": ["This booking changed while the page was open. Reload it."]}
        )
    cancel_reservation(
        actor=_actor(request),
        reservation=reservation,
        reason=request.POST.get("reason") or "Cancelled by owner",
    )


def _cancel_inventory(request: HttpRequest, public_id: str, *, expected_status: str):
    from apps.inventory import reservations as reservation_services
    from apps.inventory.models import InventoryReservation
    from apps.inventory.views.reservation_views import _actor as inventory_actor

    reservation = (
        InventoryReservation.objects.for_owner(_actor(request))
        .filter(public_id=public_id)
        .first()
    )
    if reservation is None:
        raise Http404("No reservation of yours matches that reference.")
    reservation_services.cancel_reservation(
        actor=inventory_actor(request),
        reservation=reservation,
        reason=request.POST.get("reason") or "",
        # The domain compares this itself and refuses a stale action.
        expected_status=expected_status or reservation.status,
    )


@enforce_policy("my_reservation_cancel")
@require_POST
def my_reservation_cancel(request: HttpRequest, public_id):
    summary = _own_summary(request, public_id)
    if not any(action.key == "cancel" for action in summary.actions):
        raise PermissionDenied
    expected_status = request.POST.get("expectedStatus") or ""

    handlers: dict[str, Any] = {
        ReservationSource.ROOM: _cancel_room,
        ReservationSource.INVENTORY: _cancel_inventory,
    }
    try:
        handlers[summary.source](
            request, summary.public_id, expected_status=expected_status
        )
    except ValidationError as error:
        messages = (
            error.messages if hasattr(error, "messages") else ["Cancellation failed."]
        )
        set_flash(request, level="error", message=str(messages[0]))
        return redirect(reverse("my_reservation_detail", args=[summary.public_id]))
    set_flash(request, level="success", message=f"{summary.reference} cancelled")
    return redirect(f"{reverse('my_reservations')}?tab={ReservationBucket.CANCELLED}")
