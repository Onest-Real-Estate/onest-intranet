"""Scoped administration operations for spaces, schedules, blocks, and bookings.

Everything here is a write path reached only by a scoped administrator. Three
rules hold throughout:

* **Scope is revalidated per action, per object.** A room, a target user, and a
  replacement room are each re-checked against the actor's effective hierarchy
  at the moment of the write. A payload that named an office is never trusted.
* **The database keeps the overlap invariant.** These services widen, move, and
  release capacity intervals, but the exclusion constraint in migration ``0003``
  is what makes each write race-proof; see ``docs/reservable-spaces.md``.
* **Changes that can invalidate a live booking must be seen first.** Schedule,
  policy, and lifecycle edits run through :func:`future_impact` and refuse to
  proceed silently when bookings would be stranded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.audit.service import (
    AuditTarget,
    actor_from_user,
    log_on_commit,
    snapshot_model,
)
from apps.reservations.availability import scheduled_windows_for_date
from apps.reservations.booking import (
    CAPACITY_STATUSES,
    ReservationConflict,
    occupied_interval,
)
from apps.reservations.models import (
    Occupancy,
    Reservation,
    Space,
    SpaceAvailabilityException,
    WeeklyAvailability,
)
from apps.reservations.taxonomy import (
    ReservationPermission,
    ReservationStatus,
    SpacePermission,
    SpaceStatus,
)
from apps.user.models import User
from apps.web.capability import require_permission

#: Policy fields an administrator may edit through the workspace. Anything not
#: listed here — identity, ownership, lifecycle timestamps — is changed only by
#: its own explicit operation, so a broad form post cannot reach it.
EDITABLE_SPACE_FIELDS = frozenset(
    {
        "name",
        "space_type",
        "capacity",
        "description",
        "location",
        "access_instructions",
        "is_reservable",
        "display_order",
        "minimum_duration_minutes",
        "maximum_duration_minutes",
        "booking_horizon_days",
        "minimum_notice_minutes",
        "buffer_before_minutes",
        "buffer_after_minutes",
        "requires_approval",
        "cancellation_cutoff_minutes",
        "recurrence_policy",
        "maximum_recurrence_occurrences",
    }
)

SPACE_AUDIT_FIELDS = [
    "public_id",
    "owner_office",
    "name",
    "space_type",
    "capacity",
    "status",
    "is_reservable",
    "retired_at",
]

#: Editing any of these can strand a booking that is already on the calendar,
#: so they require an impact acknowledgement. The rest are cosmetic.
IMPACTING_SPACE_FIELDS = frozenset(
    {
        "capacity",
        "is_reservable",
        "minimum_duration_minutes",
        "maximum_duration_minutes",
        "buffer_before_minutes",
        "buffer_after_minutes",
    }
)


class StaleEdit(ValidationError):
    """The record changed after the editor loaded it."""


@dataclass(frozen=True)
class ImpactedBooking:
    reference: str
    public_id: str
    owner_id: int
    owner_name: str
    starts_at: datetime
    ends_at: datetime
    reason: str


@dataclass(frozen=True)
class ImpactReport:
    """What a pending administrative change would do to live bookings."""

    total: int
    bookings: tuple[ImpactedBooking, ...]

    @property
    def is_empty(self) -> bool:
        return self.total == 0


def _snapshot(space: Space) -> dict:
    return snapshot_model(space, fields=SPACE_AUDIT_FIELDS)


def _space_target(space: Space) -> AuditTarget:
    return AuditTarget(
        target_type=space._meta.label_lower,
        target_id=str(space.public_id),
        target_label=space.name,
        target_snapshot=_snapshot(space),
    )


def _booking_target(reservation: Reservation) -> AuditTarget:
    return AuditTarget(
        target_type=reservation._meta.label_lower,
        target_id=str(reservation.public_id),
        target_label=reservation.reference,
        target_snapshot={
            "spaceId": str(reservation.space.public_id),
            "ownerId": reservation.owner_id,
            "officeId": reservation.office.stable_key,
            "startsAt": reservation.starts_at,
            "endsAt": reservation.ends_at,
            "status": reservation.status,
        },
    )


def future_bookings(space: Space, *, now: datetime | None = None) -> QuerySet:
    """Capacity-holding bookings that have not started yet, oldest first."""
    moment = now or timezone.now()
    return (
        Reservation.objects.filter(
            space=space,
            status__in=CAPACITY_STATUSES,
            starts_at__gte=moment,
        )
        .select_related("owner", "occupancy")
        .order_by("starts_at", "pk")
    )


def _impacted(
    reservation: Reservation, reason: str, *, limit_reason: str = ""
) -> ImpactedBooking:
    return ImpactedBooking(
        reference=reservation.reference,
        public_id=str(reservation.public_id),
        owner_id=reservation.owner_id,
        owner_name=reservation.owner.display_name or reservation.owner.email,
        starts_at=reservation.starts_at,
        ends_at=reservation.ends_at,
        reason=limit_reason or reason,
    )


def future_impact(
    space: Space,
    *,
    now: datetime | None = None,
    schedule: list[tuple[int, time, time]] | None = None,
    policy: dict[str, Any] | None = None,
    limit: int = 25,
) -> ImpactReport:
    """Report which live bookings a pending change would invalidate.

    With no ``schedule`` or ``policy`` this reports every future booking, which
    is what deactivation and retirement need. With either supplied it reports
    only the bookings that would *stop* being valid, so an ordinary edit does
    not alarm an administrator about bookings it leaves alone.
    """
    upcoming = list(future_bookings(space, now=now))
    if schedule is None and policy is None:
        return ImpactReport(
            total=len(upcoming),
            bookings=tuple(
                _impacted(item, "Loses its room") for item in upcoming[:limit]
            ),
        )

    probe = _probe_space(space, policy or {})
    stranded: list[ImpactedBooking] = []
    for reservation in upcoming:
        reason = _why_invalid(probe, reservation, schedule=schedule)
        if reason:
            stranded.append(_impacted(reservation, reason))
    return ImpactReport(total=len(stranded), bookings=tuple(stranded[:limit]))


def _probe_space(space: Space, policy: dict[str, Any]) -> Space:
    """A detached copy of ``space`` carrying the proposed policy values."""
    probe = Space(pk=space.pk)
    for field in space._meta.concrete_fields:
        setattr(probe, field.attname, getattr(space, field.attname))
    probe.owner_office = space.owner_office
    for key, value in policy.items():
        if key in EDITABLE_SPACE_FIELDS:
            setattr(probe, key, value)
    return probe


def _covered_by(
    windows: list[tuple[datetime, datetime]], starts_at: datetime, ends_at: datetime
) -> bool:
    return any(start <= starts_at and end >= ends_at for start, end in windows)


def _why_invalid(
    probe: Space,
    reservation: Reservation,
    *,
    schedule: list[tuple[int, time, time]] | None,
) -> str:
    duration = int((reservation.ends_at - reservation.starts_at).total_seconds() // 60)
    if duration < probe.minimum_duration_minutes:
        return "Shorter than the new minimum duration"
    if duration > probe.maximum_duration_minutes:
        return "Longer than the new maximum duration"
    if reservation.attendee_count and reservation.attendee_count > probe.capacity:
        return "More attendees than the new capacity"
    if not probe.is_reservable:
        return "The room would stop accepting bookings"
    if schedule is not None:
        windows = _windows_from_proposal(probe, schedule, reservation.starts_at)
        if not _covered_by(windows, reservation.starts_at, reservation.ends_at):
            return "Falls outside the new opening hours"
    return ""


def _windows_from_proposal(
    space: Space, schedule: list[tuple[int, time, time]], moment: datetime
) -> list[tuple[datetime, datetime]]:
    """Resolve the proposed weekly rules for the local date of ``moment``."""
    from zoneinfo import ZoneInfo

    from apps.reservations.availability import resolve_wall_time
    from apps.reservations.taxonomy import WallTimeBoundary

    zone = ZoneInfo(space.owner_office.timezone)
    local_date = moment.astimezone(zone).date()
    windows: list[tuple[datetime, datetime]] = []
    for weekday, starts_at, ends_at in schedule:
        if weekday != local_date.weekday():
            continue
        start = resolve_wall_time(
            local_date, starts_at, zone, boundary=WallTimeBoundary.START
        )
        end = resolve_wall_time(
            local_date, ends_at, zone, boundary=WallTimeBoundary.END
        )
        if start < end:
            windows.append((start, end))
    return windows


def _guard_no_protected_overlap(
    space: Space,
    starts_at: datetime,
    ends_at: datetime,
    *,
    exclude_occupancy_id: int | None = None,
    field: str = "form",
) -> None:
    """Refuse a write that would land on time another consumer already holds.

    The exclusion constraint is the race-proof authority, but it only exists on
    PostgreSQL and it speaks in ``IntegrityError``. This gives the administrator
    a specific, friendly refusal on every backend before the write is attempted.
    """
    clashing = Occupancy.objects.overlapping(
        space_id=space.pk, starts_at=starts_at, ends_at=ends_at
    )
    if exclude_occupancy_id is not None:
        clashing = clashing.exclude(pk=exclude_occupancy_id)
    if clashing.exists():
        raise ReservationConflict(
            {
                field: [
                    "That time is already held for this room. Move or cancel the "
                    "booking first, then try again."
                ]
            }
        )


def _lock_space(space: Space) -> Space:
    return Space.objects.select_for_update(of=("self",)).get(pk=space.pk)


def _guard_stale(space: Space, expected_updated_at: datetime | None) -> None:
    if expected_updated_at is None:
        return
    # Round-tripping through JSON can cost sub-microsecond precision, so compare
    # with a small tolerance rather than for equality. It must stay well under
    # the time between two deliberate edits, or a real clobber slips through.
    drift = abs((space.updated_at - expected_updated_at).total_seconds())
    if drift > 0.001:
        raise StaleEdit(
            {
                "form": [
                    "Someone else changed this room while you were editing. "
                    "Reload to see their version before saving."
                ]
            }
        )


@transaction.atomic
def update_space(
    *,
    actor: User,
    space: Space,
    expected_updated_at: datetime | None = None,
    acknowledge_impact: bool = False,
    now: datetime | None = None,
    **fields: Any,
) -> tuple[Space, ImpactReport]:
    """Edit identity and booking policy, refusing to strand live bookings."""
    locked = _lock_space(space)
    require_permission(actor, SpacePermission.MANAGE, office=locked.owner_office)
    _guard_stale(locked, expected_updated_at)

    unknown = set(fields) - EDITABLE_SPACE_FIELDS
    if unknown:
        raise ValidationError(
            {"form": [f"These fields cannot be edited here: {sorted(unknown)}."]}
        )

    report = ImpactReport(total=0, bookings=())
    if IMPACTING_SPACE_FIELDS.intersection(fields):
        report = future_impact(locked, policy=fields, now=now)
        if not report.is_empty and not acknowledge_impact:
            raise ImpactRequiresAcknowledgement(report)

    before = _snapshot(locked)
    for key, value in fields.items():
        setattr(locked, key, value)
    locked.updated_by = actor
    locked.full_clean()
    locked.save()
    log_on_commit(
        "reservations.space.updated",
        actor=actor_from_user(actor),
        target=_space_target(locked),
        before=before,
        after=_snapshot(locked),
        office_id=locked.owner_office.stable_key,
        metadata={"impactedBookings": report.total},
    )
    return locked, report


class ImpactRequiresAcknowledgement(ValidationError):
    """The change is legal but would strand bookings the actor has not seen."""

    def __init__(self, report: ImpactReport):
        self.report = report
        super().__init__(
            {
                "form": [
                    f"This change would invalidate {report.total} future "
                    "booking(s). Review them, then confirm."
                ]
            }
        )


@transaction.atomic
def set_space_activation(
    *,
    actor: User,
    space: Space,
    active: bool,
    reason: str = "",
    acknowledge_impact: bool = False,
    now: datetime | None = None,
) -> tuple[Space, ImpactReport]:
    """Activate or deactivate a space, surfacing the bookings it would strand."""
    locked = _lock_space(space)
    require_permission(actor, SpacePermission.MANAGE, office=locked.owner_office)
    if locked.status == SpaceStatus.RETIRED:
        raise ValidationError({"form": ["A retired space cannot be reactivated."]})

    report = ImpactReport(total=0, bookings=())
    if not active:
        if not reason.strip():
            raise ValidationError(
                {"reason": ["A reason is required to deactivate a room."]}
            )
        report = future_impact(locked, now=now)
        if not report.is_empty and not acknowledge_impact:
            raise ImpactRequiresAcknowledgement(report)

    before = _snapshot(locked)
    locked.status = SpaceStatus.ACTIVE if active else SpaceStatus.INACTIVE
    locked.is_reservable = active
    locked.updated_by = actor
    locked.full_clean()
    locked.save()
    log_on_commit(
        "reservations.space.activation_changed",
        actor=actor_from_user(actor),
        target=_space_target(locked),
        before=before,
        after=_snapshot(locked),
        office_id=locked.owner_office.stable_key,
        reason=reason,
        metadata={"active": active, "impactedBookings": report.total},
    )
    return locked, report


@transaction.atomic
def replace_weekly_schedule(
    *,
    actor: User,
    space: Space,
    intervals: list[tuple[int, time, time]],
    expected_updated_at: datetime | None = None,
    acknowledge_impact: bool = False,
    now: datetime | None = None,
) -> tuple[Space, ImpactReport]:
    """Replace a space's opening hours as one atomic set."""
    locked = _lock_space(space)
    require_permission(
        actor, SpacePermission.MANAGE_SCHEDULE, office=locked.owner_office
    )
    _guard_stale(locked, expected_updated_at)

    for weekday, starts_at, ends_at in intervals:
        if not 0 <= weekday <= 6:
            raise ValidationError({"schedule": ["Weekday must be 0 (Mon) to 6 (Sun)."]})
        if starts_at >= ends_at:
            raise ValidationError(
                {"schedule": ["Each interval must end after it starts."]}
            )
    _guard_overlapping_intervals(intervals)

    report = future_impact(locked, schedule=intervals, now=now)
    if not report.is_empty and not acknowledge_impact:
        raise ImpactRequiresAcknowledgement(report)

    before = {
        "intervals": [
            [item.weekday, item.starts_at.isoformat(), item.ends_at.isoformat()]
            for item in locked.weekly_availability.order_by("weekday", "starts_at")
        ]
    }
    locked.weekly_availability.all().delete()
    for weekday, starts_at, ends_at in intervals:
        interval = WeeklyAvailability(
            space=locked, weekday=weekday, starts_at=starts_at, ends_at=ends_at
        )
        interval.full_clean()
        interval.save()
    locked.updated_by = actor
    locked.save(update_fields=["updated_by", "updated_at"])
    log_on_commit(
        "reservations.space.schedule_replaced",
        actor=actor_from_user(actor),
        target=_space_target(locked),
        before=before,
        after={
            "intervals": [
                [weekday, starts_at.isoformat(), ends_at.isoformat()]
                for weekday, starts_at, ends_at in intervals
            ]
        },
        office_id=locked.owner_office.stable_key,
        metadata={"impactedBookings": report.total},
    )
    return locked, report


