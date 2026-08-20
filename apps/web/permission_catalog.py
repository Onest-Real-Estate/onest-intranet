"""Reviewed intranet permission catalog.

Django ``Permission`` rows remain authoritative at runtime. This module is the
code-owned inventory of every protected P0 capability: descriptions, domains,
actions, default role recipients, and risk metadata. Authorization helpers fail
closed on any codename absent from this catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apps.user.roles import (
    ACCOUNTANT,
    BRANCH_ADMIN,
    BRANCH_MANAGER,
    BROKER_ADMIN,
    COMPLIANCE,
    IT_SUPPORT,
    MARKETING_TEAM,
    PRINCIPAL_BROKER,
    REALTOR,
    REGIONAL_ADMIN,
    REGIONAL_MANAGER,
    REGIONAL_TRANSACTION_COORDINATOR,
    SYSTEM_ADMIN,
    TRANSACTION_COORDINATOR,
)

PermissionAction = Literal[
    "view",
    "create",
    "change",
    "approve",
    "assign",
    "export",
    "manage",
    "replay",
]
PermissionRisk = Literal["low", "medium", "high"]

# Common default role sets used by the matrix below.
_BROKERAGE_ADMINS = (SYSTEM_ADMIN, PRINCIPAL_BROKER, BROKER_ADMIN)
_MANAGERS = (*_BROKERAGE_ADMINS, REGIONAL_MANAGER, BRANCH_MANAGER)
_PEOPLE_READERS = (
    *_MANAGERS,
    BRANCH_ADMIN,
    REGIONAL_ADMIN,
    TRANSACTION_COORDINATOR,
    REGIONAL_TRANSACTION_COORDINATOR,
    ACCOUNTANT,
    COMPLIANCE,
    IT_SUPPORT,
)


@dataclass(frozen=True)
class PermissionDefinition:
    """One catalogued capability, identified by ``app_label.codename``."""

    codename: str
    name: str
    domain: str
    action: PermissionAction
    description: str
    default_roles: tuple[str, ...] = ()
    risk: PermissionRisk = "medium"
    scoped: bool = True
    sensitive: bool = False

    @property
    def app_label(self) -> str:
        return self.codename.split(".", 1)[0]

    @property
    def permission_codename(self) -> str:
        return self.codename.split(".", 1)[1]


PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    # --- People / administration ---
    PermissionDefinition(
        codename="web.view_users",
        name="Can view scoped users",
        domain="people",
        action="view",
        description="List and open people records within effective office scope.",
        default_roles=_PEOPLE_READERS,
    ),
    PermissionDefinition(
        codename="web.view_new_agents",
        name="Can view scoped new agents",
        domain="people",
        action="view",
        description="Open the New Agent List for offices in scope.",
        default_roles=(*_MANAGERS, BRANCH_ADMIN, REGIONAL_ADMIN),
    ),
    PermissionDefinition(
        codename="web.manage_new_agent_onboarding",
        name="Can manage scoped new-agent onboarding",
        domain="people",
        action="manage",
        description="Update operational onboarding tasks for agents in scope.",
        default_roles=_MANAGERS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.add_users",
        name="Can add users",
        domain="people",
        action="create",
        description="Invite or create user accounts within delegated scope.",
        default_roles=_BROKERAGE_ADMINS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.assign_user_roles",
        name="Can assign user roles",
        domain="people",
        action="assign",
        description="Grant or revoke non-protected role assignments in scope.",
        default_roles=_BROKERAGE_ADMINS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.view_agent_contracts",
        name="Can view scoped agent contracts",
        domain="people",
        action="view",
        description="Read agent contract status for people in scope.",
        default_roles=(
            *_BROKERAGE_ADMINS,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            ACCOUNTANT,
            COMPLIANCE,
        ),
    ),
    PermissionDefinition(
        codename="user.view_user_administration",
        name="Can view administrative profile fields",
        domain="people",
        action="view",
        description="View broker-controlled agent administration fields.",
        default_roles=(
            *_MANAGERS,
            BRANCH_ADMIN,
            REGIONAL_ADMIN,
            COMPLIANCE,
        ),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="user.change_user_administration",
        name="Can change administrative profile fields",
        domain="people",
        action="change",
        description="Edit broker-controlled agent administration fields.",
        default_roles=_MANAGERS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="user.view_user",
        name="Can view user",
        domain="people",
        action="view",
        description="Django model permission to view User rows (admin/API).",
        default_roles=_BROKERAGE_ADMINS,
        scoped=False,
    ),
    PermissionDefinition(
        codename="user.change_user",
        name="Can change user",
        domain="people",
        action="change",
        description="Django model permission to change User rows (admin).",
        default_roles=_BROKERAGE_ADMINS,
        scoped=False,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="user.view_office",
        name="Can view office",
        domain="organization",
        action="view",
        description="Django model permission to view Office rows in admin.",
        default_roles=_BROKERAGE_ADMINS,
        scoped=False,
    ),
    # --- Transactions / inventory ---
    PermissionDefinition(
        codename="web.view_transactions",
        name="Can view scoped transactions",
        domain="transactions",
        action="view",
        description="View transaction records within effective scope.",
        default_roles=(
            *_BROKERAGE_ADMINS,
            REGIONAL_MANAGER,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            ACCOUNTANT,
            REGIONAL_ADMIN,
        ),
    ),
    PermissionDefinition(
        codename="web.view_inventory",
        name="Can view scoped inventory",
        domain="inventory",
        action="view",
        description="View inventory items within effective scope.",
        default_roles=(*_MANAGERS, REGIONAL_TRANSACTION_COORDINATOR),
    ),
    PermissionDefinition(
        codename="web.view_reservations",
        name="Can view scoped reservations",
        domain="inventory",
        action="view",
        description="View reservations within effective scope.",
        default_roles=(*_MANAGERS, BRANCH_ADMIN, REGIONAL_ADMIN),
    ),
    # --- Content ---
    PermissionDefinition(
        codename="web.manage_announcements",
        name="Can manage announcements",
        domain="content",
        action="manage",
        description="Create and publish brokerage announcements.",
        default_roles=(*_BROKERAGE_ADMINS, MARKETING_TEAM),
        risk="high",
    ),
    PermissionDefinition(
        codename="web.manage_training",
        name="Can manage training",
        domain="content",
        action="manage",
        description="Manage training content for offices in scope.",
        default_roles=(*_MANAGERS, BRANCH_ADMIN, REGIONAL_ADMIN),
    ),
    PermissionDefinition(
        codename="web.manage_documents",
        name="Can manage documents",
        domain="content",
        action="manage",
        description="Manage shared documents for offices in scope.",
        default_roles=(
            *_MANAGERS,
            BRANCH_ADMIN,
            REGIONAL_ADMIN,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            MARKETING_TEAM,
            COMPLIANCE,
        ),
    ),
    # --- Governance ---
    PermissionDefinition(
        codename="web.view_compliance",
        name="Can view scoped compliance items",
        domain="governance",
        action="view",
        description="View compliance queues within effective scope.",
        default_roles=(*_BROKERAGE_ADMINS, COMPLIANCE),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.view_feedback",
        name="Can view scoped feedback",
        domain="governance",
        action="view",
        description="View feedback submitted in scope.",
        default_roles=(*_MANAGERS, MARKETING_TEAM),
    ),
    PermissionDefinition(
        codename="web.view_platform_tasks",
        name="Can view sanitized platform task status",
        domain="platform",
        action="view",
        description="View sanitized Celery/platform task status.",
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
        scoped=False,
        risk="low",
    ),
    PermissionDefinition(
        codename="web.manage_offices",
        name="Can manage scoped offices",
        domain="organization",
        action="manage",
        description="Manage office records within the hierarchy scope.",
        default_roles=(*_MANAGERS, REGIONAL_ADMIN),
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.view_it_support",
        name="Can view scoped IT support requests",
        domain="platform",
        action="view",
        description="View IT support requests in scope.",
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
    ),
    # --- Dashboard metrics ---
    PermissionDefinition(
        codename="web.view_own_transactions",
        name="Can view own transaction metrics",
        domain="dashboard",
        action="view",
        description="View personal transaction dashboard metrics.",
        default_roles=(
            *_MANAGERS,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            REALTOR,
            REGIONAL_ADMIN,
        ),
        scoped=False,
        risk="low",
    ),
    PermissionDefinition(
        codename="web.view_own_tasks",
        name="Can view own task metrics",
        domain="dashboard",
        action="view",
        description="View personal task dashboard metrics.",
        default_roles=(
            *_MANAGERS,
            BRANCH_ADMIN,
            REGIONAL_ADMIN,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            REALTOR,
        ),
        scoped=False,
        risk="low",
    ),
    PermissionDefinition(
        codename="web.view_own_commission",
        name="Can view own commission metrics",
        domain="dashboard",
        action="view",
        description="View personal commission dashboard metrics.",
        default_roles=(*_MANAGERS, REALTOR, ACCOUNTANT, REGIONAL_ADMIN),
        scoped=False,
        risk="low",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.view_own_leads",
        name="Can view own lead metrics",
        domain="dashboard",
        action="view",
        description="View personal lead dashboard metrics.",
        default_roles=(*_MANAGERS, REALTOR, REGIONAL_ADMIN),
        scoped=False,
        risk="low",
    ),
    PermissionDefinition(
        codename="web.view_office_tasks",
        name="Can view scoped team task metrics",
        domain="dashboard",
        action="view",
        description="View team task aggregates for offices in scope.",
        default_roles=(*_MANAGERS, BRANCH_ADMIN, REGIONAL_ADMIN),
        risk="low",
    ),
    # --- Audit ---
    PermissionDefinition(
        codename="audit.can_view_audit_events",
        name="Can view audit events",
        domain="audit",
        action="view",
        description="Query audit events within effective scope.",
        default_roles=_BROKERAGE_ADMINS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="audit.can_export_audit_events",
        name="Can export audit events",
        domain="audit",
        action="export",
        description="Export audit events within effective scope.",
        default_roles=_BROKERAGE_ADMINS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="audit.can_replay_events",
        name="Can replay / retry domain events",
        domain="audit",
        action="replay",
        description="Replay or retry domain event deliveries.",
        default_roles=_BROKERAGE_ADMINS,
        risk="high",
        sensitive=True,
        scoped=False,
    ),
    # --- Django admin break-glass surface (staff + this grant; not hub UI) ---
    PermissionDefinition(
        codename="admin.access_admin",
        name="Can access Django admin",
        domain="platform",
        action="manage",
        description=(
            "Enter the Django admin site (/admin/). Separate from hub System Admin."
        ),
        default_roles=(),
        risk="high",
        sensitive=True,
        scoped=False,
    ),
)

PERMISSION_BY_CODENAME: dict[str, PermissionDefinition] = {
    item.codename: item for item in PERMISSION_DEFINITIONS
}
CATALOG_CODENAMES: frozenset[str] = frozenset(PERMISSION_BY_CODENAME)
CATALOG_VERSION = "p0-permissions-v1"


def is_cataloged_permission(codename: str) -> bool:
    return codename in PERMISSION_BY_CODENAME


def get_permission_definition(codename: str) -> PermissionDefinition:
    return PERMISSION_BY_CODENAME[codename]


def permissions_for_role(role_code: str) -> frozenset[str]:
    return frozenset(
        item.codename
        for item in PERMISSION_DEFINITIONS
        if role_code in item.default_roles
    )


def catalog_payload_for_client() -> dict[str, object]:
    """Compact metadata safe for authenticated clients (no grant matrix)."""
    return {
        "version": CATALOG_VERSION,
    }


def filter_to_catalog(permissions: set[str] | frozenset[str]) -> frozenset[str]:
    """Keep only reviewed catalog codenames (client + EffectiveAccess)."""
    return frozenset(item for item in permissions if item in CATALOG_CODENAMES)
