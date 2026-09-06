from datetime import UTC, datetime

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditEvent
from apps.reservations.models import SpaceOfficeTransfer
from apps.reservations.queries import agent_spaces
from apps.reservations.services import (
    create_availability_exception,
    create_space,
    migrate_space_office,
    retire_space,
    transfer_space,
)
from apps.reservations.taxonomy import (
    ExceptionKind,
    ExceptionVisibility,
    SpaceStatus,
    SpaceType,
)
from apps.reservations.tests.factories import assign_role, make_space, office, person
from apps.user.roles import ScopeType


def manager(seeded, email="manager@example.com", office_slug="fairfax-va"):
    user = person(email, office_slug)
    assign_role(
        user,
        "branch_manager",
        ScopeType.OFFICE,
        scope_office=office(office_slug),
    )
    return user


def test_create_requires_manage_permission(seeded):
    agent = person("agent@example.com", "fairfax-va")

    with pytest.raises(PermissionDenied):
        create_space(
            actor=agent,
            owner_office=office("fairfax-va"),
            name="Conference room",
            space_type=SpaceType.CONFERENCE_ROOM,
            capacity=10,
        )


def test_retirement_preserves_row_and_prevents_new_agent_bookings(seeded):
    actor = manager(seeded)
    agent = person("agent@example.com", "fairfax-va")
    space = make_space()

    retired = retire_space(actor=actor, space=space, reason="Lease ended")

    assert retired.status == SpaceStatus.RETIRED
    assert retired.retired_at is not None
    assert not retired.is_reservable
    assert type(space).objects.filter(pk=space.pk).exists()
    assert not agent_spaces(agent).filter(pk=space.pk).exists()


def test_ordinary_transfer_is_blocked_after_booking_history_starts(seeded):
    actor = manager(seeded)
    destination = office("harrisburg")
    actor.is_superuser = True
    actor.save(update_fields=["is_superuser"])
    space = make_space(booking_history_started_at=datetime.now(UTC))

    with pytest.raises(ValidationError, match="migrate_space_office"):
        transfer_space(
            actor=actor,
            space=space,
            to_office=destination,
            reason="Office consolidation",
        )


def test_explicit_migration_preserves_booking_history_and_transfer_record(seeded):
    actor = manager(seeded)
    actor.is_superuser = True
    actor.save(update_fields=["is_superuser"])
    space = make_space(booking_history_started_at=datetime.now(UTC))

    transfer = migrate_space_office(
        actor=actor,
        space=space,
        to_office=office("harrisburg"),
        reason="Approved office migration",
    )

    space.refresh_from_db()
    assert space.owner_office == office("harrisburg")
    assert transfer.preserves_booking_history is True
    assert SpaceOfficeTransfer.objects.filter(space=space).count() == 1


def test_direct_office_change_with_history_fails_model_validation(seeded):
    space = make_space(booking_history_started_at=datetime.now(UTC))
    space.owner_office = office("harrisburg")

    with pytest.raises(ValidationError, match="explicit migration"):
        space.full_clean()


def test_exception_creation_enforces_scope_and_writes_audit_after_commit(
    seeded, django_capture_on_commit_callbacks
):
    actor = manager(seeded)
    foreign_space = make_space(owner_slug="harrisburg")

    with pytest.raises(PermissionDenied):
        create_availability_exception(
            actor=actor,
            space=foreign_space,
            kind=ExceptionKind.MAINTENANCE,
            starts_at=datetime(2026, 1, 5, 14, tzinfo=UTC),
            ends_at=datetime(2026, 1, 5, 16, tzinfo=UTC),
            reason="HVAC service",
            visibility=ExceptionVisibility.INTERNAL,
        )

    local_space = make_space()
    with django_capture_on_commit_callbacks(execute=True):
        block = create_availability_exception(
            actor=actor,
            space=local_space,
            kind=ExceptionKind.MAINTENANCE,
            starts_at=datetime(2026, 1, 5, 14, tzinfo=UTC),
            ends_at=datetime(2026, 1, 5, 16, tzinfo=UTC),
            reason="HVAC service",
            visibility=ExceptionVisibility.INTERNAL,
        )

    assert block.created_by == actor
    assert AuditEvent.objects.filter(
        action="reservations.space.availability_blocked",
        target_id=str(local_space.public_id),
    ).exists()
