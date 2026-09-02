"""Live session schedule, registration, and attendance correction."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.audit.service import (
    actor_from_user,
    log_on_commit,
    snapshot_model,
    target_from_instance,
)
from apps.training.administration import assert_can_author
from apps.training.audience import assert_visible, targetable_user_queryset
from apps.training.models import (
    TrainingContent,
    TrainingLiveSession,
    TrainingSessionRegistration,
)
from apps.training.progress_service import mark_started
from apps.training.taxonomy import (
    CONTENT_TYPE_LIVE_SESSION,
    PROGRESS_SOURCE_ADMIN,
    PROGRESS_SOURCE_SESSION,
    SESSION_REGISTRATION_STATUS_CODES,
)
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

MANAGE_PERMISSION = "web.manage_training"
Status = TrainingSessionRegistration.Status


class SessionError(ValidationError):
    """Domain validation for live-session mutations."""


def get_session(content: TrainingContent) -> TrainingLiveSession | None:
    return TrainingLiveSession.objects.filter(content=content).first()


def session_is_configured(content: TrainingContent) -> bool:
    return TrainingLiveSession.objects.filter(content=content).exists()


def _active_registration_count(content: TrainingContent) -> int:
    return TrainingSessionRegistration.objects.filter(
        content=content,
        status__in={Status.REGISTERED, Status.ATTENDED},
    ).count()


def _within_registration_window(session: TrainingLiveSession, *, now) -> bool:
    if session.registration_opens_at and now < session.registration_opens_at:
        return False
    return not (session.registration_closes_at and now > session.registration_closes_at)


def session_payload(content: TrainingContent, user: User) -> dict[str, Any] | None:
    session = get_session(content)
    if session is None:
        return None
    registration = TrainingSessionRegistration.objects.filter(
        user=user, content=content
    ).first()
    seats_taken = _active_registration_count(content)
    seats_remaining = None
    if session.capacity is not None:
        seats_remaining = max(0, session.capacity - seats_taken)
    return {
        "startsAt": session.starts_at.isoformat(),
        "timezone": session.timezone,
        "durationMinutes": session.duration_minutes,
        "capacity": session.capacity,
        "seatsTaken": seats_taken,
        "seatsRemaining": seats_remaining,
        "meetingUrl": session.meeting_url,
        "registrationOpensAt": (
            session.registration_opens_at.isoformat()
            if session.registration_opens_at
            else None
        ),
        "registrationClosesAt": (
            session.registration_closes_at.isoformat()
            if session.registration_closes_at
            else None
        ),
        "registration": (
            {
                "status": registration.status,
                "registeredAt": registration.registered_at.isoformat(),
                "cancelledAt": (
                    registration.cancelled_at.isoformat()
                    if registration.cancelled_at
                    else None
                ),
                "attendedAt": (
                    registration.attended_at.isoformat()
                    if registration.attended_at
                    else None
                ),
            }
            if registration
            else None
        ),
    }


@transaction.atomic
def register(user: User, content: TrainingContent) -> TrainingSessionRegistration:
    assert_visible(user, content, reason="session_out_of_audience")
    if content.content_type != CONTENT_TYPE_LIVE_SESSION:
        raise SessionError({"content": ["This item is not a live session."]})
    session = (
        TrainingLiveSession.objects.select_for_update(of=("self",))
        .filter(content=content)
        .first()
    )
    if session is None:
        raise SessionError({"session": ["This session is not configured yet."]})

    now = timezone.now()
    if not _within_registration_window(session, now=now):
        raise SessionError({"registration": ["Registration is closed."]})

    locked = (
        TrainingSessionRegistration.objects.select_for_update(of=("self",))
        .filter(user=user, content=content)
        .first()
    )
    if locked is not None and locked.status in {Status.REGISTERED, Status.ATTENDED}:
        return locked

    if session.capacity is not None:
        taken = _active_registration_count(content)
        if taken >= session.capacity:
            raise SessionError({"capacity": ["This session is full."]})

    if locked is None:
        locked = TrainingSessionRegistration(
            user=user,
            content=content,
            status=Status.REGISTERED,
        )
        locked.save()
    else:
        locked.status = Status.REGISTERED
        locked.cancelled_at = None
        locked.save(update_fields=["status", "cancelled_at", "updated_at"])

    mark_started(
        user,
        content,
        source=PROGRESS_SOURCE_SESSION,
        evidence={"registrationId": locked.pk},
    )
    return locked


@transaction.atomic
def cancel_registration(
    user: User, content: TrainingContent
) -> TrainingSessionRegistration:
    assert_visible(user, content, reason="session_out_of_audience")
    locked = (
        TrainingSessionRegistration.objects.select_for_update(of=("self",))
        .filter(user=user, content=content)
        .first()
    )
    if locked is None:
        raise SessionError({"registration": ["You are not registered."]})
    if locked.status == Status.CANCELLED:
        return locked
    if locked.status == Status.ATTENDED:
        raise SessionError({"registration": ["Attendance has already been recorded."]})
    locked.status = Status.CANCELLED
    locked.cancelled_at = timezone.now()
    locked.save(update_fields=["status", "cancelled_at", "updated_at"])
    return locked


@transaction.atomic
def correct_attendance(
    *,
    actor: User,
    learner: User,
    content: TrainingContent,
    status: str,
    reason: str,
) -> TrainingSessionRegistration:
    reason_text = (reason or "").strip()
    if not reason_text:
        raise SessionError(
            {"reason": ["Explain the correction so the audit trail is useful."]}
        )
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        raise PermissionDenied("You cannot correct attendance.")
    assert_can_author(actor, content.owner_office)
    if not targetable_user_queryset(actor).filter(pk=learner.pk).exists():
        raise PermissionDenied("That learner is outside your training scope.")

    normalized = (status or "").strip()
    if normalized not in SESSION_REGISTRATION_STATUS_CODES:
        raise SessionError({"status": ["Unknown attendance status."]})

    locked = (
        TrainingSessionRegistration.objects.select_for_update(of=("self",))
        .filter(user=learner, content=content)
        .first()
    )
    if locked is None:
        locked = TrainingSessionRegistration(
            user=learner,
            content=content,
            status=normalized,
        )
        locked.save()
        locked = (
            TrainingSessionRegistration.objects.select_for_update(of=("self",))
            .filter(pk=locked.pk)
            .get()
        )

    if locked.status == normalized:
        return locked

    before = snapshot_model(locked, fields=["status", "attended_at", "cancelled_at"])
    now = timezone.now()
    locked.status = normalized
    updates = ["status", "updated_at"]
    if normalized == Status.ATTENDED:
        locked.attended_at = now
        updates.append("attended_at")
    elif normalized == Status.CANCELLED:
        locked.cancelled_at = now
        updates.append("cancelled_at")
    elif normalized == Status.NO_SHOW:
        locked.attended_at = None
        updates.append("attended_at")
    locked.save(update_fields=updates)
    after = snapshot_model(locked, fields=["status", "attended_at", "cancelled_at"])

    if normalized == Status.ATTENDED:
        from apps.training.progress_service import touch_progress

        touch_progress(
            learner,
            content,
            status="completed",
            source=PROGRESS_SOURCE_ADMIN,
            evidence={
                "registrationId": locked.pk,
                "reason": reason_text,
                "corrected_by": actor.pk,
            },
            actor=actor,
            reason=reason_text,
        )

    log_on_commit(
        "training.attendance_corrected",
        actor=actor_from_user(actor),
        target=target_from_instance(locked, label=content.title),
        before=before,
        after=after,
        metadata={
            "learner_id": learner.pk,
            "content_id": content.pk,
            "status": normalized,
            "reason": reason_text[:500],
        },
    )
    return locked


@transaction.atomic
def save_session_definition(
    *,
    actor: User,
    content: TrainingContent,
    starts_at,
    timezone_name: str,
    duration_minutes: int,
    capacity: int | None,
    meeting_url: str,
    registration_opens_at,
    registration_closes_at,
) -> TrainingLiveSession:
    assert_can_author(actor, content.owner_office)
    if content.status != TrainingContent.Status.DRAFT:
        raise SessionError({"content": ["Session schedule can only change on drafts."]})
    if content.content_type != CONTENT_TYPE_LIVE_SESSION:
        raise SessionError({"content": ["This item is not a live session."]})
    if isinstance(starts_at, str):
        starts_at = parse_datetime(starts_at)
    if starts_at is None:
        raise SessionError({"starts_at": ["Provide a valid start time."]})
    if not timezone.is_aware(starts_at):
        starts_at = timezone.make_aware(starts_at, timezone.get_current_timezone())
    if duration_minutes < 1:
        raise SessionError({"duration_minutes": ["Duration must be at least 1."]})
    if capacity is not None and capacity < 1:
        raise SessionError({"capacity": ["Capacity must be at least 1."]})
    tz_name = (timezone_name or "").strip() or "America/New_York"

    opens = registration_opens_at
    closes = registration_closes_at
    if isinstance(opens, str):
        opens = parse_datetime(opens)
    if isinstance(closes, str):
        closes = parse_datetime(closes)

    session, _ = TrainingLiveSession.objects.update_or_create(
        content=content,
        defaults={
            "starts_at": starts_at,
            "timezone": tz_name[:64],
            "duration_minutes": duration_minutes,
            "capacity": capacity,
            "meeting_url": (meeting_url or "").strip()[:500],
            "registration_opens_at": opens,
            "registration_closes_at": closes,
        },
    )
    return session


def admin_session_payload(content: TrainingContent) -> dict[str, Any] | None:
    session = get_session(content)
    if session is None:
        return None
    return {
        "startsAt": session.starts_at.isoformat(),
        "timezone": session.timezone,
        "durationMinutes": session.duration_minutes,
        "capacity": session.capacity,
        "meetingUrl": session.meeting_url,
        "registrationOpensAt": (
            session.registration_opens_at.isoformat()
            if session.registration_opens_at
            else None
        ),
        "registrationClosesAt": (
            session.registration_closes_at.isoformat()
            if session.registration_closes_at
            else None
        ),
        "seatsTaken": _active_registration_count(content),
    }
