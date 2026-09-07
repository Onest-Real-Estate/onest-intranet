from __future__ import annotations

import uuid
from datetime import datetime

from apps.reservations.models import Occupancy, Reservation, Space
from apps.reservations.taxonomy import OccupancySource, SpaceType
from apps.user.models import Office, UserRoleAssignment
from apps.user.tests.test_profile import completed_user


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, office_slug: str):
    return completed_user(email=email, office=office(office_slug))


def assign_role(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def make_space(owner_slug: str = "fairfax-va", **fields) -> Space:
    space = Space(
        owner_office=office(owner_slug),
        name=fields.pop("name", "Blue conference room"),
        space_type=fields.pop("space_type", SpaceType.CONFERENCE_ROOM),
        capacity=fields.pop("capacity", 8),
        **fields,
    )
    space.full_clean()
    space.save()
    return space


def make_occupancy(
    space: Space,
    *,
    starts_at: datetime,
    ends_at: datetime,
    source: str = OccupancySource.RESERVATION,
    consumes_capacity: bool = True,
) -> Occupancy:
    occupancy = Occupancy(
        space=space,
        starts_at=starts_at,
        ends_at=ends_at,
        source=source,
        consumes_capacity=consumes_capacity,
    )
    occupancy.full_clean()
    occupancy.save()
    return occupancy


def make_reservation(
    *,
    space: Space,
    owner,
    starts_at: datetime,
    ends_at: datetime,
    **fields,
) -> Reservation:
    """Build a reservation and its ledger row the way the service will."""
    occupancy = fields.pop(
        "occupancy",
        make_occupancy(space, starts_at=starts_at, ends_at=ends_at),
    )
    reservation = Reservation(
        occupancy=occupancy,
        space=space,
        owner=owner,
        office=fields.pop("office", space.owner_office),
        office_name=fields.pop("office_name", space.owner_office.name),
        space_name=fields.pop("space_name", space.name),
        starts_at=starts_at,
        ends_at=ends_at,
        reference=fields.pop("reference", uuid.uuid4().hex[:12].upper()),
        purpose=fields.pop("purpose", "Buyer consultation"),
        submission_key=fields.pop("submission_key", uuid.uuid4().hex),
        created_by=fields.pop("created_by", owner),
        **fields,
    )
    reservation.full_clean()
    reservation.save()
    return reservation
