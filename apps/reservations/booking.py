"""Authoritative room reservation validation and lifecycle services."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.audit.service import AuditTarget, actor_from_user, log_on_commit
from apps.reservations.availability import scheduled_windows_for_date
from apps.reservations.models import Occupancy, Reservation, Space
from apps.reservations.taxonomy import (
    OccupancySource,
    ReservationPermission,
    ReservationStatus,
    SpaceStatus,
)
from apps.user.models import User
from apps.web.capability import evaluate_permission, require_permission

CAPACITY_STATUSES = frozenset(
    {ReservationStatus.REQUESTED, ReservationStatus.CONFIRMED}
)

# PostgreSQL ``deadlock_detected``; see ``_save_occupancy``.
DEADLOCK_DETECTED = "40P01"


class ReservationConflict(ValidationError):
    """The requested capacity interval became unavailable."""


def occupied_interval(
    space: Space, starts_at: datetime, ends_at: datetime
) -> tuple[datetime, datetime]:
    return (
        starts_at - timedelta(minutes=space.buffer_before_minutes),
        ends_at + timedelta(minutes=space.buffer_after_minutes),
    )


def _covered_by_schedule(space: Space, starts_at: datetime, ends_at: datetime) -> bool:
    zone = ZoneInfo(space.owner_office.timezone)
    first_day = starts_at.astimezone(zone).date()
    final_probe = (ends_at - timedelta(microseconds=1)).astimezone(zone).date()
    if first_day != final_probe:
        return False
    return any(
        window.starts_at <= starts_at and window.ends_at >= ends_at
        for window in scheduled_windows_for_date(space, first_day)
    )


def validate_reservation_interval(
    *,
    space: Space,
    starts_at: datetime,
    ends_at: datetime,
    attendee_count: int | None = None,
    now: datetime | None = None,
    exclude_occupancy_id: int | None = None,
    schedule_windows: list[tuple[datetime, datetime]] | None = None,
    busy_intervals: list[tuple[datetime, datetime]] | None = None,
) -> tuple[datetime, datetime]:
    """Validate booking rules and return its buffered capacity interval.

    This is shared by calendar slot generation and every mutation path. The
    caller must still persist through the transaction service: this check is
    friendly and advisory until PostgreSQL accepts the occupancy row.
    """
    errors: dict[str, list[str]] = {}
    if not timezone.is_aware(starts_at):
        errors["starts_at"] = ["Start time must include a timezone."]
    if not timezone.is_aware(ends_at):
        errors["ends_at"] = ["End time must include a timezone."]
    if errors:
        raise ValidationError(errors)
    if ends_at <= starts_at:
        raise ValidationError({"ends_at": ["End time must be after start time."]})
    if space.status != SpaceStatus.ACTIVE or not space.is_reservable:
        raise ValidationError({"space": ["This space is not reservable."]})

    duration = int((ends_at - starts_at).total_seconds() // 60)
    if duration < space.minimum_duration_minutes:
        errors["ends_at"] = [
            f"Minimum reservation duration is {space.minimum_duration_minutes} minutes."
        ]
    if duration > space.maximum_duration_minutes:
        errors["ends_at"] = [
            f"Maximum reservation duration is {space.maximum_duration_minutes} minutes."
        ]
    if attendee_count is not None:
        if attendee_count < 1:
            errors["attendee_count"] = ["Attendee count must be positive."]
        elif attendee_count > space.capacity:
            errors["attendee_count"] = [
                f"This space holds at most {space.capacity} people."
            ]

    current = now or timezone.now()
    notice_at = current + timedelta(minutes=space.minimum_notice_minutes)
    horizon_at = current + timedelta(days=space.booking_horizon_days)
    if starts_at < notice_at:
        errors["starts_at"] = [
            f"This space requires {space.minimum_notice_minutes} minutes of notice."
        ]
    if starts_at > horizon_at:
        errors["starts_at"] = [
            f"This space can be booked up to {space.booking_horizon_days} days ahead."
        ]
    covered = (
        any(start <= starts_at and end >= ends_at for start, end in schedule_windows)
        if schedule_windows is not None
        else _covered_by_schedule(space, starts_at, ends_at)
    )
    if not covered:
        errors["starts_at"] = [
            "The full reservation must fit within one published office-hours interval."
        ]
    if errors:
        raise ValidationError(errors)

    occupied_start, occupied_end = occupied_interval(space, starts_at, ends_at)
    if busy_intervals is not None:
        has_overlap = any(
            busy_start < occupied_end and busy_end > occupied_start
            for busy_start, busy_end in busy_intervals
        )
    else:
        overlaps = Occupancy.objects.overlapping(
            space_id=space.pk,
            starts_at=occupied_start,
            ends_at=occupied_end,
        )
        if exclude_occupancy_id is not None:
            overlaps = overlaps.exclude(pk=exclude_occupancy_id)
        has_overlap = overlaps.exists()
    if has_overlap:
        raise ReservationConflict(
            {
                "form": [
                    "That time is no longer available. Refresh and choose another slot."
                ]
            }
        )
    return occupied_start, occupied_end


def _target(reservation: Reservation) -> AuditTarget:
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


def _is_deadlock(exc: OperationalError) -> bool:
    """True for PostgreSQL's ``deadlock_detected`` (SQLSTATE 40P01)."""
    return getattr(exc.__cause__, "sqlstate", None) == DEADLOCK_DETECTED


