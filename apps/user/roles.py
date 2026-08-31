"""Canonical brokerage role catalog.

Stable ``code`` values are the identity used in assignments, integrations, and
migrations. Display names are presentation data and may change without altering
authorization. Django Groups remain the permission carrier; role checks never
replace permission checks.

Superadmin remains Django's ``is_superuser`` (staff + full /admin access), not
a catalog role.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import User


class ScopeType:
    COMPANY = "company"
    REGION = "region"
    OFFICE = "office"
    ASSIGNED_RECORD = "assigned_record"

    CHOICES: tuple[tuple[str, str], ...] = (
        (COMPANY, "Company"),
        (REGION, "Region"),
        (OFFICE, "Office"),
        (ASSIGNED_RECORD, "Assigned records"),
    )

    # Scopes that never target an office/region node on the assignment row.
    ORG_LESS: frozenset[str] = frozenset({COMPANY, ASSIGNED_RECORD})


# Stable codes — never rename these; change ``label`` instead.
SYSTEM_ADMIN = "system_admin"
PRINCIPAL_BROKER = "principal_broker"
BROKER_ADMIN = "broker_admin"
TRANSACTION_COORDINATOR = "transaction_coordinator"
BRANCH_MANAGER = "branch_manager"
BRANCH_ADMIN = "branch_admin"
REALTOR = "realtor"
MARKETING_TEAM = "marketing_team"
REGIONAL_MANAGER = "regional_manager"
REGIONAL_ADMIN = "regional_admin"
REGIONAL_TRANSACTION_COORDINATOR = "regional_transaction_coordinator"
ACCOUNTANT = "accountant"
COMPLIANCE = "compliance"
IT_SUPPORT = "it_support"

# Backward-compatible aliases used across the hub during the catalog rollout.
ADMIN = SYSTEM_ADMIN
AGENT = REALTOR
REGION_MANAGER = REGIONAL_MANAGER

# Legacy Django group names (and any prior assignment.role values) → stable code.
LEGACY_ROLE_ALIASES: dict[str, str] = {
    "Admins": SYSTEM_ADMIN,
    "Users": REALTOR,
    "Region Managers": REGIONAL_MANAGER,
    "Branch Managers": BRANCH_MANAGER,
    "Admin": SYSTEM_ADMIN,
    "Agent": REALTOR,
    "Region manager": REGIONAL_MANAGER,
    "Branch manager": BRANCH_MANAGER,
}

# Roles that may grant/revoke non-protected assignments (superuser always can).
DELEGATING_ROLES = frozenset({SYSTEM_ADMIN, PRINCIPAL_BROKER, BROKER_ADMIN})

# Company-wide management roles that must not be self-revoked down to zero.
MANAGEMENT_ROLE_KEYS = frozenset({SYSTEM_ADMIN, PRINCIPAL_BROKER, BROKER_ADMIN})


@dataclass(frozen=True)
class RoleDefinition:
    """Code-owned role contract. DB rows mirror this for lifecycle overrides."""

    code: str
    group_name: str
    label: str
    description: str
    priority: int
    valid_scope_types: tuple[str, ...]
    default_permissions: tuple[str, ...] = ()
    protected: bool = False
    assignable: bool = True
    is_system: bool = True

    @property
    def key(self) -> str:
        """Alias for callers that still say ``key``."""
        return self.code


# Permission bundles use ``app_label.codename``. Granular catalog growth lands
# here via reviewed changes — not ad-hoc admin edits for system roles.
_OPS_ALL = (
    "web.manage_quick_access",
    "web.manage_company_quick_access",
    "web.view_users",
    "web.view_new_agents",
    "web.manage_new_agent_onboarding",
    "web.add_users",
    "web.assign_user_roles",
    "web.view_agent_contracts",
    "contract.manage_agent_contracts",
    "contract.manage_contract_templates",
    "contract.approve_contract_templates",
    "contract.view_commission_terms",
    "contract.view_internal_notes",
    "web.view_transactions",
    "web.view_inventory",
    "web.view_reservations",
    "inventory.manage_inventory",
    "inventory.view_inventory_sensitive",
    "web.manage_announcements",
    "web.publish_announcements",
    "web.pin_announcements",
    "web.manage_training",
    "web.manage_documents",
    "web.view_compliance",
    "web.view_feedback",
    "web.triage_feedback",
    "web.assign_feedback",
    "web.note_feedback",
    "web.view_operational_tasks",
    "web.manage_operational_tasks",
    "web.assign_operational_tasks",
    "web.comment_operational_tasks",
    "web.view_platform_tasks",
    "web.manage_offices",
    "web.view_it_support",
    "web.view_office_resources_admin",
    "web.manage_office_resources",
    "web.publish_company_resources",
    "user.view_user_administration",
    "user.change_user_administration",
    "user.manage_account_state",
    "web.view_own_transactions",
    "web.view_own_tasks",
    "web.view_own_commission",
    "web.view_own_leads",
    "web.view_office_tasks",
    "web.view_reports",
    "web.export_reports",
)
_OPS_REGIONAL = (
    "web.manage_quick_access",
    "web.view_users",
    "web.view_new_agents",
    "web.manage_new_agent_onboarding",
    "contract.manage_agent_contracts",
    "contract.manage_contract_templates",
    "contract.approve_contract_templates",
    "contract.view_commission_terms",
    "contract.view_internal_notes",
    "web.view_transactions",
    "web.view_inventory",
    "web.view_reservations",
    "inventory.manage_inventory",
    "inventory.view_inventory_sensitive",
    "web.manage_announcements",
    "web.publish_announcements",
    "web.pin_announcements",
    "web.manage_training",
    "web.manage_documents",
    "web.view_feedback",
    "web.view_operational_tasks",
    "web.assign_operational_tasks",
    "web.comment_operational_tasks",
    "web.manage_offices",
    "web.view_office_resources_admin",
    "web.manage_office_resources",
    "user.view_user_administration",
    "user.change_user_administration",
    "web.view_own_transactions",
    "web.view_own_tasks",
    "web.view_own_commission",
    "web.view_own_leads",
    "web.view_office_tasks",
    "web.view_reports",
    "web.export_reports",
)
_OPS_BRANCH = (
    "web.manage_quick_access",
    "web.view_users",
    "web.view_new_agents",
    "web.manage_new_agent_onboarding",
    "contract.manage_agent_contracts",
    "contract.manage_contract_templates",
    "contract.view_commission_terms",
    "web.view_inventory",
    "web.view_reservations",
    "inventory.manage_inventory",
    "inventory.view_inventory_sensitive",
    "web.manage_announcements",
    "web.publish_announcements",
    "web.manage_training",
    "web.manage_documents",
    "web.view_feedback",
    "web.view_operational_tasks",
    "web.assign_operational_tasks",
    "web.comment_operational_tasks",
    "web.manage_offices",
    "web.view_office_resources_admin",
    "web.manage_office_resources",
    "user.view_user_administration",
    "user.change_user_administration",
    "web.view_own_transactions",
    "web.view_own_tasks",
    "web.view_own_commission",
    "web.view_own_leads",
    "web.view_office_tasks",
    "web.view_reports",
    "web.export_reports",
)
_OPS_TC = (
    "web.view_users",
    "web.view_transactions",
    "web.view_agent_contracts",
    "web.manage_documents",
    "web.view_own_transactions",
    "web.view_own_tasks",
    "web.view_reports",
    "web.export_reports",
)
_OPS_OFFICE_ADMIN = (
    "web.manage_quick_access",
    "web.view_users",
    "web.view_new_agents",
    "web.view_reservations",
    # Authoring only. Regional and branch administrators write the notice; the
    # publish grant sits with their manager.
    "web.manage_announcements",
    "web.manage_training",
    "web.manage_documents",
    "user.view_user_administration",
    "web.view_own_tasks",
    "web.view_office_tasks",
    "web.view_reports",
    "web.export_reports",
)
_OPS_REALTOR = (
    "web.view_own_transactions",
    "web.view_own_tasks",
    "web.view_own_commission",
    "web.view_own_leads",
    "web.view_reports",
)

ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        code=SYSTEM_ADMIN,
        group_name="Admins",
        label="System Admin",
        description=(
            "Platform and brokerage-wide administration. May configure roles, "
            "offices, and operational modules company-wide."
        ),
        priority=0,
        valid_scope_types=(ScopeType.COMPANY,),
        default_permissions=_OPS_ALL,
        protected=True,
    ),
    RoleDefinition(
        code=PRINCIPAL_BROKER,
        group_name="Principal Broker",
        label="Principal Broker",
        description=(
            "Licensed principal with brokerage-wide authority. Protected; "
            "assignment requires enhanced audit and cannot be delegated by "
            "ordinary administrators."
        ),
        priority=1,
        valid_scope_types=(ScopeType.COMPANY,),
        default_permissions=_OPS_ALL,
        protected=True,
    ),
    RoleDefinition(
        code=BROKER_ADMIN,
        group_name="Broker Admin",
        label="Broker Admin",
        description=(
            "Brokerage operations administrator. May assign non-protected "
            "roles within company scope and manage people company-wide."
        ),
        priority=2,
        valid_scope_types=(ScopeType.COMPANY,),
        default_permissions=_OPS_ALL,
    ),
    RoleDefinition(
        code=REGIONAL_MANAGER,
        group_name="Region Managers",
        label="Regional Manager",
        description=(
            "Owns performance and staffing for a region. Scope is the region "
            "node and its descendant offices."
        ),
        priority=3,
        valid_scope_types=(ScopeType.REGION,),
        default_permissions=_OPS_REGIONAL,
    ),
    RoleDefinition(
        code=REGIONAL_ADMIN,
        group_name="Regional Admin",
        label="Regional Admin",
        description=(
            "Supports regional operations and people administration without "
            "full regional-manager authority."
        ),
        priority=4,
        valid_scope_types=(ScopeType.REGION,),
        default_permissions=_OPS_OFFICE_ADMIN
        + (
            "web.view_transactions",
            "web.manage_offices",
            "web.view_office_resources_admin",
            "web.manage_office_resources",
            "web.view_own_transactions",
            "web.view_own_commission",
            "web.view_own_leads",
        ),
    ),
    RoleDefinition(
        code=REGIONAL_TRANSACTION_COORDINATOR,
        group_name="Regional Transaction Coordinator",
        label="Regional Transaction Coordinator",
        description=(
            "Coordinates transactions across offices in a region. Does not "
            "replace branch-level coordinators."
        ),
        priority=5,
        valid_scope_types=(ScopeType.REGION, ScopeType.ASSIGNED_RECORD),
        default_permissions=_OPS_TC + ("web.view_inventory", "web.view_reservations"),
    ),
    RoleDefinition(
        code=BRANCH_MANAGER,
        group_name="Branch Managers",
        label="Branch Manager",
        description=(
            "Owns a branch or regional office. Scope is limited to that "
            "assignable office."
        ),
        priority=6,
        valid_scope_types=(ScopeType.OFFICE,),
        default_permissions=_OPS_BRANCH,
    ),
    RoleDefinition(
        code=BRANCH_ADMIN,
        group_name="Branch Admin",
        label="Branch Admin / Office Admin",
        description=(
            "Office operations support: people lists, training, and documents "
            "within a single office."
        ),
        priority=7,
        valid_scope_types=(ScopeType.OFFICE,),
        default_permissions=_OPS_OFFICE_ADMIN
        + (
            "web.view_office_resources_admin",
            "web.manage_office_resources",
        ),
    ),
    RoleDefinition(
        code=TRANSACTION_COORDINATOR,
        group_name="Transaction Coordinator",
        label="Transaction Coordinator",
        description=(
            "Runs transaction files for an office. Authorization still uses "
            "granular permissions, not this label alone."
        ),
        priority=8,
        valid_scope_types=(ScopeType.OFFICE, ScopeType.ASSIGNED_RECORD),
        default_permissions=_OPS_TC,
    ),
    RoleDefinition(
        code=REALTOR,
        group_name="Users",
        label="Realtor",
        description=(
            "Licensed agent. Default role for new signups; office scope "
            "follows primary membership."
        ),
        priority=9,
        valid_scope_types=(ScopeType.OFFICE, ScopeType.ASSIGNED_RECORD),
        default_permissions=_OPS_REALTOR,
    ),
    RoleDefinition(
        code=MARKETING_TEAM,
        group_name="Marketing Team",
        label="Marketing Team",
        description=(
            "Brokerage marketing: announcements and feedback visibility company-wide."
        ),
        priority=10,
        valid_scope_types=(ScopeType.COMPANY,),
        default_permissions=(
            "web.manage_announcements",
            "web.publish_announcements",
            "web.pin_announcements",
            "web.view_feedback",
            "web.manage_documents",
            "web.manage_quick_access",
            "web.view_office_resources_admin",
            "web.manage_office_resources",
        ),
    ),
    RoleDefinition(
        code=ACCOUNTANT,
        group_name="Accountant",
        label="Accountant",
        description=(
            "Financial operations: transaction and people visibility for "
            "reconciliation and reporting."
        ),
        priority=11,
        valid_scope_types=(ScopeType.COMPANY,),
        default_permissions=(
            "web.view_transactions",
            "web.view_users",
            "web.view_agent_contracts",
            "contract.view_commission_terms",
            "web.view_own_commission",
            "web.view_reports",
            "web.export_reports",
        ),
    ),
    RoleDefinition(
        code=COMPLIANCE,
        group_name="Compliance",
        label="Compliance",
        description=(
            "Compliance review of licenses, contracts, and related documents "
            "company-wide."
        ),
        priority=12,
        valid_scope_types=(ScopeType.COMPANY,),
        default_permissions=(
            "web.view_compliance",
            "web.view_users",
            "web.view_agent_contracts",
            "contract.view_commission_terms",
            "contract.view_internal_notes",
            "contract.approve_contract_templates",
            "web.manage_announcements",
            "web.publish_announcements",
            "web.manage_documents",
            "user.view_user_administration",
            "web.view_reports",
            "web.export_reports",
        ),
    ),
    RoleDefinition(
        code=IT_SUPPORT,
        group_name="IT Support",
        label="IT Support",
        description=(
            "IT support queues and sanitized platform task visibility. Does "
            "not grant brokerage people administration."
        ),
        priority=13,
        valid_scope_types=(ScopeType.COMPANY,),
        default_permissions=(
            "web.view_it_support",
            "web.view_feedback",
            "web.triage_feedback",
            "web.assign_feedback",
            "web.note_feedback",
            "web.view_operational_tasks",
            "web.manage_operational_tasks",
            "web.assign_operational_tasks",
            "web.comment_operational_tasks",
            "web.view_platform_tasks",
            "web.manage_announcements",
            "web.view_users",
        ),
    ),
)

ROLE_BY_KEY = {definition.code: definition for definition in ROLE_DEFINITIONS}
ROLE_BY_GROUP = {definition.group_name: definition for definition in ROLE_DEFINITIONS}

SEEDED_GROUPS: tuple[str, ...] = tuple(
    definition.group_name for definition in ROLE_DEFINITIONS
)
ROLE_PRIORITY: tuple[str, ...] = tuple(
    definition.code
    for definition in sorted(ROLE_DEFINITIONS, key=lambda item: item.priority)
)
ROLE_LABELS: dict[str, str] = {
    definition.code: definition.label for definition in ROLE_DEFINITIONS
}
ROLE_DESCRIPTIONS: dict[str, str] = {
    definition.code: definition.description for definition in ROLE_DEFINITIONS
}
PROTECTED_ROLE_CODES: frozenset[str] = frozenset(
    definition.code for definition in ROLE_DEFINITIONS if definition.protected
)
REQUIRED_ROLE_CODES: frozenset[str] = frozenset(ROLE_BY_KEY)
SUPERADMIN_LABEL = "Superadmin"


def normalize_role_code(value: str) -> str | None:
    """Map a stable code or legacy label/group name to a catalog code."""
    if value in ROLE_BY_KEY:
        return value
    aliased = LEGACY_ROLE_ALIASES.get(value)
    if aliased is not None:
        return aliased
    if value in ROLE_BY_GROUP:
        return ROLE_BY_GROUP[value].code
    return None


def seed_role_groups(group_model=None) -> None:
    """Idempotent: create Django groups for every catalog role if missing."""
    from django.contrib.auth.models import Group as LiveGroup

    Group = group_model or LiveGroup
    for name in SEEDED_GROUPS:
        Group.objects.get_or_create(name=name)


def get_role_definition(role_key: str) -> RoleDefinition:
    code = normalize_role_code(role_key)
    if code is None:
        raise KeyError(role_key)
    return ROLE_BY_KEY[code]


def is_valid_scope_type(role_key: str, scope_type: str) -> bool:
    definition = get_role_definition(role_key)
    return scope_type in definition.valid_scope_types


def role_group_name(role_key: str) -> str:
    return get_role_definition(role_key).group_name


def is_protected_role(role_key: str) -> bool:
    code = normalize_role_code(role_key)
    return code in PROTECTED_ROLE_CODES if code else False


def active_role_definitions(*, include_inactive: bool = False) -> list[RoleDefinition]:
    """Catalog roles, optionally filtered by DB active flag when rows exist."""
    try:
        from apps.user.models import BrokerageRole
    except ImportError:
        return list(ROLE_DEFINITIONS)

    if not BrokerageRole.objects.exists():
        return list(ROLE_DEFINITIONS)

    rows = BrokerageRole.objects.all()
    if not include_inactive:
        rows = rows.filter(is_active=True)
    codes = set(rows.values_list("code", flat=True))
    return [definition for definition in ROLE_DEFINITIONS if definition.code in codes]


def assignable_role_definitions() -> list[RoleDefinition]:
    """Roles that may receive new assignments (active + assignable)."""
    try:
        from apps.user.models import BrokerageRole
    except ImportError:
        return [item for item in ROLE_DEFINITIONS if item.assignable]

    if not BrokerageRole.objects.exists():
        return [item for item in ROLE_DEFINITIONS if item.assignable]

    allowed = set(
        BrokerageRole.objects.filter(is_active=True, is_assignable=True).values_list(
            "code", flat=True
        )
    )
    return [
        definition
        for definition in ROLE_DEFINITIONS
        if definition.code in allowed and definition.assignable
    ]


def is_role_assignable(role_key: str) -> bool:
    code = normalize_role_code(role_key)
    if code is None:
        return False
    definition = ROLE_BY_KEY[code]
    if not definition.assignable:
        return False
    try:
        from apps.user.models import BrokerageRole
    except ImportError:
        return True
    row = BrokerageRole.objects.filter(code=code).first()
    if row is None:
        return True
    return row.is_active and row.is_assignable


def seed_brokerage_roles(
    *,
    sync_presentation: bool = False,
    sync_permissions: bool = True,
) -> list[str]:
    """Idempotent catalog seed.

    Creates missing ``BrokerageRole`` rows and Django groups. Existing rows keep
    ``is_active`` / ``is_assignable`` so intentional deactivation survives
    re-seed. Presentation fields update only when ``sync_presentation`` is set.
    Permission grants are additive for the role's default bundle.
    """
    from django.contrib.auth.models import Group, Permission

    from apps.user.models import BrokerageRole

    seed_role_groups()
    touched: list[str] = []
    permission_cache: dict[str, Permission] = {}

    def _permission(full_codename: str) -> Permission | None:
        if full_codename in permission_cache:
            return permission_cache[full_codename]
        if "." not in full_codename:
            return None
        app_label, codename = full_codename.split(".", 1)
        permission = (
            Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            )
            .select_related("content_type")
            .first()
        )
        if permission is not None:
            permission_cache[full_codename] = permission
        return permission

    for definition in ROLE_DEFINITIONS:
        group, _ = Group.objects.get_or_create(name=definition.group_name)
        row, created = BrokerageRole.objects.get_or_create(
            code=definition.code,
            defaults={
                "display_name": definition.label,
                "description": definition.description,
                "group_name": definition.group_name,
                "is_active": True,
                "is_assignable": definition.assignable,
                "is_system": definition.is_system,
                "is_protected": definition.protected,
                "valid_scope_types": list(definition.valid_scope_types),
                "priority": definition.priority,
            },
        )
        updates: list[str] = []
        if created:
            touched.append(definition.code)
        else:
            # System contract fields always stay aligned with code.
            if row.group_name != definition.group_name:
                row.group_name = definition.group_name
                updates.append("group_name")
            if row.is_system != definition.is_system:
                row.is_system = definition.is_system
                updates.append("is_system")
            if row.is_protected != definition.protected:
                row.is_protected = definition.protected
                updates.append("is_protected")
            if list(row.valid_scope_types) != list(definition.valid_scope_types):
                row.valid_scope_types = list(definition.valid_scope_types)
                updates.append("valid_scope_types")
            if row.priority != definition.priority:
                row.priority = definition.priority
                updates.append("priority")
            if sync_presentation:
                if row.display_name != definition.label:
                    row.display_name = definition.label
                    updates.append("display_name")
                if row.description != definition.description:
                    row.description = definition.description
                    updates.append("description")
            if updates:
                row.save(update_fields=[*updates, "updated_at"])
                touched.append(definition.code)

        if sync_permissions and definition.default_permissions:
            resolved = [
                permission
                for full in definition.default_permissions
                if (permission := _permission(full)) is not None
            ]
            if resolved:
                group.permissions.add(*resolved)

    return touched


def ordered_role_names(user: User) -> list[str]:
    from .services.role_assignments import get_effective_role_keys

    return get_effective_role_keys(user)


def primary_role_label(user: User) -> str:
    from .services.role_assignments import get_primary_role_key

    if getattr(user, "is_superuser", False):
        return SUPERADMIN_LABEL
    role_key = get_primary_role_key(user)
    if role_key and role_key in ROLE_LABELS:
        return ROLE_LABELS[role_key]
    return ROLE_LABELS[REALTOR]


def role_assignment_block_reason(
    role_key: str, *, actor_is_superuser: bool
) -> str | None:
    """Human-readable reason a role cannot be newly assigned, if any."""
    code = normalize_role_code(role_key)
    if code is None:
        return "This role is not in the brokerage catalog."
    definition = ROLE_BY_KEY[code]
    if definition.protected and not actor_is_superuser:
        return (
            f"{definition.label} is a protected system role. Only a superadmin "
            "can assign it, and the change is heavily audited."
        )
    if not is_role_assignable(code):
        return (
            f"{definition.label} is deactivated or not assignable. Historical "
            "assignments remain, but new grants are blocked."
        )
    return None
