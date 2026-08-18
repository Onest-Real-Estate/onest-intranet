"""Named hub roles.

Superadmin is Django's ``is_superuser`` (staff + full /admin access), not a
Group. Everyone else is a Django Group so permissions can be granted in the
admin without code changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import User

# Keep names in sync with migrations 0002 and 0005.
AGENT = "Users"
ADMIN = "Admins"
REGION_MANAGER = "Region Managers"
BRANCH_MANAGER = "Branch Managers"

# Groups that should exist after migrate. Superadmin is not in this list.
SEEDED_GROUPS: tuple[str, ...] = (ADMIN, REGION_MANAGER, BRANCH_MANAGER, AGENT)

# Highest-priority first when a user is in more than one group.
ROLE_PRIORITY: tuple[str, ...] = (ADMIN, REGION_MANAGER, BRANCH_MANAGER, AGENT)

ROLE_LABELS: dict[str, str] = {
    ADMIN: "Admin",
    REGION_MANAGER: "Region manager",
    BRANCH_MANAGER: "Branch manager",
    AGENT: "Agent",
}

SUPERADMIN_LABEL = "Superadmin"


def seed_role_groups(group_model=None) -> None:
    """Idempotent: create the management + agent groups if missing."""
    from django.contrib.auth.models import Group as LiveGroup

    Group = group_model or LiveGroup
    for name in SEEDED_GROUPS:
        Group.objects.get_or_create(name=name)


def ordered_role_names(user: User) -> list[str]:
    names = list(user.groups.values_list("name", flat=True))
    rank = {name: index for index, name in enumerate(ROLE_PRIORITY)}
    known = [name for name in names if name in rank]
    extra = [name for name in names if name not in rank]
    known.sort(key=lambda name: rank[name])
    extra.sort()
    return known + extra


def primary_role_label(user: User) -> str:
    if getattr(user, "is_superuser", False):
        return SUPERADMIN_LABEL
    for name in ordered_role_names(user):
        label = ROLE_LABELS.get(name)
        if label:
            return label
    return ROLE_LABELS[AGENT]
