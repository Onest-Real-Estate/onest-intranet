"""Room-utilization dashboard widget for holders of ``web.view_reservations``.

Utilization is booked room-minutes over *published open* room-minutes. The
denominator matters: a room with no published hours for a day was never
bookable, so counting it as 0% used would report a scheduling problem that does
not exist. Such a day is reported as unmeasured instead, which is what the
meter's null ratio renders.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.urls import reverse

from apps.reservations.models import Occupancy, Space
from apps.reservations.queries import manager_spaces
from apps.reservations.taxonomy import SpacePermission
from apps.web.capability import has_capability
from apps.web.dashboard.envelope import ProviderResult, empty, ready
from apps.web.dashboard.providers import DashboardContext

#: Today plus the rest of the working week. Long enough to be a trend, short
#: enough that every minute counted is one somebody can still act on.
_WINDOW_DAYS = 7


def _open_minutes(space: Space, day: date) -> int:
    """Published open minutes for one space on one local date."""
    total = 0
    for interval in space.weekly_availability.all():
        if interval.weekday != day.weekday():
            continue
        start = interval.starts_at.hour * 60 + interval.starts_at.minute
        end = interval.ends_at.hour * 60 + interval.ends_at.minute
        if end > start:
            total += end - start
    return total


def room_utilization(context: DashboardContext) -> ProviderResult:
    """Booked share of published open hours across the reader's rooms."""
    user = context.user
    access = context.access
    if not has_capability(user, SpacePermission.VIEW, access=access):
        return empty(
            "No rooms in scope",
            "Room utilization appears here once you can view reservations.",
        )

    spaces = list(
        manager_spaces(user, access=access).filter(is_reservable=True)[:200],
    )
    if not spaces:
        return empty(
            "No reservable rooms",
            "Utilization is measured once your scope has a bookable room.",
            action_label="Open room administration",
            action_href=reverse("space_administration"),
        )

    # Each room's own office decides its local day, so a future cross-timezone
    # office does not shift another office's window.
    by_space = {space.pk: space for space in spaces}
    zones = {space.pk: ZoneInfo(space.owner_office.timezone) for space in spaces}
    today = context.now.astimezone(zones[spaces[0].pk]).date()
    days = [today + timedelta(days=offset) for offset in range(_WINDOW_DAYS)]

    window_start = min(
        context.now.astimezone(zones[space.pk]).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for space in spaces
    )
    window_end = window_start + timedelta(days=_WINDOW_DAYS)

    booked: dict[int, int] = defaultdict(int)
    occupancies = Occupancy.objects.filter(
        space__in=spaces,
        starts_at__lt=window_end,
        ends_at__gt=window_start,
    ).only("space_id", "starts_at", "ends_at")
    for occupancy in occupancies:
        # Clip to the window so a long-running block does not inflate the week.
        start = max(occupancy.starts_at, window_start)
        end = min(occupancy.ends_at, window_end)
        if end > start:
            booked[occupancy.space_id] += int((end - start).total_seconds() // 60)

    # Two offices can name a room the same thing, and until the office chain
    # existed sharing one room between offices *required* entering it twice —
    # so a brokerage that worked around the old scope rule has duplicates by
    # construction. A bare name would print the same row twice with different
    # figures, so a colliding name carries its office.
    name_counts = Counter(space.name for space in spaces)

    def label_for(space: Space) -> str:
        if name_counts[space.name] > 1:
            return f"{space.name} · {space.owner_office.name}"
        return space.name

    series = []
    measured_open = 0
    measured_booked = 0
    # Busiest first: the row worth acting on is the room that is running out.
    ranked = sorted(
        spaces,
        key=lambda space: (
            -(
                booked[space.pk]
                / max(sum(_open_minutes(space, day) for day in days), 1)
            ),
            space.name,
        ),
    )
    for space in ranked[:4]:
        open_minutes = sum(_open_minutes(space, day) for day in days)
        used = booked[space.pk]
        if open_minutes == 0:
            series.append(
                {
                    "label": label_for(space),
                    "ratio": None,
                    "caption": "No published hours this week",
                }
            )
            continue
        measured_open += open_minutes
        measured_booked += min(used, open_minutes)
        series.append(
            {
                "label": label_for(space),
                "ratio": round(min(used / open_minutes, 1.0), 3),
                "caption": f"{used // 60}h booked of {open_minutes // 60}h open",
            }
        )

    if measured_open == 0:
        return empty(
            "No published hours",
            "Utilization needs at least one room with weekly opening hours.",
            action_label="Open room administration",
            action_href=reverse("space_administration"),
        )

    overall = measured_booked / measured_open
    return ready(
        {
            "headline": f"{round(overall * 100)}% booked",
            "caption": (
                f"Next {_WINDOW_DAYS} days across "
                f"{len(by_space)} reservable room{'' if len(by_space) == 1 else 's'}"
            ),
            "series": series,
        }
    )
