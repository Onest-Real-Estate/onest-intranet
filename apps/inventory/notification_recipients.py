"""Resolve office staff who may receive inventory reservation notices.

Recipients come from currently authorized role assignments whose scope covers
the reservation office. Domain schedulers call these helpers; they never trust
client-supplied office or owner identifiers.
"""

from __future__ import annotations

from django.db.models import Q

from apps.inventory.models import InventoryReservation
from apps.inventory.reservation_taxonomy import ReservationPermission
from apps.user.models import User, UserRoleAssignment
from apps.user.roles import ADMIN, BRANCH_MANAGER, REGION_MANAGER, ScopeType
from apps.web.capability import evaluate_permission

_MAX_STAFF_RECIPIENTS = 40


def operational_staff_ids(
    reservation: InventoryReservation,
    *,
    permission: str = ReservationPermission.APPROVE,
    exclude_ids: set[int] | None = None,
) -> list[int]:
    """Active users who may operate on this reservation's office right now."""
    excluded = set(exclude_ids or ())
    owner_id = getattr(reservation, "owner_id", None)
    if owner_id:
        excluded.add(int(owner_id))

    office = reservation.office
    candidate_ids: set[int] = set()
    checked_out_by_id = getattr(reservation, "checked_out_by_id", None)
    if checked_out_by_id:
        candidate_ids.add(int(checked_out_by_id))

    if office is not None:
        region = getattr(office, "region", None)
        reach = Q(is_superuser=True) | Q(
            role_assignments__role=ADMIN,
            role_assignments__scope_type=ScopeType.COMPANY,
            role_assignments__status=UserRoleAssignment.Status.ACTIVE,
        )
        reach |= Q(
            role_assignments__role=BRANCH_MANAGER,
            role_assignments__scope_type=ScopeType.OFFICE,
            role_assignments__scope_office=office,
            role_assignments__status=UserRoleAssignment.Status.ACTIVE,
        )
        if region is not None:
            reach |= Q(
                role_assignments__role=REGION_MANAGER,
                role_assignments__scope_type=ScopeType.REGION,
                role_assignments__scope_office=region,
                role_assignments__status=UserRoleAssignment.Status.ACTIVE,
            )
        candidate_ids.update(
            User.objects.filter(is_active=True)
            .filter(reach)
            .values_list("pk", flat=True)
            .distinct()[: _MAX_STAFF_RECIPIENTS * 3]
        )

    resolved: list[int] = []
    for user in User.objects.filter(pk__in=candidate_ids, is_active=True).order_by(
        "pk"
    ):
        if user.pk in excluded:
            continue
        decision = evaluate_permission(user, permission, office=office)
        if not decision.allowed:
            continue
        resolved.append(user.pk)
        if len(resolved) >= _MAX_STAFF_RECIPIENTS:
            break
    return resolved
