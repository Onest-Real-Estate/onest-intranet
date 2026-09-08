"""Bounded, privacy-safe room availability projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch, Q
from django.urls import reverse
from django.utils import timezone

from apps.reservations.availability import AvailabilityWindow, resolve_wall_time
from apps.reservations.booking import ReservationConflict, validate_reservation_interval
from apps.reservations.models import Amenity, Occupancy, Space, WeeklyAvailability
from apps.reservations.taxonomy import (
    CalendarView,
    ExceptionVisibility,
    OccupancySource,
    ReservationPermission,
    SpacePermission,
    SpaceType,
    WallTimeBoundary,
)
from apps.user.models import Office, User
from apps.user.services.role_assignments import get_effective_access
from apps.web.authorization import scope_queryset_for_offices
from apps.web.capability import evaluate_permission, has_capability

MAX_CALENDAR_DAYS = 7
MAX_CALENDAR_LOOKAHEAD_DAYS = 366
MAX_CALENDAR_SPACES = 50
SLOT_INCREMENT_MINUTES = 15


@dataclass(frozen=True)
class CalendarFilters:
    view: CalendarView
    start_date: date
    office_key: str = ""
    space_type: str = ""
    minimum_capacity: int | None = None
    amenity_codes: tuple[str, ...] = ()
    space_public_id: UUID | None = None


def _window_payload(window: AvailabilityWindow) -> dict[str, str]:
    return {
        "startsAt": window.starts_at.isoformat(),
        "endsAt": window.ends_at.isoformat(),
    }


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


def _schedule_windows(space: Space, local_date: date) -> list[AvailabilityWindow]:
    zone = ZoneInfo(space.owner_office.timezone)
    intervals = [
        interval
        for interval in space.weekly_availability.all()
        if interval.weekday == local_date.weekday()
    ]
    windows: list[AvailabilityWindow] = []
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


def _day_bounds(local_date: date, zone: ZoneInfo) -> AvailabilityWindow:
    return AvailabilityWindow(
        resolve_wall_time(
            local_date, time.min, zone, boundary=WallTimeBoundary.START
        ).astimezone(UTC),
        resolve_wall_time(
            local_date + timedelta(days=1),
            time.min,
            zone,
            boundary=WallTimeBoundary.END,
        ).astimezone(UTC),
    )


def _ceil_slot(value: datetime) -> datetime:
    epoch_minutes = int(value.timestamp() // 60)
    remainder = epoch_minutes % SLOT_INCREMENT_MINUTES
    if remainder:
        epoch_minutes += SLOT_INCREMENT_MINUTES - remainder
    return datetime.fromtimestamp(epoch_minutes * 60, tz=UTC)


def _candidate_slots(
    *,
    space: Space,
    schedule: list[AvailabilityWindow],
    busy: list[AvailabilityWindow],
    now: datetime,
) -> list[dict[str, str]]:
    slots: list[dict[str, str]] = []
    schedule_pairs = [(window.starts_at, window.ends_at) for window in schedule]
    busy_pairs = [(window.starts_at, window.ends_at) for window in busy]
    duration = timedelta(minutes=space.minimum_duration_minutes)
    for window in schedule:
        cursor = _ceil_slot(window.starts_at)
        while cursor + duration <= window.ends_at:
            ends_at = cursor + duration
            try:
                validate_reservation_interval(
                    space=space,
                    starts_at=cursor,
                    ends_at=ends_at,
                    now=now,
                    schedule_windows=schedule_pairs,
                    busy_intervals=busy_pairs,
                )
            except (ValidationError, ReservationConflict):
                cursor += timedelta(minutes=SLOT_INCREMENT_MINUTES)
                continue
            query = urlencode(
                {
                    "space": str(space.public_id),
                    "startsAt": cursor.isoformat(),
                    "endsAt": ends_at.isoformat(),
                }
            )
            slots.append(
                {
                    "startsAt": cursor.isoformat(),
                    "endsAt": ends_at.isoformat(),
                    "bookingHref": f"{reverse('room_reservation_new')}?{query}",
                }
            )
            cursor += timedelta(minutes=SLOT_INCREMENT_MINUTES)
    return slots


def _office_options(user: User, *, access) -> list[Office]:
    queryset = Office.objects.filter(is_active=True, is_assignable=True).select_related(
        "region"
    )
    scoped = (
        scope_queryset_for_offices(user, queryset)
        if has_capability(user, SpacePermission.VIEW, access=access)
        else queryset.none()
    )
    own_office_id = getattr(user, "office_id", None)
    if own_office_id:
        scoped = queryset.filter(Q(pk=own_office_id) | Q(pk__in=scoped.values("pk")))
    return list(scoped.order_by("region__name", "name", "pk"))


def _selected_office(
    user: User, *, filters: CalendarFilters, access
) -> tuple[Office | None, list[Office]]:
    options = _office_options(user, access=access)
    if not options:
        return None, []
    requested = filters.office_key.strip()
    if not requested:
        own_id = getattr(user, "office_id", None)
        return next(
            (office for office in options if office.pk == own_id), options[0]
        ), options
    selected = next(
        (office for office in options if office.stable_key == requested), None
    )
    if selected is None:
        raise PermissionDenied
    return selected, options


def _date_range(filters: CalendarFilters, *, today: date) -> list[date]:
    if filters.start_date < today:
        raise ValidationError({"date": ["Availability starts today or later."]})
    if filters.start_date > today + timedelta(days=MAX_CALENDAR_LOOKAHEAD_DAYS):
        raise ValidationError(
            {"date": ["Availability can be viewed up to one year ahead."]}
        )
    count = 1 if filters.view == CalendarView.DAY else MAX_CALENDAR_DAYS
    return [filters.start_date + timedelta(days=offset) for offset in range(count)]


def _space_queryset(office: Office, filters: CalendarFilters):
    queryset = (
        Space.objects.for_agent_office(office)
        .select_related("owner_office", "owner_office__region")
        .prefetch_related(
            Prefetch(
                "weekly_availability",
                queryset=WeeklyAvailability.objects.order_by(
                    "weekday", "starts_at", "pk"
                ),
            ),
            Prefetch(
                "amenities",
                queryset=Amenity.objects.filter(is_active=True).order_by(
                    "display_order", "name", "pk"
                ),
            ),
        )
    )
    if filters.space_type:
        queryset = queryset.filter(space_type=filters.space_type)
    if filters.minimum_capacity is not None:
        queryset = queryset.filter(capacity__gte=filters.minimum_capacity)
    if filters.space_public_id is not None:
        queryset = queryset.filter(public_id=filters.space_public_id)
    for code in filters.amenity_codes:
        queryset = queryset.filter(amenities__code=code)
    return queryset.distinct().order_by("display_order", "name", "pk")


def _busy_payload(occupancy: Occupancy, *, user: User, sensitive: bool) -> dict:
    label = "Busy"
    kind = "busy"
    mine = False
    if occupancy.source == OccupancySource.EXCEPTION:
        exception = occupancy.exception_record
        kind = exception.kind
        if exception.visibility == ExceptionVisibility.PUBLIC or sensitive:
            label = exception.reason
        else:
            label = "Unavailable"
    else:
        reservation = occupancy.reservation_record
        mine = reservation.owner_id == user.pk
        label = "Your reservation" if mine else "Busy"
    return {
        "startsAt": occupancy.starts_at.isoformat(),
        "endsAt": occupancy.ends_at.isoformat(),
        "kind": kind,
        "label": label,
        "isMine": mine,
    }


def build_calendar(*, user: User, filters: CalendarFilters, now=None) -> dict:
    """Return a bounded calendar whose private reservations are coarse busy rows."""
    current = now or timezone.now()
    access = get_effective_access(user)
    office, office_options = _selected_office(user, filters=filters, access=access)
    if office is None:
        return {
            "calendar": None,
            "office": None,
            "officeOptions": [],
            "filterOptions": {
                "spaceTypes": [],
                "amenities": [],
                "rooms": [],
            },
            "empty": {
                "kind": "no-office",
                "title": "No office assigned",
                "description": "Add an office to your profile before reserving a room.",
            },
            "capabilities": {"canBook": False, "canChangeOffice": False},
        }
    if (
        office.pk != getattr(user, "office_id", None)
        and not evaluate_permission(
            user, SpacePermission.VIEW, office=office, access=access
        ).allowed
    ):
        raise PermissionDenied
    days = _date_range(
        filters, today=current.astimezone(ZoneInfo(office.timezone)).date()
    )
    room_options = list(
        Space.objects.for_agent_office(office)
        .order_by("display_order", "name", "pk")
        .values("public_id", "name")
    )
    spaces = list(_space_queryset(office, filters)[: MAX_CALENDAR_SPACES + 1])
    truncated = len(spaces) > MAX_CALENDAR_SPACES
    spaces = spaces[:MAX_CALENDAR_SPACES]

    if spaces:
        zone = ZoneInfo(office.timezone)
        range_start = resolve_wall_time(
            days[0], time.min, zone, boundary=WallTimeBoundary.START
        ).astimezone(UTC)
        range_end = resolve_wall_time(
            days[-1] + timedelta(days=1),
            time.min,
            zone,
            boundary=WallTimeBoundary.END,
        ).astimezone(UTC)
        occupancies = list(
            Occupancy.objects.consuming()
            .filter(
                space_id__in=[space.pk for space in spaces],
                starts_at__lt=range_end,
                ends_at__gt=range_start,
            )
            .select_related(
                "reservation_record", "reservation_record__owner", "exception_record"
            )
            .order_by("starts_at", "ends_at", "pk")
        )
    else:
        occupancies = []
    by_space: dict[int, list[Occupancy]] = {}
    for occupancy in occupancies:
        by_space.setdefault(occupancy.space_id, []).append(occupancy)

    sensitive = evaluate_permission(
        user, SpacePermission.VIEW_SENSITIVE, office=office, access=access
    ).allowed
    rows = []
    for space in spaces:
        space_days = []
        for local_date in days:
            schedule = _schedule_windows(space, local_date)
            local_day = _day_bounds(local_date, ZoneInfo(office.timezone))
            relevant = [
                occupancy
                for occupancy in by_space.get(space.pk, [])
                if occupancy.starts_at < local_day.ends_at
                and occupancy.ends_at > local_day.starts_at
            ]
            busy = [
                AvailabilityWindow(occupancy.starts_at, occupancy.ends_at)
                for occupancy in relevant
            ]
            available = list(schedule)
            for block in busy:
                available = [
                    piece for window in available for piece in _subtract(window, block)
                ]
            space_days.append(
                {
                    "date": local_date.isoformat(),
                    "isClosed": not schedule,
                    "openIntervals": [_window_payload(window) for window in schedule],
                    "busyIntervals": [
                        _busy_payload(item, user=user, sensitive=sensitive)
                        for item in relevant
                    ],
                    "availableIntervals": [
                        _window_payload(window) for window in available
                    ],
                    "candidateSlots": _candidate_slots(
                        space=space,
                        schedule=schedule,
                        busy=busy,
                        now=current,
                    ),
                }
            )
        rows.append(
            {
                "publicId": str(space.public_id),
                "name": space.name,
                "type": space.space_type,
                "typeLabel": space.get_space_type_display(),
                "capacity": space.capacity,
                "location": space.location,
                "amenities": [
                    {"code": amenity.code, "name": amenity.name}
                    for amenity in space.amenities.all()
                ],
                "rules": {
                    "minimumDurationMinutes": space.minimum_duration_minutes,
                    "maximumDurationMinutes": space.maximum_duration_minutes,
                    "minimumNoticeMinutes": space.minimum_notice_minutes,
                    "bookingHorizonDays": space.booking_horizon_days,
                    "bufferBeforeMinutes": space.buffer_before_minutes,
                    "bufferAfterMinutes": space.buffer_after_minutes,
                    "requiresApproval": space.requires_approval,
                },
                "days": space_days,
            }
        )

    return {
        "calendar": {
            "view": filters.view.value,
            "startDate": filters.start_date.isoformat(),
            "days": [{"date": item.isoformat()} for item in days],
            "spaces": rows,
            "generatedAt": current.isoformat(),
            "timezone": office.timezone,
            "isTruncated": truncated,
            "advisory": (
                "Availability is current as of the generated time. "
                "The server checks the slot again when you submit."
            ),
        },
        "office": {
            "key": office.stable_key,
            "name": office.name,
            "timezone": office.timezone,
        },
        "officeOptions": [
            {
                "key": option.stable_key,
                "name": option.name,
                "regionName": option.region_name(),
            }
            for option in office_options
        ],
        "filterOptions": {
            "spaceTypes": [
                {"value": value, "label": label} for value, label in SpaceType.choices
            ],
            "amenities": [
                {"value": amenity.code, "label": amenity.name}
                for amenity in Amenity.objects.filter(is_active=True).order_by(
                    "display_order", "name", "pk"
                )
            ],
            "rooms": [
                {"value": str(item["public_id"]), "label": item["name"]}
                for item in room_options
            ],
        },
        "empty": (
            {
                "kind": "no-results",
                "title": "No rooms match these filters",
                "description": "Clear a filter or choose another date.",
            }
            if not rows
            else None
        ),
        "capabilities": {
            "canBook": evaluate_permission(
                user, ReservationPermission.BOOK, office=office, access=access
            ).allowed,
            "canChangeOffice": len(office_options) > 1,
        },
    }