def _guard_overlapping_intervals(intervals: list[tuple[int, time, time]]) -> None:
    by_day: dict[int, list[tuple[time, time]]] = {}
    for weekday, starts_at, ends_at in intervals:
        by_day.setdefault(weekday, []).append((starts_at, ends_at))
    for weekday, spans in by_day.items():
        ordered = sorted(spans)
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if earlier[1] > later[0]:
                raise ValidationError(
                    {"schedule": [f"Overlapping intervals on weekday {weekday}."]}
                )


@transaction.atomic
def update_availability_exception(
    *,
    actor: User,
    exception: SpaceAvailabilityException,
    starts_at: datetime,
    ends_at: datetime,
    **fields: Any,
) -> SpaceAvailabilityException:
    """Move or relabel a block, keeping its ledger row in step and overlap-safe."""
    locked = _lock_space(exception.space)
    require_permission(
        actor, SpacePermission.MANAGE_SCHEDULE, office=locked.owner_office
    )
    if starts_at >= ends_at:
        raise ValidationError({"ends_at": ["End time must be after start time."]})
    _guard_no_protected_overlap(
        locked,
        starts_at,
        ends_at,
        exclude_occupancy_id=exception.occupancy_id,
        field="starts_at",
    )

    before = {
        "startsAt": exception.starts_at,
        "endsAt": exception.ends_at,
        "kind": exception.kind,
        "reason": exception.reason,
    }
    exception.starts_at = starts_at
    exception.ends_at = ends_at
    for key, value in fields.items():
        setattr(exception, key, value)
    exception.full_clean(exclude={"occupancy"})
    exception.save()
    log_on_commit(
        "reservations.space.availability_block_updated",
        actor=actor_from_user(actor),
        target=_space_target(locked),
        before=before,
        after={
            "startsAt": exception.starts_at,
            "endsAt": exception.ends_at,
            "kind": exception.kind,
            "reason": exception.reason,
        },
        office_id=locked.owner_office.stable_key,
        metadata={"exceptionId": str(exception.public_id)},
    )
    return exception


