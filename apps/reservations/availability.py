from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from apps.reservations.models import Space, SpaceAvailabilityException
from apps.reservations.taxonomy import WallTimeBoundary


@dataclass(frozen=True, order=True)
class AvailabilityWindow:
    """Half-open UTC interval: ``starts_at`` is included, ``ends_at`` is not."""

    starts_at: datetime
    ends_at: datetime


def _valid_wall_time_candidates(value: datetime, zone: ZoneInfo) -> list[datetime]:
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        aware = value.replace(tzinfo=zone, fold=fold)
        utc_value = aware.astimezone(UTC)
        round_trip = utc_value.astimezone(zone)
        if round_trip.replace(tzinfo=None) == value:
            candidates[utc_value] = aware
    return [candidates[key] for key in sorted(candidates)]


def resolve_wall_time(
    local_date: date,
    local_time: time,
    zone: ZoneInfo,
    *,
    boundary: WallTimeBoundary,
) -> datetime:
    """Resolve an office wall time with an explicit DST policy.

    Nonexistent spring-forward values advance minute-by-minute to the first
    valid wall time. Ambiguous fall-back starts choose the earlier instant and
    ends choose the later instant, preserving the whole advertised interval.
    """
    if boundary not in WallTimeBoundary:
        raise ValueError("boundary must be a WallTimeBoundary value")
    value = datetime.combine(local_date, local_time)
    candidates = _valid_wall_time_candidates(value, zone)
    for _ in range(180):
        if candidates:
            return (
                candidates[0] if boundary == WallTimeBoundary.START else candidates[-1]
            )
        value += timedelta(minutes=1)
        candidates = _valid_wall_time_candidates(value, zone)
    raise ValueError("Unable to resolve office wall time within the DST gap limit.")


def scheduled_windows_for_date(
    space: Space, local_date: date
) -> list[AvailabilityWindow]:
    if not space.is_reservable:
        return []
    zone = ZoneInfo(space.owner_office.timezone)
    windows: list[AvailabilityWindow] = []
    intervals = space.weekly_availability.filter(weekday=local_date.weekday())
    for interval in intervals:
        starts_at = resolve_wall_time(
            local_date,
            interval.starts_at,
            zone,
            boundary=WallTimeBoundary.START,
        ).astimezone(UTC)
        ends_at = resolve_wall_time(
            local_date,
            interval.ends_at,
            zone,
            boundary=WallTimeBoundary.END,
        ).astimezone(UTC)
        if starts_at < ends_at:
            windows.append(AvailabilityWindow(starts_at, ends_at))
    return windows


def _subtract(
    window: AvailabilityWindow, block: AvailabilityWindow
) -> list[AvailabilityWindow]:
    if block.ends_at <= window.starts_at or block.starts_at >= window.ends_at:
        return [window]
    pieces: list[AvailabilityWindow] = []
    if block.starts_at > window.starts_at:
        pieces.append(AvailabilityWindow(window.starts_at, block.starts_at))
    if block.ends_at < window.ends_at:
        pieces.append(AvailabilityWindow(block.ends_at, window.ends_at))
    return pieces


def availability_windows_for_date(
    space: Space, local_date: date
) -> list[AvailabilityWindow]:
    """Resolve weekly availability minus every overlapping exception/block."""
    windows = scheduled_windows_for_date(space, local_date)
    if not windows:
        return []
    range_start = min(window.starts_at for window in windows)
    range_end = max(window.ends_at for window in windows)
    exceptions = SpaceAvailabilityException.objects.filter(
        space=space,
        starts_at__lt=range_end,
        ends_at__gt=range_start,
    ).order_by("starts_at", "ends_at", "pk")
    for exception in exceptions:
        block = AvailabilityWindow(exception.starts_at, exception.ends_at)
        windows = [piece for window in windows for piece in _subtract(window, block)]
    return sorted(windows)
