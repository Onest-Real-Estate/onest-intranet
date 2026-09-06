from __future__ import annotations

from apps.reservations.models import Space
from apps.reservations.taxonomy import SpaceType
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
