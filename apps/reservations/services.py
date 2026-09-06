from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.service import (
    AuditTarget,
    actor_from_user,
    log_on_commit,
    snapshot_model,
)
from apps.reservations.guards import allow_office_transfer
from apps.reservations.models import (
    Space,
    SpaceAvailabilityException,
    SpaceOfficeTransfer,
)
from apps.reservations.taxonomy import SpacePermission, SpaceStatus
from apps.user.models import Office, User
from apps.web.capability import require_permission

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


def _snapshot(space: Space) -> dict:
    return snapshot_model(space, fields=SPACE_AUDIT_FIELDS)


def _target(space: Space) -> AuditTarget:
    return AuditTarget(
        target_type=space._meta.label_lower,
        target_id=str(space.public_id),
        target_label=space.name,
        target_snapshot=_snapshot(space),
    )


def _require_assignable_office(office: Office) -> None:
    if not office.is_active or not office.is_assignable:
        raise ValidationError(
            {"owner_office": "Only active, assignable offices may own spaces."}
        )


@transaction.atomic
def create_space(*, actor: User, owner_office: Office, **fields) -> Space:
    require_permission(actor, SpacePermission.MANAGE, office=owner_office)
    _require_assignable_office(owner_office)
    disallowed = {
        "public_id",
        "owner_office",
        "retired_at",
        "booking_history_started_at",
    }
    if disallowed.intersection(fields):
        raise ValidationError(
            "Stable or lifecycle fields cannot be set during creation."
        )
    space = Space(
        owner_office=owner_office,
        created_by=actor,
        updated_by=actor,
        **fields,
    )
    space.full_clean()
    space.save()
    log_on_commit(
        "reservations.space.created",
        actor=actor_from_user(actor),
        target=_target(space),
        after=_snapshot(space),
        office_id=owner_office.stable_key,
    )
    return space


@transaction.atomic
def retire_space(*, actor: User, space: Space, reason: str) -> Space:
    locked = (
        Space.objects.select_for_update(of=("self",))
        .select_related("owner_office")
        .get(pk=space.pk)
    )
    require_permission(actor, SpacePermission.MANAGE, office=locked.owner_office)
    if locked.is_retired:
        raise ValidationError("This space is already retired.")
    if not reason.strip():
        raise ValidationError({"reason": "A retirement reason is required."})
    before = _snapshot(locked)
    locked.status = SpaceStatus.RETIRED
    locked.is_reservable = False
    locked.retired_at = timezone.now()
    locked.updated_by = actor
    locked.full_clean()
    locked.save()
    log_on_commit(
        "reservations.space.retired",
        actor=actor_from_user(actor),
        target=_target(locked),
        before=before,
        after=_snapshot(locked),
        office_id=locked.owner_office.stable_key,
        reason=reason,
    )
    return locked


def _transfer_locked(
    *,
    actor: User,
    locked: Space,
    to_office: Office,
    reason: str,
    preserves_booking_history: bool,
) -> SpaceOfficeTransfer:
    require_permission(actor, SpacePermission.MANAGE, office=locked.owner_office)
    require_permission(actor, SpacePermission.MANAGE, office=to_office)
    _require_assignable_office(to_office)
    if locked.is_retired:
        raise ValidationError("Retired spaces cannot be transferred.")
    if locked.owner_office_id == to_office.pk:
        raise ValidationError({"to_office": "Choose a different destination office."})
    if not reason.strip():
        raise ValidationError({"reason": "A transfer reason is required."})
    if locked.booking_history_started_at and not preserves_booking_history:
        raise ValidationError(
            "Spaces with booking history require migrate_space_office()."
        )

    before = _snapshot(locked)
    from_office = locked.owner_office
    with allow_office_transfer():
        locked.owner_office = to_office
        locked.updated_by = actor
        locked.full_clean()
        locked.save()
    transfer = SpaceOfficeTransfer(
        space=locked,
        from_office=from_office,
        to_office=to_office,
        preserves_booking_history=preserves_booking_history,
        reason=reason.strip(),
        performed_by=actor,
    )
    transfer.full_clean()
    transfer.save()
    log_on_commit(
        "reservations.space.transferred",
        actor=actor_from_user(actor),
        target=_target(locked),
        before=before,
        after=_snapshot(locked),
        office_id=to_office.stable_key,
        reason=reason,
        metadata={"preservesBookingHistory": preserves_booking_history},
    )
    return transfer


@transaction.atomic
def transfer_space(
    *, actor: User, space: Space, to_office: Office, reason: str
) -> SpaceOfficeTransfer:
    locked = (
        Space.objects.select_for_update(of=("self",))
        .select_related("owner_office")
        .get(pk=space.pk)
    )
    return _transfer_locked(
        actor=actor,
        locked=locked,
        to_office=to_office,
        reason=reason,
        preserves_booking_history=False,
    )


@transaction.atomic
def migrate_space_office(
    *, actor: User, space: Space, to_office: Office, reason: str
) -> SpaceOfficeTransfer:
    """Explicit history-preserving operation for a space that has bookings."""
    locked = (
        Space.objects.select_for_update(of=("self",))
        .select_related("owner_office")
        .get(pk=space.pk)
    )
    return _transfer_locked(
        actor=actor,
        locked=locked,
        to_office=to_office,
        reason=reason,
        preserves_booking_history=True,
    )


@transaction.atomic
def create_availability_exception(
    *,
    actor: User,
    space: Space,
    **fields,
) -> SpaceAvailabilityException:
    locked = (
        Space.objects.select_for_update(of=("self",))
        .select_related("owner_office")
        .get(pk=space.pk)
    )
    require_permission(
        actor,
        SpacePermission.MANAGE_SCHEDULE,
        office=locked.owner_office,
    )
    exception = SpaceAvailabilityException(space=locked, created_by=actor, **fields)
    exception.full_clean()
    exception.save()
    log_on_commit(
        "reservations.space.availability_blocked",
        actor=actor_from_user(actor),
        target=_target(locked),
        office_id=locked.owner_office.stable_key,
        metadata={
            "exceptionId": str(exception.public_id),
            "kind": exception.kind,
            "startsAt": exception.starts_at,
            "endsAt": exception.ends_at,
            "visibility": exception.visibility,
        },
    )
    return exception
