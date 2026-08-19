"""Named hub roles and scope rules.

Superadmin remains Django's ``is_superuser`` (staff + full /admin access), not
an assignment or group. Assignment-backed roles still map to legacy Django
groups so the existing permission model can be bridged safely during rollout.
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

    CHOICES: tuple[tuple[str, str], ...] = (
        (COMPANY, "Company"),
        (REGION, "Region"),
        (OFFICE, "Office"),
    )


@dataclass(frozen=True)
class RoleDefinition:
    key: str
    group_name: str
    label: str
    priority: int
    valid_scope_types: tuple[str, ...]
    protected: bool = False


ADMIN = "Admins"
AGENT = "Users"
REGION_MANAGER = "Region Managers"
BRANCH_MANAGER = "Branch Managers"

ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        key=ADMIN,
        group_name=ADMIN,
        label="Admin",
        priority=0,
        valid_scope_types=(ScopeType.COMPANY,),
        protected=True,
    ),
    RoleDefinition(
        key=REGION_MANAGER,
        group_name=REGION_MANAGER,
        label="Region manager",
        priority=1,
        valid_scope_types=(ScopeType.REGION,),
    ),
    RoleDefinition(
        key=BRANCH_MANAGER,
        group_name=BRANCH_MANAGER,
        label="Branch manager",
        priority=2,
        valid_scope_types=(ScopeType.OFFICE,),
    ),
    RoleDefinition(
        key=AGENT,
        group_name=AGENT,
        label="Agent",
        priority=3,
        valid_scope_types=(ScopeType.OFFICE,),
    ),
)

ROLE_BY_KEY = {definition.key: definition for definition in ROLE_DEFINITIONS}
ROLE_BY_GROUP = {definition.group_name: definition for definition in ROLE_DEFINITIONS}

SEEDED_GROUPS: tuple[str, ...] = tuple(
    definition.group_name for definition in ROLE_DEFINITIONS
)
ROLE_PRIORITY: tuple[str, ...] = tuple(
    definition.key
    for definition in sorted(ROLE_DEFINITIONS, key=lambda item: item.priority)
)
ROLE_LABELS: dict[str, str] = {
    definition.key: definition.label for definition in ROLE_DEFINITIONS
}
SUPERADMIN_LABEL = "Superadmin"


def seed_role_groups(group_model=None) -> None:
    """Idempotent: create the assignment-backed legacy groups if missing."""
    from django.contrib.auth.models import Group as LiveGroup

    Group = group_model or LiveGroup
    for name in SEEDED_GROUPS:
        Group.objects.get_or_create(name=name)


def get_role_definition(role_key: str) -> RoleDefinition:
    return ROLE_BY_KEY[role_key]


def is_valid_scope_type(role_key: str, scope_type: str) -> bool:
    definition = get_role_definition(role_key)
    return scope_type in definition.valid_scope_types


def role_group_name(role_key: str) -> str:
    return get_role_definition(role_key).group_name


def ordered_role_names(user: User) -> list[str]:
    from .services.role_assignments import get_effective_role_keys

    return get_effective_role_keys(user)


def primary_role_label(user: User) -> str:
    from .services.role_assignments import get_primary_role_key

    if getattr(user, "is_superuser", False):
        return SUPERADMIN_LABEL
    role_key = get_primary_role_key(user)
    if role_key in ROLE_LABELS:
        return ROLE_LABELS[role_key]
    return ROLE_LABELS[AGENT]