@transaction.atomic
def remove_availability_exception(
    *, actor: User, exception: SpaceAvailabilityException
) -> None:
    """Delete a block and release the capacity it held."""
    locked = _lock_space(exception.space)
    require_permission(
        actor, SpacePermission.MANAGE_SCHEDULE, office=locked.owner_office
    )
    occupancy_id = exception.occupancy_id
    payload = {
        "startsAt": exception.starts_at,
        "endsAt": exception.ends_at,
        "kind": exception.kind,
        "reason": exception.reason,
        "exceptionId": str(exception.public_id),
    }
    exception.delete()
    Occupancy.objects.filter(pk=occupancy_id).delete()
    log_on_commit(
        "reservations.space.availability_block_removed",
        actor=actor_from_user(actor),
        target=_space_target(locked),
        before=payload,
        office_id=locked.owner_office.stable_key,
    )


@transaction.atomic
def move_reservation(
    *,
    actor: User,
    reservation: Reservation,
    destination: Space,
    reason: str,
    now: datetime | None = None,
) -> Reservation:
    """Move a booking to another room the actor also administers.

    The destination is re-scoped here rather than trusted from the request, and
    the ledger row changes rooms inside the same transaction so the exclusion
    constraint judges the move against the destination's occupancy.
    """
    if not reason.strip():
        raise ValidationError({"reason": ["A reason is required to move a booking."]})

    locked = (
        Reservation.objects.select_for_update(of=("self", "occupancy"))
        .select_related("occupancy", "space", "office", "owner")
        .get(pk=reservation.pk)
    )
    require_permission(actor, ReservationPermission.MANAGE, office=locked.office)
    if locked.status not in CAPACITY_STATUSES:
        raise ValidationError({"form": ["This booking no longer holds a room."]})

    locked_destination = _lock_space(destination)
    # Scope is re-checked against the destination, not the source: moving into a
    # room the actor cannot administer would otherwise escape their hierarchy.
    require_permission(
        actor, SpacePermission.MANAGE, office=locked_destination.owner_office
    )
    if locked_destination.pk == locked.space_id:
        raise ValidationError({"destination": ["The booking is already in that room."]})
    if (
        locked_destination.status != SpaceStatus.ACTIVE
        or not locked_destination.is_reservable
    ):
        raise ValidationError({"destination": ["That room is not accepting bookings."]})
    if locked_destination.owner_office_id != locked.office_id:
        raise ValidationError(
            {"destination": ["A booking cannot move to another office."]}
        )
    if locked.attendee_count and locked.attendee_count > locked_destination.capacity:
        raise ValidationError(
            {"destination": ["That room is too small for this booking."]}
        )

    moment = now or timezone.now()
    windows = [
        (window.starts_at, window.ends_at)
        for window in scheduled_windows_for_date(
            locked_destination, _local_date(locked_destination, locked.starts_at)
        )
    ]
    if not _covered_by(windows, locked.starts_at, locked.ends_at):
        raise ValidationError(
            {"destination": ["That room is not open for this time range."]}
        )

    occupied_start, occupied_end = occupied_interval(
        locked_destination, locked.starts_at, locked.ends_at
    )
    _guard_no_protected_overlap(
        locked_destination,
        occupied_start,
        occupied_end,
        exclude_occupancy_id=locked.occupancy_id,
        field="destination",
    )
    before = {
        "spaceId": str(locked.space.public_id),
        "spaceName": locked.space_name,
    }
    occupancy = locked.occupancy
    occupancy.space = locked_destination
    occupancy.starts_at = occupied_start
    occupancy.ends_at = occupied_end
    _save_moved_occupancy(occupancy)

    locked.space = locked_destination
    locked.space_name = locked_destination.name
    locked.buffer_before_minutes = locked_destination.buffer_before_minutes
    locked.buffer_after_minutes = locked_destination.buffer_after_minutes
    locked.instructions_snapshot = locked_destination.access_instructions
    locked.full_clean()
    locked.save()
    log_on_commit(
        "reservations.booking.moved",
        actor=actor_from_user(actor),
        target=_booking_target(locked),
        before=before,
        after={
            "spaceId": str(locked_destination.public_id),
            "spaceName": locked_destination.name,
        },
        office_id=locked.office.stable_key,
        reason=reason,
        metadata={"ownerId": locked.owner_id, "movedAt": moment},
    )
    return locked


