"""Permission catalog, capability evaluator, and fail-closed matrix tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied

from apps.user.models import Office, User
from apps.user.roles import (
    BRANCH_MANAGER,
    REALTOR,
    ROLE_DEFINITIONS,
    SYSTEM_ADMIN,
    ScopeType,
    role_group_name,
    seed_brokerage_roles,
)
from apps.user.services.role_assignments import (
    create_role_assignment,
    get_effective_access,
    has_effective_permission,
)
from apps.web.authorization import NON_ROUTE_SURFACES, ROUTE_POLICIES, _has_permissions
from apps.web.capability import (
    evaluate_permission,
    has_capability,
    matches_permission_check,
    require_permission,
)
from apps.web.operations import OPERATIONS_DESTINATIONS
from apps.web.permission_catalog import (
    CATALOG_CODENAMES,
    CATALOG_VERSION,
    PERMISSION_DEFINITIONS,
    is_cataloged_permission,
    permissions_for_role,
)
from apps.web.shell import authorization_version


def _user(email: str) -> User:
    return User.objects.create_user(email=email, profile_completed=True)


def _superuser(email: str) -> User:
    return User.objects.create_superuser(email=email, password="x")


def _branch() -> Office:
    office = Office.assignable_queryset().filter(kind=Office.Kind.BRANCH).first()
    assert office is not None
    return office


@pytest.mark.django_db
def test_catalog_covers_role_default_permissions():
    missing = {
        permission
        for definition in ROLE_DEFINITIONS
        for permission in definition.default_permissions
        if permission not in CATALOG_CODENAMES
    }
    assert missing == set()


@pytest.mark.django_db
def test_catalog_covers_operations_and_policy_permissions():
    referenced = {destination.permission for destination in OPERATIONS_DESTINATIONS}
    referenced.add("web.manage_new_agent_onboarding")
    for policy in list(ROUTE_POLICIES.values()) + list(NON_ROUTE_SURFACES):
        referenced.update(policy.any_permissions)
        referenced.update(policy.all_permissions)
    missing = referenced - CATALOG_CODENAMES
    assert missing == set()


def test_catalog_codenames_are_unique_and_versioned():
    codenames = [item.codename for item in PERMISSION_DEFINITIONS]
    assert len(codenames) == len(set(codenames))
    assert CATALOG_VERSION
    assert all("." in item.codename for item in PERMISSION_DEFINITIONS)


@pytest.mark.django_db
def test_unknown_permission_fails_closed():
    user = _user("agent@example.com")
    assert not is_cataloged_permission("web.not_a_real_permission")
    assert not has_capability(user, "web.not_a_real_permission")
    assert not has_effective_permission(user, "web.not_a_real_permission")
    assert not matches_permission_check(
        user, all_permissions=("web.not_a_real_permission",)
    )
    assert not _has_permissions(user, (), ("web.not_a_real_permission",))
    decision = evaluate_permission(user, "web.not_a_real_permission")
    assert decision.denied
    assert decision.reason == "unknown_permission"


@pytest.mark.django_db
def test_missing_scope_context_fails_closed_for_scoped_permission():
    seed_brokerage_roles(sync_permissions=True)
    user = _user("manager@example.com")
    group = Group.objects.get(name=role_group_name(BRANCH_MANAGER))
    user.groups.add(group)
    assert has_capability(user, "web.view_users")
    decision = evaluate_permission(user, "web.view_users")
    assert decision.denied
    assert decision.reason == "missing_scope_context"


@pytest.mark.django_db
def test_scoped_permission_allows_in_scope_office():
    seed_brokerage_roles(sync_permissions=True)
    actor = _superuser("admin-actor@example.com")
    user = _user("bm@example.com")
    office = _branch()
    create_role_assignment(
        actor=actor,
        target_user=user,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )
    decision = evaluate_permission(user, "web.view_users", office=office)
    assert decision.allowed
    assert decision.reason == "ok"


@pytest.mark.django_db
def test_system_admin_is_not_superuser_shortcut():
    """System Admin without a grant is denied; superuser is break-glass."""
    seed_brokerage_roles(sync_permissions=True)
    actor = _superuser("grantor@example.com")
    admin = _user("sysadmin@example.com")
    group = Group.objects.get(name=role_group_name(SYSTEM_ADMIN))
    perm = Permission.objects.get(
        content_type__app_label="web",
        content_type__model="operationspermission",
        codename="assign_user_roles",
    )
    group.permissions.remove(perm)
    create_role_assignment(
        actor=actor,
        target_user=admin,
        role=SYSTEM_ADMIN,
        scope_type=ScopeType.COMPANY,
    )
    assert not has_capability(admin, "web.assign_user_roles")

    break_glass = _superuser("root@example.com")
    assert has_capability(break_glass, "web.assign_user_roles")


@pytest.mark.django_db
def test_permission_matrix_realtor_vs_branch_manager():
    seed_brokerage_roles(sync_permissions=True)
    actor = _superuser("matrix-actor@example.com")
    office = _branch()

    realtor = _user("realtor@example.com")
    create_role_assignment(
        actor=actor,
        target_user=realtor,
        role=REALTOR,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )
    manager = _user("branch-mgr@example.com")
    create_role_assignment(
        actor=actor,
        target_user=manager,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )

    assert has_capability(realtor, "web.view_own_tasks")
    assert not has_capability(realtor, "web.view_users")
    assert has_capability(manager, "web.view_users")
    assert has_capability(manager, "web.view_own_tasks")
    assert "web.view_users" in permissions_for_role(BRANCH_MANAGER)
    assert "web.view_users" not in permissions_for_role(REALTOR)


@pytest.mark.django_db
def test_effective_access_filters_uncatalogued_permissions():
    user = _user("direct@example.com")
    user.user_permissions.add(Permission.objects.get(codename="view_user"))
    extra = Permission.objects.filter(
        content_type__app_label="auth", codename="change_permission"
    ).first()
    assert extra is not None
    user.user_permissions.add(extra)
    access = get_effective_access(user)
    assert "user.view_user" in access.permissions
    assert "auth.change_permission" not in access.permissions


@pytest.mark.django_db
def test_authorization_version_changes_when_permissions_change():
    seed_brokerage_roles(sync_permissions=True)
    actor = _superuser("ver-actor@example.com")
    user = _user("ver-user@example.com")
    office = _branch()
    create_role_assignment(
        actor=actor,
        target_user=user,
        role=REALTOR,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )
    before = authorization_version(get_effective_access(user))
    create_role_assignment(
        actor=actor,
        target_user=user,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )
    after = authorization_version(get_effective_access(user))
    assert before != after


@pytest.mark.django_db
def test_require_permission_raises_on_deny():
    user = _user("denied@example.com")
    with pytest.raises(PermissionDenied):
        require_permission(user, "web.view_users", require_scope=False)
