"""Brokerage role catalog: seed, scopes, permissions, and assignment policy."""

from importlib import import_module

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError

from apps.user.models import BrokerageRole, User, UserRoleAssignment
from apps.user.roles import (
    BRANCH_MANAGER,
    BROKER_ADMIN,
    PRINCIPAL_BROKER,
    REALTOR,
    REQUIRED_ROLE_CODES,
    ROLE_DEFINITIONS,
    ROLE_LABELS,
    SYSTEM_ADMIN,
    ScopeType,
    is_role_assignable,
    is_valid_scope_type,
    normalize_role_code,
    role_assignment_block_reason,
    role_group_name,
    seed_brokerage_roles,
)
from apps.user.services.role_assignments import (
    actor_can_manage_assignments,
    create_role_assignment,
)
from apps.user.tests.test_onboarding import assignable_office

backfill = import_module(
    "apps.user.migrations.0017_brokerage_role_catalog"
).seed_and_remap_roles


@pytest.mark.django_db
def test_catalog_has_fourteen_stable_codes():
    assert len(ROLE_DEFINITIONS) == 14
    assert len(REQUIRED_ROLE_CODES) == 14
    assert {item.code for item in ROLE_DEFINITIONS} == REQUIRED_ROLE_CODES


@pytest.mark.django_db
def test_seed_brokerage_roles_is_idempotent_and_preserves_deactivation():
    seed_brokerage_roles(sync_presentation=True)
    assert BrokerageRole.objects.count() == 14
    assert (
        set(BrokerageRole.objects.values_list("code", flat=True)) == REQUIRED_ROLE_CODES
    )

    row = BrokerageRole.objects.get(code=BRANCH_MANAGER)
    row.is_assignable = False
    row.is_active = False
    row.display_name = "Custom branch title"
    row.save(update_fields=["is_assignable", "is_active", "display_name", "updated_at"])

    seed_brokerage_roles(sync_presentation=False)
    row.refresh_from_db()
    assert row.is_assignable is False
    assert row.is_active is False
    assert row.display_name == "Custom branch title"
    assert not is_role_assignable(BRANCH_MANAGER)

    seed_brokerage_roles(sync_presentation=True)
    row.refresh_from_db()
    assert row.display_name == ROLE_LABELS[BRANCH_MANAGER]
    assert row.is_assignable is False


@pytest.mark.django_db
def test_role_permission_bundles_and_scope_policies():
    seed_brokerage_roles(sync_permissions=True)
    for definition in ROLE_DEFINITIONS:
        group = Group.objects.get(name=definition.group_name)
        granted = {
            f"{app}.{codename}"
            for app, codename in group.permissions.values_list(
                "content_type__app_label", "codename"
            )
            if app and codename
        }
        for permission in definition.default_permissions:
            assert permission in granted, f"{definition.code} missing {permission}"
        for scope in definition.valid_scope_types:
            assert is_valid_scope_type(definition.code, scope)
        assert not is_valid_scope_type(
            definition.code,
            next(
                value
                for value, _label in ScopeType.CHOICES
                if value not in definition.valid_scope_types
            ),
        )


@pytest.mark.django_db
def test_normalize_legacy_role_strings():
    assert normalize_role_code("Admins") == SYSTEM_ADMIN
    assert normalize_role_code("Users") == REALTOR
    assert normalize_role_code("Branch Managers") == BRANCH_MANAGER
    assert normalize_role_code(SYSTEM_ADMIN) == SYSTEM_ADMIN
    assert normalize_role_code("not-a-role") is None


@pytest.mark.django_db
def test_display_name_change_does_not_change_code_behavior():
    seed_brokerage_roles()
    row = BrokerageRole.objects.get(code=REALTOR)
    row.display_name = "Sales Associate"
    row.save(update_fields=["display_name", "updated_at"])
    assert normalize_role_code(REALTOR) == REALTOR
    assert is_valid_scope_type(REALTOR, ScopeType.OFFICE)
    assert role_group_name(REALTOR) == "Users"


@pytest.mark.django_db
def test_protected_roles_cannot_be_delegated_by_broker_admin():
    seed_brokerage_roles()
    office = assignable_office()
    actor = User.objects.create_user(email="broker-admin@example.com", office=office)
    Group.objects.get(name=role_group_name(BROKER_ADMIN)).user_set.add(actor)
    create_role_assignment(
        actor=User.objects.create_superuser(email="root@example.com", password="x"),
        target_user=actor,
        role=BROKER_ADMIN,
        scope_type=ScopeType.COMPANY,
    )

    assert not actor_can_manage_assignments(
        actor,
        role=SYSTEM_ADMIN,
        target_scope_type=ScopeType.COMPANY,
        scope_office=None,
    )
    assert not actor_can_manage_assignments(
        actor,
        role=PRINCIPAL_BROKER,
        target_scope_type=ScopeType.COMPANY,
        scope_office=None,
    )
    assert role_assignment_block_reason(SYSTEM_ADMIN, actor_is_superuser=False)
    assert actor_can_manage_assignments(
        actor,
        role=BRANCH_MANAGER,
        target_scope_type=ScopeType.OFFICE,
        scope_office=office,
    )


@pytest.mark.django_db
def test_self_escalation_and_deactivated_role_blocked():
    seed_brokerage_roles()
    office = assignable_office()
    actor = User.objects.create_superuser(email="root@example.com", password="x")
    target = User.objects.create_user(email="agent@example.com", office=office)

    with pytest.raises(PermissionDenied):
        create_role_assignment(
            actor=target,
            target_user=target,
            role=BRANCH_MANAGER,
            scope_type=ScopeType.OFFICE,
            scope_office=office,
        )

    BrokerageRole.objects.filter(code=BRANCH_MANAGER).update(
        is_assignable=False, is_active=False
    )
    with pytest.raises(ValidationError, match="deactivated"):
        create_role_assignment(
            actor=actor,
            target_user=target,
            role=BRANCH_MANAGER,
            scope_type=ScopeType.OFFICE,
            scope_office=office,
        )


@pytest.mark.django_db
def test_system_role_delete_blocked_when_referenced():
    seed_brokerage_roles()
    office = assignable_office()
    actor = User.objects.create_superuser(email="root@example.com", password="x")
    target = User.objects.create_user(email="agent@example.com", office=office)
    create_role_assignment(
        actor=actor,
        target_user=target,
        role=REALTOR,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )
    row = BrokerageRole.objects.get(code=REALTOR)
    with pytest.raises(ValidationError, match="historical"):
        row.delete()


@pytest.mark.django_db
def test_migration_remaps_legacy_assignment_role_strings(django_user_model=None):
    seed_brokerage_roles()
    office = assignable_office()
    user = User.objects.create_user(email="legacy@example.com", office=office)
    assignment = UserRoleAssignment.objects.create(
        user=user,
        role="Branch Managers",
        scope_type=ScopeType.OFFICE,
        scope_office=office,
        status=UserRoleAssignment.Status.ACTIVE,
    )
    # Bypass clean() normalization so we simulate pre-migration data.
    UserRoleAssignment.objects.filter(pk=assignment.pk).update(role="Branch Managers")

    from django.apps import apps as django_apps

    backfill(django_apps, None)
    assignment.refresh_from_db()
    assert assignment.role == BRANCH_MANAGER
