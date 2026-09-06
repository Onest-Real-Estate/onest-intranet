from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from apps.reservations.models import Space, SpaceAvailabilityException, SpacePhoto
from apps.reservations.taxonomy import (
    ExceptionVisibility,
    SpacePermission,
    SpaceStatus,
)
from apps.user.models import User
from apps.web.capability import has_capability


def _with_catalog_relations(queryset: QuerySet[Space]) -> QuerySet[Space]:
    return queryset.select_related(
        "owner_office", "owner_office__region"
    ).prefetch_related(
        "amenities",
        Prefetch("photos", queryset=SpacePhoto.objects.filter(is_public=True)),
    )


def agent_spaces(user: User) -> QuerySet[Space]:
    """Active reservable spaces at the signed-in user's effective office."""
    office = getattr(user, "office", None)
    return _with_catalog_relations(
        Space.objects.for_agent_office(office).defer("access_instructions")
    )


def manager_spaces(
    user: User,
    *,
    access,
    include_retired: bool = False,
    include_sensitive: bool = False,
) -> QuerySet[Space]:
    """Permission-checked, hierarchy-scoped administration queryset."""
    if not has_capability(user, SpacePermission.VIEW, access=access):
        return Space.objects.none()
    queryset = Space.objects.for_manager(user, access=access)
    if not include_retired:
        queryset = queryset.exclude(status=SpaceStatus.RETIRED)
    if not include_sensitive or not has_capability(
        user, SpacePermission.VIEW_SENSITIVE, access=access
    ):
        queryset = queryset.defer("access_instructions")
    return _with_catalog_relations(queryset)


def space_for_agent(user: User, *, public_id) -> Space | None:
    return agent_spaces(user).filter(public_id=public_id).first()


def space_for_manager(
    user: User, *, access, public_id, include_retired: bool = False
) -> Space | None:
    return (
        manager_spaces(user, access=access, include_retired=include_retired)
        .filter(public_id=public_id)
        .first()
    )


def _reader_visibility(user: User, space: Space, *, access=None) -> tuple[bool, bool]:
    agent_visible = (
        space.owner_office_id == getattr(user, "office_id", None)
        and space.status == SpaceStatus.ACTIVE
        and space.is_reservable
    )
    manager_visible = False
    if access is not None and has_capability(user, SpacePermission.VIEW, access=access):
        manager_visible = (
            Space.objects.for_manager(user, access=access).filter(pk=space.pk).exists()
        )
    return agent_visible or manager_visible, manager_visible


def exceptions_for_reader(
    user: User,
    *,
    space: Space,
    access=None,
) -> QuerySet[SpaceAvailabilityException]:
    """Hide internal blocks entirely unless the sensitive-field grant is held."""
    queryset = space.availability_exceptions.all()
    visible, manager_visible = _reader_visibility(user, space, access=access)
    if not visible:
        return queryset.none()
    if not manager_visible or not has_capability(
        user, SpacePermission.VIEW_SENSITIVE, access=access
    ):
        queryset = queryset.filter(visibility=ExceptionVisibility.PUBLIC)
    return queryset.select_related("created_by")


def space_payload(user: User, space: Space, *, access=None) -> dict | None:
    visible, manager_visible = _reader_visibility(user, space, access=access)
    if not visible:
        return None
    payload = {
        "id": str(space.public_id),
        "officeId": space.owner_office.stable_key,
        "name": space.name,
        "spaceType": space.space_type,
        "capacity": space.capacity,
        "description": space.description,
        "location": space.location,
        "amenities": [amenity.code for amenity in space.amenities.all()],
        "status": space.status,
        "isReservable": space.is_reservable,
        "displayOrder": space.display_order,
    }
    if manager_visible and has_capability(
        user, SpacePermission.VIEW_SENSITIVE, access=access
    ):
        payload["accessInstructions"] = space.access_instructions
    return payload