def _local_date(space: Space, moment: datetime):
    from zoneinfo import ZoneInfo

    return moment.astimezone(ZoneInfo(space.owner_office.timezone)).date()


def _save_moved_occupancy(occupancy: Occupancy) -> None:
    """Reuse the booking service's conflict mapping for the moved ledger row."""
    from apps.reservations.booking import _save_occupancy

    _save_occupancy(occupancy)


@transaction.atomic
def cancel_reservation_as_admin(
    *,
    actor: User,
    reservation: Reservation,
    reason: str,
    now: datetime | None = None,
) -> Reservation:
    """Cancel someone else's booking with an audited, notified reason."""
    if not reason.strip():
        raise ValidationError(
            {"reason": ["A reason is required to cancel someone else's booking."]}
        )
    locked = (
        Reservation.objects.select_for_update(of=("self", "occupancy"))
        .select_related("occupancy", "space", "office", "owner")
        .get(pk=reservation.pk)
    )
    require_permission(actor, ReservationPermission.MANAGE, office=locked.office)
    if locked.status not in CAPACITY_STATUSES:
        raise ValidationError({"form": ["This booking is already closed."]})

    before = {"status": locked.status}
    moment = now or timezone.now()
    locked.status = ReservationStatus.CANCELLED
    locked.cancelled_at = moment
    locked.cancelled_by = actor
    locked.full_clean()
    locked.save()
    locked.occupancy.consumes_capacity = False
    locked.occupancy.save(update_fields=["consumes_capacity"])
    log_on_commit(
        "reservations.booking.cancelled_by_admin",
        actor=actor_from_user(actor),
        target=_booking_target(locked),
        before=before,
        after={"status": locked.status},
        office_id=locked.office.stable_key,
        reason=reason,
        metadata={"ownerId": locked.owner_id},
    )
    return locked


__all__ = [
    "EDITABLE_SPACE_FIELDS",
    "ImpactReport",
    "ImpactRequiresAcknowledgement",
    "ImpactedBooking",
    "ReservationConflict",
    "StaleEdit",
    "cancel_reservation_as_admin",
    "future_bookings",
    "future_impact",
    "move_reservation",
    "remove_availability_exception",
    "replace_weekly_schedule",
    "set_space_activation",
    "update_availability_exception",
    "update_space",
]
