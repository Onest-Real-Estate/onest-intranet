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
    "transition",
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
_SPACE_ADMINS = (*_MANAGERS, BRANCH_ADMIN, REGIONAL_ADMIN)
# Booking a room is ordinary staff work, so every catalog role holds it.
_SPACE_BOOKERS = (
    *_SPACE_ADMINS,
    TRANSACTION_COORDINATOR,
    REGIONAL_TRANSACTION_COORDINATOR,
    REALTOR,
    MARKETING_TEAM,
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
        codename="contract.manage_agent_contracts",
        name="Can manage scoped agent contracts",
        domain="people",
        action="manage",
        description="Create and edit agent contract drafts within office scope.",
        default_roles=(*_BROKERAGE_ADMINS, REGIONAL_MANAGER, BRANCH_MANAGER),
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="contract.manage_contract_templates",
        name="Can manage scoped contract templates",
        domain="people",
        action="manage",
        description=(
            "Create and edit draft contract templates, merge schemas, and safe "
            "synthetic previews for offices within effective scope."
        ),
        default_roles=(*_BROKERAGE_ADMINS, REGIONAL_MANAGER, BRANCH_MANAGER),
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="contract.approve_contract_templates",
        name="Can approve and activate scoped contract templates",
        domain="people",
        action="approve",
        description=(
            "Publish immutable contract template versions, activate them for new "
            "contracts, supersede older versions, and retire template families."
        ),
        default_roles=(*_BROKERAGE_ADMINS, REGIONAL_MANAGER, COMPLIANCE),
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="contract.view_commission_terms",
        name="Can view contract commission terms",
        domain="people",
        action="view",
        description=(
            "Read agent/office splits, mentor and referral terms, fees, and "
            "caps on scoped contracts."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            REGIONAL_MANAGER,
            BRANCH_MANAGER,
            ACCOUNTANT,
            COMPLIANCE,
        ),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="contract.view_internal_notes",
        name="Can view contract internal notes",
        domain="people",
        action="view",
        description="Read broker-only internal notes on scoped agent contracts.",
        default_roles=(*_BROKERAGE_ADMINS, REGIONAL_MANAGER, COMPLIANCE),
        risk="high",
        sensitive=True,
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
        codename="user.manage_account_state",
        name="Can disable or reactivate accounts",
        domain="people",
        action="manage",
        description=(
            "Disable or reactivate a user account in scope. Disabling ends "
            "every live session and blocks the next request."
        ),
        default_roles=_BROKERAGE_ADMINS,
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
        codename="web.manage_transactions",
        name="Can create and manage scoped transactions",
        domain="transactions",
        action="manage",
        description=(
            "Create drafts, edit non-status fields, and mutate party "
            "assignments within effective scope."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            REGIONAL_MANAGER,
            BRANCH_MANAGER,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
        ),
        risk="high",
    ),
    PermissionDefinition(
        codename="web.create_own_transactions",
        name="Can create own transactions as primary agent",
        domain="transactions",
        action="create",
        description=(
            "Open a draft transaction where the signed-in agent is the "
            "primary agent and the owning office is their home office."
        ),
        default_roles=(REALTOR,),
    ),
    PermissionDefinition(
        codename="web.transition_transactions",
        name="Can transition scoped transaction lifecycle",
        domain="transactions",
        action="transition",
        description=(
            "Move transactions through the enforced lifecycle within effective scope."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            REGIONAL_MANAGER,
            BRANCH_MANAGER,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
        ),
        risk="high",
    ),
    PermissionDefinition(
        codename="transactions.view_transaction_financials",
        name="Can view transaction list and contract prices",
        domain="transactions",
        action="view",
        description="View list and contract prices on scoped transactions.",
        default_roles=(
            *_BROKERAGE_ADMINS,
            REGIONAL_MANAGER,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            ACCOUNTANT,
        ),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="transactions.view_transaction_clients",
        name="Can view transaction client snapshots",
        domain="transactions",
        action="view",
        description="View client PII snapshots on scoped transactions.",
        default_roles=(
            *_BROKERAGE_ADMINS,
            REGIONAL_MANAGER,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
        ),
        sensitive=True,
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
    PermissionDefinition(
        codename="inventory.manage_inventory",
        name="Can manage scoped inventory items",
        domain="inventory",
        action="manage",
        description=(
            "Create, update, retire, and transfer inventory within effective "
            "scope. Retirement preserves history and blocks new reservations."
        ),
        default_roles=(*_MANAGERS, REGIONAL_TRANSACTION_COORDINATOR),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="inventory.view_inventory_sensitive",
        name="Can view inventory serial numbers, valuation, and internal notes",
        domain="inventory",
        action="view",
        description=(
            "Read asset identifiers, replacement value, and staff-only notes "
            "on inventory in scope."
        ),
        default_roles=(*_MANAGERS, REGIONAL_TRANSACTION_COORDINATOR),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="inventory.reserve_on_behalf",
        name="Can create inventory reservations for other users",
        domain="inventory",
        action="manage",
        description=(
            "Create inventory reservations on behalf of another agent. "
            "Actor, subject, and reason must be recorded."
        ),
        default_roles=(*_MANAGERS,),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="inventory.approve_reservations",
        name="Can approve or deny inventory reservations",
        domain="inventory",
        action="manage",
        description=(
            "Approve or deny inventory reservations that require office review."
        ),
        default_roles=(*_MANAGERS, BRANCH_ADMIN, REGIONAL_ADMIN),
    ),
    PermissionDefinition(
        codename="inventory.override_reservations",
        name="Can override inventory reservation policy",
        domain="inventory",
        action="manage",
        description=(
            "Override cancel cutoffs or related reservation policy with a "
            "mandatory reason. Never bypasses physical capacity."
        ),
        default_roles=(*_MANAGERS,),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="reservations.view_spaces",
        name="Can view scoped office spaces",
        domain="reservations",
        action="view",
        description="View room and space records within effective office scope.",
        default_roles=_SPACE_ADMINS,
    ),
    PermissionDefinition(
        codename="reservations.manage_spaces",
        name="Can manage scoped office spaces",
        domain="reservations",
        action="manage",
        description=(
            "Create, update, retire, and explicitly migrate spaces within "
            "effective office scope."
        ),
        default_roles=_SPACE_ADMINS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="reservations.manage_space_schedules",
        name="Can manage scoped space schedules and exceptions",
        domain="reservations",
        action="manage",
        description=(
            "Manage weekly availability and maintenance or closure blocks for "
            "spaces within effective office scope."
        ),
        default_roles=_SPACE_ADMINS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="reservations.book_spaces",
        name="Can book active spaces at the assigned office",
        domain="reservations",
        action="create",
        description=(
            "Create and manage own reservations for reservable spaces at the "
            "user's assigned office."
        ),
        default_roles=_SPACE_BOOKERS,
    ),
    PermissionDefinition(
        codename="reservations.manage_reservations",
        name="Can manage scoped reservations",
        domain="reservations",
        action="manage",
        description=(
            "View, book on behalf of, reschedule, and cancel other people's "
            "reservations within effective office scope."
        ),
        default_roles=_SPACE_ADMINS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="reservations.override_reservations",
        name="Can override reservation policy with an audited reason",
        domain="reservations",
        action="manage",
        description=(
            "Book outside notice, horizon, duration, or capacity policy. The "
            "reason is required and recorded on the audit event."
        ),
        default_roles=_MANAGERS,
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="reservations.view_space_sensitive",
        name="Can view sensitive space access and maintenance details",
        domain="reservations",
        action="view",
        description=(
            "Read internal access instructions and internal-only availability "
            "exception reasons for spaces in scope."
        ),
        default_roles=_SPACE_ADMINS,
        sensitive=True,
    ),
    # --- Content ---
    PermissionDefinition(
        codename="web.manage_announcements",
        name="Can manage announcements",
        domain="content",
        action="manage",
        description=(
            "Open the announcement workspace and write drafts for offices in "
            "scope. Drafts reach nobody, so this grant alone cannot change "
            "what any reader sees."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            MARKETING_TEAM,
            REGIONAL_MANAGER,
            BRANCH_MANAGER,
            REGIONAL_ADMIN,
            BRANCH_ADMIN,
            COMPLIANCE,
            IT_SUPPORT,
        ),
        risk="medium",
    ),
    PermissionDefinition(
        codename="web.publish_announcements",
        name="Can publish, schedule, and archive announcements",
        domain="content",
        action="approve",
        description=(
            "Move an announcement between draft, scheduled, published, and "
            "archived. Held apart from authoring because publication is the "
            "step that puts words in front of people; the audience is still "
            "bounded by the actor's own office grant."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            MARKETING_TEAM,
            REGIONAL_MANAGER,
            BRANCH_MANAGER,
            COMPLIANCE,
        ),
        risk="high",
    ),
    PermissionDefinition(
        codename="web.pin_announcements",
        name="Can pin announcements",
        domain="content",
        action="manage",
        description=(
            "Lift a published announcement to the top of the feed and the "
            "dashboard band. Ordering only — pinning never widens who can "
            "read it."
        ),
        default_roles=(*_BROKERAGE_ADMINS, MARKETING_TEAM, REGIONAL_MANAGER),
        risk="medium",
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
        codename="web.manage_marketing_resources",
        name="Can manage marketing resources",
        domain="content",
        action="manage",
        description=(
            "Draft, upload, version, and target audiences for marketing "
            "assets within effective publication scope."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            MARKETING_TEAM,
            REGIONAL_MANAGER,
            BRANCH_MANAGER,
            REGIONAL_ADMIN,
            BRANCH_ADMIN,
        ),
        risk="medium",
    ),
    PermissionDefinition(
        codename="web.publish_marketing_resources",
        name="Can publish, schedule, and archive marketing resources",
        domain="content",
        action="approve",
        description=(
            "Publish, schedule, unpublish, archive, or restore marketing "
            "assets within effective publication scope."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            MARKETING_TEAM,
            REGIONAL_MANAGER,
            BRANCH_MANAGER,
            REGIONAL_ADMIN,
            BRANCH_ADMIN,
            COMPLIANCE,
        ),
        risk="medium",
    ),
    PermissionDefinition(
        codename="web.download_marketing_sources",
        name="Can download marketing source files",
        domain="content",
        action="view",
        description=(
            "Download editable source files for marketing assets in scope. "
            "Export downloads use audience visibility alone."
        ),
        default_roles=(*_BROKERAGE_ADMINS, MARKETING_TEAM),
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.manage_documents",
        name="Can manage documents",
        domain="content",
        action="manage",
        description=(
            "Create, edit, target audiences, upload files, and draft new "
            "versions of documents for offices in scope. Publication and "
            "retirement are separate grants."
        ),
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
    PermissionDefinition(
        codename="web.publish_documents",
        name="Can publish, schedule, and supersede documents",
        domain="content",
        action="approve",
        description=(
            "Publish or schedule a draft document version and supersede the "
            "previous current sibling in the family. Scoped publishers cannot "
            "widen audience or jurisdiction beyond their grant."
        ),
        default_roles=(
            *_MANAGERS,
            BRANCH_ADMIN,
            REGIONAL_ADMIN,
            MARKETING_TEAM,
            COMPLIANCE,
        ),
        risk="high",
    ),
    PermissionDefinition(
        codename="web.retire_documents",
        name="Can retire published documents",
        domain="content",
        action="manage",
        description=(
            "Retire a published document version after reviewing usage. "
            "Files and history are retained."
        ),
        default_roles=(*_MANAGERS, REGIONAL_ADMIN, COMPLIANCE),
        risk="high",
        sensitive=True,
    ),
    # --- Governance ---
    PermissionDefinition(
        codename="web.manage_quick_access",
        name="Can manage scoped Quick Access links",
        domain="content",
        action="manage",
        description=(
            "Create, edit, reorder, and archive dashboard Quick Access links "
            "for offices within effective scope."
        ),
        default_roles=(*_MANAGERS, REGIONAL_ADMIN, BRANCH_ADMIN, MARKETING_TEAM),
        risk="medium",
    ),
    PermissionDefinition(
        codename="web.manage_company_quick_access",
        name="Can manage company-wide Quick Access links",
        domain="content",
        action="manage",
        description=(
            "Publish a Quick Access link to the whole brokerage and edit "
            "company-owned link definitions. Strictly wider than the scoped "
            "grant, so it is held separately."
        ),
        default_roles=_BROKERAGE_ADMINS,
        risk="high",
        scoped=False,
        sensitive=True,
    ),
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
        codename="web.manage_policies",
        name="Can manage policies",
        domain="governance",
        action="manage",
        description=(
            "Draft, edit, target audiences, upload files, submit for review, "
            "and create new policy versions within effective scope."
        ),
        default_roles=(*_BROKERAGE_ADMINS, COMPLIANCE),
        risk="medium",
    ),
    PermissionDefinition(
        codename="web.approve_policies",
        name="Can approve policies",
        domain="governance",
        action="approve",
        description=(
            "Move an in-review policy version to approved. Separate from "
            "drafting and from publication."
        ),
        default_roles=(*_BROKERAGE_ADMINS, COMPLIANCE),
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.publish_policies",
        name="Can publish and retire policies",
        domain="governance",
        action="approve",
        description=(
            "Publish, supersede, or retire approved policy versions within "
            "effective scope."
        ),
        default_roles=(*_BROKERAGE_ADMINS, COMPLIANCE),
        risk="high",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.view_policy_acknowledgements",
        name="Can view scoped policy acknowledgements",
        domain="governance",
        action="view",
        description=(
            "Read acknowledgement completion and overdue reports for policies in scope."
        ),
        default_roles=(*_BROKERAGE_ADMINS, COMPLIANCE),
        risk="medium",
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.waive_policy_acknowledgements",
        name="Can waive policy acknowledgements",
        domain="governance",
        action="manage",
        description=(
            "Grant a reasoned waiver for a required policy acknowledgement "
            "within effective scope. Evidence rows are never deleted."
        ),
        default_roles=(*_BROKERAGE_ADMINS, COMPLIANCE),
        risk="high",
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
        codename="web.triage_feedback",
        name="Can triage scoped feedback",
        domain="governance",
        action="manage",
        description=(
            "Read other people's feedback in scope, move it through the "
            "lifecycle, set priority, and convert it to operational work."
        ),
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.assign_feedback",
        name="Can assign feedback tickets",
        domain="governance",
        action="manage",
        description="Set or clear the assignee on a ticket in scope.",
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
    ),
    PermissionDefinition(
        codename="web.note_feedback",
        name="Can write internal notes on feedback",
        domain="governance",
        action="manage",
        description=(
            "Write staff-only notes. Never visible to the submitter, and "
            "separate from replying to them."
        ),
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.view_operational_tasks",
        name="Can view scoped operational tasks",
        domain="governance",
        action="view",
        description=(
            "View operational tasks within effective scope, plus tasks the "
            "holder reported, is assigned, or was explicitly shared."
        ),
        default_roles=(*_MANAGERS, IT_SUPPORT),
    ),
    PermissionDefinition(
        codename="web.manage_operational_tasks",
        name="Can create and transition operational tasks",
        domain="governance",
        action="manage",
        description=(
            "Create tasks, move them through the lifecycle, write internal "
            "notes, and reopen closed work."
        ),
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
        sensitive=True,
    ),
    PermissionDefinition(
        codename="web.assign_operational_tasks",
        name="Can assign operational tasks",
        domain="governance",
        action="manage",
        description="Set or clear the assignee on a task in scope.",
        default_roles=(*_MANAGERS, IT_SUPPORT),
    ),
    PermissionDefinition(
        codename="web.comment_operational_tasks",
        name="Can comment on operational tasks",
        domain="governance",
        action="manage",
        description=(
            "Post a visible comment. Internal staff-only notes need the "
            "management grant instead."
        ),
        default_roles=(*_MANAGERS, IT_SUPPORT),
        risk="low",
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
        codename="web.view_office_resources_admin",
        name="Can view the office resources console",
        domain="content",
        action="view",
        description=(
            "Open the office resources administration console for resources "
            "within the actor's office-tree scope."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            REGIONAL_MANAGER,
            REGIONAL_ADMIN,
            BRANCH_MANAGER,
            BRANCH_ADMIN,
            MARKETING_TEAM,
        ),
    ),
    PermissionDefinition(
        codename="web.manage_office_resources",
        name="Can manage scoped office resources",
        domain="content",
        action="manage",
        description=(
            "Create, edit, schedule, reorder, archive, and upload files for "
            "office resources owned by offices within scope."
        ),
        default_roles=(
            *_BROKERAGE_ADMINS,
            REGIONAL_MANAGER,
            REGIONAL_ADMIN,
            BRANCH_MANAGER,
            BRANCH_ADMIN,
            MARKETING_TEAM,
        ),
        risk="high",
    ),
    PermissionDefinition(
        codename="web.publish_company_resources",
        name="Can publish company-wide office resources",
        domain="content",
        action="manage",
        description=(
            "Author or edit company-owned (head-office) resources and shadow "
            "wider-scope slugs. Requires company-wide authority as well."
        ),
        default_roles=_BROKERAGE_ADMINS,
        risk="high",
    ),
    PermissionDefinition(
        codename="web.manage_onboarding_tools",
        name="Can manage the agent tool catalog",
        domain="platform",
        action="manage",
        description=(
            "Add, edit, reorder, and retire the tools every agent is set up "
            "with, including which offices each applies to and the setup guide "
            "agents follow. Brokerage-wide configuration, distinct from moving "
            "one agent's checklist."
        ),
        default_roles=_BROKERAGE_ADMINS,
        risk="high",
    ),
    PermissionDefinition(
        codename="web.view_it_support",
        name="Can view scoped IT support requests",
        domain="platform",
        action="view",
        description="View IT support requests in scope.",
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
    ),
    PermissionDefinition(
        codename="web.triage_it_support",
        name="Can triage scoped IT support requests",
        domain="platform",
        action="manage",
        description=(
            "Read other people's IT requests in scope, move them through the "
            "lifecycle, and set priority."
        ),
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
    ),
    PermissionDefinition(
        codename="web.assign_it_support",
        name="Can assign IT support requests",
        domain="platform",
        action="manage",
        description="Set or clear the owner of an IT support request.",
        default_roles=(*_BROKERAGE_ADMINS, IT_SUPPORT),
    ),
    PermissionDefinition(
        codename="web.note_it_support",
        name="Can write internal notes on IT support requests",
        domain="platform",
        action="manage",
        description=(
            "Write IT-only notes and attach IT-only files. Never visible to "
            "the requester."
        ),
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
    PermissionDefinition(
        codename="web.view_reports",
        name="Can view the operational reports catalog",
        domain="reporting",
        action="view",
        description=(
            "Open the reports hub. Individual reports still require their own "
            "domain permissions and effective scope."
        ),
        default_roles=(
            *_MANAGERS,
            BRANCH_ADMIN,
            REGIONAL_ADMIN,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            ACCOUNTANT,
            COMPLIANCE,
            REALTOR,
        ),
        risk="low",
    ),
    PermissionDefinition(
        codename="web.export_reports",
        name="Can export operational reports",
        domain="reporting",
        action="export",
        description=(
            "Request and download scoped report exports. Files expire and are "
            "served only through an authorized download view."
        ),
        default_roles=(
            *_MANAGERS,
            BRANCH_ADMIN,
            REGIONAL_ADMIN,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            ACCOUNTANT,
            COMPLIANCE,
        ),
        risk="high",
        sensitive=True,
    ),
    # --- Audit ---
    PermissionDefinition(
        codename="audit.can_view_activity_timeline",
        name="Can view activity timelines",
        domain="activity",
        action="view",
        description=(
            "View the permission-aware activity timeline projected from audit "
            "events for records in scope. Distinct from raw audit-log access."
        ),
        default_roles=(
            *_MANAGERS,
            BRANCH_ADMIN,
            REGIONAL_ADMIN,
            TRANSACTION_COORDINATOR,
            REGIONAL_TRANSACTION_COORDINATOR,
            COMPLIANCE,
            IT_SUPPORT,
            ACCOUNTANT,
        ),
        risk="medium",
        sensitive=True,
    ),
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
CATALOG_VERSION = "p1-document-version-admin-v1"


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
