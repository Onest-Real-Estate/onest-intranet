"""Resolve who receives a contract notification for a given event.

Recipients come from the frozen contract (agent, creator) and from currently
authorized operational roles whose scope covers the contract's office. Domain
producers call these helpers; they never invent office or owner ids from the
client.
"""

from __future__ import annotations

from django.db.models import Q

from apps.contract.models import AgentContract
from apps.contract.permissions import MANAGE_AGENT_CONTRACTS
from apps.user.models import User, UserRoleAssignment
from apps.user.roles import ADMIN, BRANCH_MANAGER, REGION_MANAGER, ScopeType
from apps.web.capability import evaluate_permission

#: Soft cap so a company-wide role cannot turn one viewed event into a storm.
_MAX_STAFF_RECIPIENTS = 40


def agent_recipient_id(contract: AgentContract) -> int | None:
    recipient_id = getattr(contract, "recipient_id", None)
    return int(recipient_id) if recipient_id else None


def operational_staff_ids(
    contract: AgentContract,
    *,
    permission: str = MANAGE_AGENT_CONTRACTS,
    exclude_ids: set[int] | None = None,
) -> list[int]:
    """Active users who may operate on this contract's office right now.

    Always includes ``created_by`` when active and authorized. Then candidates
    with management role assignments that can cover the office, gated by
    :func:`evaluate_permission` so revoked grants disappear without rewriting
    old notifications.
    """
    excluded = set(exclude_ids or ())
    agent_id = agent_recipient_id(contract)
    if agent_id is not None:
        excluded.add(agent_id)

    office = contract.office
    candidate_ids: set[int] = set()
    created_by_id = getattr(contract, "created_by_id", None)
    if created_by_id:
        candidate_ids.add(int(created_by_id))

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
