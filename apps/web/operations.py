"""Reviewed administrative navigation, route, and permission configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from apps.user.models import Office
from apps.user.roles import (
    ADMIN,
    BRANCH_MANAGER,
    REGION_MANAGER,
    ROLE_BY_KEY,
    SYSTEM_ADMIN,
)
from apps.user.services.role_assignments import get_effective_access
from apps.web.permission_catalog import permissions_for_role


@dataclass(frozen=True)
class OperationsDestination:
    key: str
    label: str
    section: str
    route_name: str
    path: str
    permission: str
    order: int
    feature: str
    scope_rule: str


OPERATIONS_DESTINATIONS: tuple[OperationsDestination, ...] = (
    OperationsDestination(
        key="admin-users",
        label="Users",
        section="People",
        route_name="admin_users",
        path="operations/users",
        permission="web.view_users",
        order=10,
        feature="admin-users",
        scope_rule="user_office_scope",
    ),
    OperationsDestination(
        key="admin-new-agents",
        label="New Agent List",
        section="People",
        route_name="admin_new_agents",
        path="operations/new-agents",
        permission="web.view_new_agents",
        order=20,
        feature="admin-new-agents",
        scope_rule="user_office_scope",
    ),
    OperationsDestination(
        key="admin-add-user",
        label="Add New User",
        section="People",
        route_name="admin_add_user",
        path="operations/users/new",
        permission="web.add_users",
        order=30,
        feature="admin-add-user",
        scope_rule="delegated_user_scope",
    ),
    OperationsDestination(
        key="admin-assign-roles",
        label="Assign User Roles",
        section="People",
        route_name="admin_assign_roles",
        path="operations/role-assignments",
        permission="web.assign_user_roles",
        order=40,
        feature="admin-assign-roles",
        scope_rule="role_delegation_scope",
    ),
    OperationsDestination(
        key="admin-agent-contracts",
        label="Agent Contracts",
        section="People",
        route_name="admin_agent_contracts",
        path="operations/agent-contracts",
        permission="web.view_agent_contracts",
        order=50,
        feature="admin-agent-contracts",
        scope_rule="user_office_scope",
    ),
    OperationsDestination(
        key="admin-transactions",
        label="Transactions",
        section="Operations",
        route_name="admin_transactions",
        path="operations/transactions",
        permission="web.view_transactions",
        order=60,
        feature="admin-transactions",
        scope_rule="transaction_office_scope",
    ),
    OperationsDestination(
        key="admin-inventory",
        label="Inventory",
        section="Operations",
        route_name="admin_inventory",
        path="operations/inventory",
        permission="web.view_inventory",
        order=70,
        feature="admin-inventory",
        scope_rule="inventory_office_scope",
    ),
    OperationsDestination(
        key="admin-reservations",
        label="Reservations",
        section="Operations",
        route_name="admin_reservations",
        path="operations/reservations",
        permission="web.view_reservations",
        order=80,
        feature="admin-reservations",
        scope_rule="reservation_office_scope",
    ),
    OperationsDestination(
        key="admin-announcements",
        label="Announcements",
        section="Content",
        route_name="admin_announcements",
        path="operations/announcements",
        permission="web.manage_announcements",
        order=90,
        feature="admin-announcements",
        scope_rule="publication_scope",
    ),
    OperationsDestination(
        key="admin-training",
        label="Training",
        section="Content",
        route_name="admin_training",
        path="operations/training",
        permission="web.manage_training",
        order=100,
        feature="admin-training",
        scope_rule="publication_scope",
    ),
    OperationsDestination(
        key="admin-documents",
        label="Documents",
        section="Content",
        route_name="admin_documents",
        path="operations/documents",
        permission="web.manage_documents",
        order=110,
        feature="admin-documents",
        scope_rule="publication_scope",
    ),
    OperationsDestination(
        key="admin-quick-access",
        label="Quick Access",
        section="Content",
        route_name="admin_quick_access",
        path="operations/quick-access",
        permission="web.manage_quick_access",
        order=120,
        feature="admin-quick-access",
        scope_rule="quick_access_audience_scope",
    ),
    OperationsDestination(
        key="admin-compliance",
        label="Compliance",
        section="Governance & support",
        route_name="admin_compliance",
        path="operations/compliance",
        permission="web.view_compliance",
        order=130,
        feature="admin-compliance",
        scope_rule="compliance_office_scope",
    ),
    OperationsDestination(
        key="admin-feedback",
        label="Feedback",
        section="Governance & support",
        route_name="admin_feedback",
        path="operations/feedback",
        permission="web.view_feedback",
        order=140,
        feature="admin-feedback",
        scope_rule="feedback_office_scope",
    ),
    OperationsDestination(
        key="admin-platform-tasks",
        label="Platform Tasks",
        section="Governance & support",
        route_name="admin_platform_tasks",
        path="operations/platform-tasks",
        permission="web.view_platform_tasks",
        order=150,
        feature="admin-platform-tasks",
        scope_rule="sanitized_status_only",
    ),
    OperationsDestination(
        key="admin-offices",
        label="Offices",
        section="Governance & support",
        route_name="admin_offices",
        path="operations/offices",
        permission="web.manage_offices",
        order=160,
        feature="admin-offices",
        scope_rule="office_tree_scope",
    ),
    OperationsDestination(
        key="admin-it-support",
        label="IT Support",
        section="Governance & support",
        route_name="admin_it_support",
        path="operations/it-support",
        permission="web.view_it_support",
        order=170,
        feature="admin-it-support",
        scope_rule="support_request_scope",
    ),
)

OPERATIONS_BY_KEY = {
    destination.key: destination for destination in OPERATIONS_DESTINATIONS
}
OPERATIONS_BY_ROUTE = {
    destination.route_name: destination for destination in OPERATIONS_DESTINATIONS
}
OPERATIONS_FEATURES: dict[str, bool] = {
    destination.feature: False for destination in OPERATIONS_DESTINATIONS
}
OPERATIONS_FEATURES["admin-new-agents"] = True
OPERATIONS_FEATURES["admin-quick-access"] = True

_OPS_SURFACE_PERMISSIONS = frozenset(
    destination.permission for destination in OPERATIONS_DESTINATIONS
) | {"web.manage_new_agent_onboarding", "web.manage_company_quick_access"}

ROLE_OPERATION_PERMISSIONS: dict[str, frozenset[str]] = {
    # Aliases kept for existing callers; values are role defaults ∩ ops surfaces.
    ADMIN: frozenset(ROLE_BY_KEY[SYSTEM_ADMIN].default_permissions)
    & _OPS_SURFACE_PERMISSIONS,
    REGION_MANAGER: frozenset(permissions_for_role(REGION_MANAGER))
    & _OPS_SURFACE_PERMISSIONS,
    BRANCH_MANAGER: frozenset(permissions_for_role(BRANCH_MANAGER))
    & _OPS_SURFACE_PERMISSIONS,
}


def operations_policy_key(destination: OperationsDestination) -> str:
    return f"operations_{destination.route_name}"


class OperationsScope(TypedDict):
    level: str
    label: str


def operations_scope_payload(user) -> OperationsScope:
    """Describe only the current user's effective scope, without counts or data."""
    access = get_effective_access(user)
    if access.company_wide:
        return {"level": "brokerage", "label": "Brokerage-wide"}
    if access.region_keys:
        regions = list(
            Office.objects.filter(stable_key__in=access.region_keys)
            .order_by("sort_order", "name")
            .values_list("name", flat=True)
        )
        label = regions[0] if len(regions) == 1 else f"{len(regions)} regions"
        return {"level": "region", "label": label}
    if access.office_keys:
        offices = list(
            Office.objects.filter(stable_key__in=access.office_keys)
            .order_by("sort_order", "name")
            .values_list("name", flat=True)
        )
        label = offices[0] if len(offices) == 1 else f"{len(offices)} offices"
        return {"level": "office", "label": label}
    return {"level": "none", "label": "No administrative scope"}