def _save_occupancy(occupancy: Occupancy) -> None:
    """Persist a capacity interval, mapping every lost race to one conflict.

    Two shapes of loss reach here. A writer that arrives after the winner
    committed gets ``IntegrityError`` from the exclusion constraint. Two writers
    that are already in flight — concurrent reschedules, which lock their own
    reservation rows rather than the shared space row — can instead wait on each
    other while PostgreSQL checks the constraint, and the loser is aborted with
    ``deadlock detected``. Both mean the same thing to a booker, so both become
    ``ReservationConflict`` and a 409 rather than a 500.
    """
    try:
        with transaction.atomic():
            occupancy.full_clean()
            occupancy.save()
    except IntegrityError as exc:
        raise ReservationConflict(
            {"form": ["That time was just taken. Refresh and choose another slot."]}
        ) from exc
    except OperationalError as exc:
        if not _is_deadlock(exc):
            raise
        raise ReservationConflict(
            {"form": ["That time was just taken. Refresh and choose another slot."]}
        ) from exc


@transaction.atomic
def create_reservation(
    *,
    actor: User,
    space: Space,
    starts_at: datetime,
    ends_at: datetime,
    purpose: str,
    submission_key: str,
    attendee_count: int | None = None,
    owner: User | None = None,
    override_reason: str = "",
    now: datetime | None = None,
) -> tuple[Reservation, bool]:
    owner = actor if owner is None else owner
    existing = Reservation.objects.filter(submission_key=submission_key).first()
    if existing is not None:
        if existing.owner_id != owner.pk:
            raise PermissionDenied
        return existing, False
    if not submission_key.strip() or len(submission_key) > 64:
        raise ValidationError(
            {"submission_key": ["A valid submission key is required."]}
        )

    locked_space = Space.objects.select_for_update(of=("self",)).get(pk=space.pk)
    existing = Reservation.objects.filter(submission_key=submission_key).first()
    if existing is not None:
        if existing.owner_id != owner.pk:
            raise PermissionDenied
        return existing, False
    require_permission(
        actor, ReservationPermission.BOOK, office=locked_space.owner_office
    )
    if owner.pk != actor.pk:
        require_permission(
            actor, ReservationPermission.MANAGE, office=locked_space.owner_office
        )
        if not override_reason.strip():
            raise ValidationError(
                {"override_reason": ["Creating on behalf requires a reason."]}
            )
    elif (
        getattr(actor, "office_id", None) != locked_space.owner_office_id
        and not evaluate_permission(
            actor, ReservationPermission.MANAGE, office=locked_space.owner_office
        ).allowed
    ):
        raise PermissionDenied

    purpose = purpose.strip()
    if not purpose:
        raise ValidationError({"purpose": ["A business purpose is required."]})
    occupied_start, occupied_end = validate_reservation_interval(
        space=locked_space,
        starts_at=starts_at,
        ends_at=ends_at,
        attendee_count=attendee_count,
        now=now,
    )
    occupancy = Occupancy(
        space=locked_space,
        starts_at=occupied_start,
        ends_at=occupied_end,
        source=OccupancySource.RESERVATION,
    )
    _save_occupancy(occupancy)

    created_at = now or timezone.now()
    status = (
        ReservationStatus.REQUESTED
        if locked_space.requires_approval
        else ReservationStatus.CONFIRMED
    )
    reservation = Reservation(
        reference=f"ROOM-{uuid4().hex[:10].upper()}",
        occupancy=occupancy,
        space=locked_space,
        owner=owner,
        office=locked_space.owner_office,
        office_name=locked_space.owner_office.name,
        space_name=locked_space.name,
        starts_at=starts_at,
        ends_at=ends_at,
        buffer_before_minutes=locked_space.buffer_before_minutes,
        buffer_after_minutes=locked_space.buffer_after_minutes,
        purpose=purpose,
        attendee_count=attendee_count,
        status=status,
        instructions_snapshot=locked_space.access_instructions,
        submission_key=submission_key.strip(),
        created_by=actor,
        approved_at=created_at if status == ReservationStatus.CONFIRMED else None,
        approved_by=actor if status == ReservationStatus.CONFIRMED else None,
    )
    reservation.full_clean()
    reservation.save()
    if locked_space.booking_history_started_at is None:
        locked_space.booking_history_started_at = created_at
        locked_space.save(update_fields=["booking_history_started_at", "updated_at"])
    log_on_commit(
        "reservations.booking.created",
        actor=actor_from_user(actor),
        target=_target(reservation),
        office_id=locked_space.owner_office.stable_key,
        after={"status": reservation.status},
        reason=override_reason,
    )
    return reservation, True


