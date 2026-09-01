"""Overdue inventory dashboard queue for authorized managers."""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse

from apps.inventory.overdue import is_overdue, overdue_queryset, return_calendar_day
from apps.inventory.reservation_administration import (
    can_view_reservations,
    managed_reservation_queryset,
)
from apps.web.dashboard.envelope import ProviderResult, empty, ready
from apps.web.dashboard.providers import DashboardContext

_MAX_ROWS = 5


def overdue_inventory_queue(context: DashboardContext) -> ProviderResult:
    user = context.user
    if not can_view_reservations(user):
        return empty(
            "No overdue inventory in scope",
            "Overdue returns appear here when you can view office reservations.",
        )

    queryset = overdue_queryset(
        managed_reservation_queryset(user),
        now=context.now,
    )
    total = queryset.count()
    if total == 0:
        return empty(
            "No overdue inventory",
            "Checked-out items past their return date in your scope appear here.",
        )

    rows_payload = []
    for reservation in queryset.order_by("ends_at", "pk")[:_MAX_ROWS]:
        if not is_overdue(reservation, now=context.now):
            continue
        owner = reservation.owner
        return_day = return_calendar_day(reservation)
        rows_payload.append(
            {
                "id": str(reservation.public_id),
                "title": reservation.item_name,
                "subtitle": owner.get_full_name() or owner.email,
                "meta": f"Due {return_day.isoformat()}",
                "badge": "Overdue",
                "tone": "destructive",
                "href": reverse(
                    "admin_reservation_detail",
                    args=[str(reservation.public_id)],
                ),
            }
        )

    list_href = reverse("admin_reservations")
    list_href = f"{list_href}?{urlencode({'status': 'overdue'})}"
    return ready(
        {
            "total": total,
            "rows": rows_payload,
            "viewAllHref": list_href,
        }
    )