@transaction.atomic
def cancel_reservation(
    *, actor: User, reservation: Reservation, reason: str, override_reason: str = ""
) -> Reservation:
    locked = (
        Reservation.objects.select_for_update(of=("self", "occupancy"))
        .select_related("occupancy", "space", "office")
        .get(pk=reservation.pk)
    )
    is_owner = locked.owner_id == actor.pk
    if not is_owner:
        require_permission(actor, ReservationPermission.MANAGE, office=locked.office)
    if locked.status not in CAPACITY_STATUSES:
        raise ValidationError(
            {"form": ["This reservation can no longer be cancelled."]}
        )
    if not reason.strip():
        raise ValidationError({"reason": ["A cancellation reason is required."]})
    cutoff = locked.starts_at - timedelta(
        minutes=locked.space.cancellation_cutoff_minutes
    )
    if timezone.now() >= cutoff:
        if not evaluate_permission(
            actor, ReservationPermission.OVERRIDE, office=locked.office
        ).allowed:
            raise ValidationError({"form": ["The cancellation cutoff has passed."]})
        if not override_reason.strip():
            raise ValidationError(
                {"override_reason": ["An override reason is required."]}
            )
    before_status = locked.status
    locked.status = ReservationStatus.CANCELLED
    locked.cancelled_at = timezone.now()
    locked.cancelled_by = actor
    locked.cancel_reason = reason.strip()
    locked.full_clean()
    locked.save()
    locked.occupancy.consumes_capacity = False
    locked.occupancy.save(update_fields=["consumes_capacity"])
    log_on_commit(
        "reservations.booking.cancelled",
        actor=actor_from_user(actor),
        target=_target(locked),
        office_id=locked.office.stable_key,
        before={"status": before_status},
        after={"status": ReservationStatus.CANCELLED},
        reason=override_reason or reason,
    )
    return locked


@transaction.atomic
def reschedule_reservation(
    *,
    actor: User,
    reservation: Reservation,
    starts_at: datetime,
    ends_at: datetime,
    attendee_count: int | None = None,
    now: datetime | None = None,
) -> Reservation:
    locked = (
        Reservation.objects.select_for_update(of=("self", "occupancy"))
        .select_related("occupancy", "space", "office")
        .get(pk=reservation.pk)
    )
    if locked.owner_id != actor.pk:
        require_permission(actor, ReservationPermission.MANAGE, office=locked.office)
    if locked.status not in CAPACITY_STATUSES:
        raise ValidationError({"form": ["This reservation cannot be rescheduled."]})
    occupied_start, occupied_end = validate_reservation_interval(
        space=locked.space,
        starts_at=starts_at,
        ends_at=ends_at,
        attendee_count=attendee_count,
        now=now,
        exclude_occupancy_id=locked.occupancy_id,
    )
    before = {"startsAt": locked.starts_at, "endsAt": locked.ends_at}
    locked.occupancy.starts_at = occupied_start
    locked.occupancy.ends_at = occupied_end
    _save_occupancy(locked.occupancy)
    locked.starts_at = starts_at
    locked.ends_at = ends_at
    locked.attendee_count = attendee_count
    locked.full_clean()
    locked.save()
    log_on_commit(
        "reservations.booking.rescheduled",
        actor=actor_from_user(actor),
        target=_target(locked),
        office_id=locked.office.stable_key,
        before=before,
        after={"startsAt": starts_at, "endsAt": ends_at},
    )
    return locked


@transaction.atomic
def decide_reservation(
    *, actor: User, reservation: Reservation, approve: bool, reason: str = ""
) -> Reservation:
    locked = (
        Reservation.objects.select_for_update(of=("self", "occupancy"))
        .select_related("occupancy", "office", "space")
        .get(pk=reservation.pk)
    )
    require_permission(actor, ReservationPermission.MANAGE, office=locked.office)
    if locked.status != ReservationStatus.REQUESTED:
        raise ValidationError({"form": ["This reservation is no longer pending."]})
    if not approve and not reason.strip():
        raise ValidationError({"reason": ["A denial reason is required."]})
    before_status = locked.status
    if approve:
        locked.status = ReservationStatus.CONFIRMED
        locked.approved_at = timezone.now()
        locked.approved_by = actor
    else:
        locked.status = ReservationStatus.DENIED
        locked.occupancy.consumes_capacity = False
        locked.occupancy.save(update_fields=["consumes_capacity"])
    locked.full_clean()
    locked.save()
    log_on_commit(
        "reservations.booking.approved" if approve else "reservations.booking.denied",
        actor=actor_from_user(actor),
        target=_target(locked),
        office_id=locked.office.stable_key,
        before={"status": before_status},
        after={"status": locked.status},
        reason=reason,
    )
    return locked
