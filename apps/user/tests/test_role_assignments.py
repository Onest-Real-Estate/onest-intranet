from importlib import import_module
from typing import Any

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.query import query_audit_events
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import (
    Office,
    User,
    UserRoleAssignment,
    UserRoleAssignmentMigrationConflict,
)
from apps.user.office_seed import seed_offices
from apps.user.roles import ADMIN, AGENT, BRANCH_MANAGER, REGION_MANAGER, ScopeType
from apps.user.services.role_assignments import (
    create_role_assignment,
    get_effective_access,
    get_effective_permissions,
    revoke_role_assignment,
    update_role_assignment,
)
from apps.user.tests.test_onboarding import assignable_office

backfill_role_assignments = import_module(
    "apps.user.migrations.0009_user_role_assignments"
).backfill_role_assignments


@pytest.mark.django_db
def test_create_role_assignment_records_active_scoped_role():
    actor = User.objects.create_superuser(email="admin@example.com", password="x")
    user = User.objects.create_user(
        email="agent@example.com", office=assignable_office()
    )

    assignment = create_role_assignment(
        actor=actor,
        target_user=user,
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office=user.office,
        business_reason="Primary office assignment",
    )

    assert assignment.status == UserRoleAssignment.Status.ACTIVE
    assert assignment.assigned_by == actor
    assert assignment.scope_office == user.office


@pytest.mark.django_db(transaction=True)
def test_duplicate_live_assignment_is_rejected():
    actor = User.objects.create_superuser(email="admin@example.com", password="x")
    with transaction.atomic():
        seed_offices()
    office = assignable_office()
    user = User.objects.create_user(email="agent@example.com", office=office)
    create_role_assignment(
        actor=actor,
        target_user=user,
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )

    with pytest.raises(ValidationError, match="already exists"):
        create_role_assignment(
            actor=actor,
            target_user=user,
            role=AGENT,
            scope_type=ScopeType.OFFICE,
            scope_office=office,
        )


@pytest.mark.django_db
def test_scheduled_and_expired_assignments_do_not_grant_access():
    actor = User.objects.create_superuser(email="admin@example.com", password="x")
    office = assignable_office()
    user = User.objects.create_user(email="agent@example.com", office=office)
    future = timezone.now() + timezone.timedelta(days=2)
    past = timezone.now() - timezone.timedelta(days=2)

    scheduled = create_role_assignment(
        actor=actor,
        target_user=user,
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
        starts_at=future,
    )
    expired = create_role_assignment(
        actor=actor,
        target_user=user,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
        starts_at=past - timezone.timedelta(days=3),
        ends_at=past,
    )
    expired = update_role_assignment(
        actor=actor,
        assignment=expired,
        starts_at=expired.starts_at,
        ends_at=expired.ends_at,
        business_reason=expired.business_reason,
    )

    scheduled.refresh_from_db()
    assert scheduled.status == UserRoleAssignment.Status.SCHEDULED
    assert expired.status == UserRoleAssignment.Status.EXPIRED
    assert get_effective_access(user).assignments == ()


@pytest.mark.django_db
def test_effective_permissions_union_mixed_roles_and_scopes():
    actor = User.objects.create_superuser(email="admin@example.com", password="x")
    office = assignable_office()
    region = office.region
    assert region is not None

    admin_group = Group.objects.get_or_create(name=ADMIN)[0]
    branch_group = Group.objects.get_or_create(name=BRANCH_MANAGER)[0]
    admin_group.permissions.add(Permission.objects.get(codename="view_user"))
    branch_group.permissions.add(
        Permission.objects.get(codename="can_view_audit_events")
    )

    user = User.objects.create_user(email="manager@example.com", office=office)
    create_role_assignment(
        actor=actor,
        target_user=user,
        role=ADMIN,
        scope_type=ScopeType.COMPANY,
    )
    create_role_assignment(
        actor=actor,
        target_user=user,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )
    create_role_assignment(
        actor=actor,
        target_user=user,
        role=REGION_MANAGER,
        scope_type=ScopeType.REGION,
        scope_office=region,
    )

    permissions = get_effective_permissions(user)
    access = get_effective_access(user)

    assert "user.view_user" in permissions
    assert "audit.can_view_audit_events" in permissions
    assert access.company_wide is True
    assert office.stable_key in access.office_keys
    assert region.stable_key in access.region_keys


@pytest.mark.django_db
def test_office_assignment_does_not_promote_access_to_the_parent_region():
    actor = User.objects.create_superuser(email="admin@example.com", password="x")
    office = assignable_office()
    manager = User.objects.create_user(email="branch@example.com", office=office)
    create_role_assignment(
        actor=actor,
        target_user=manager,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )

    access = get_effective_access(manager)

    assert access.office_keys == frozenset({office.stable_key})
    assert access.region_keys == frozenset()


@pytest.mark.django_db
def test_self_revocation_of_last_management_role_is_blocked():
    office = assignable_office()
    actor = User.objects.create_user(email="manager@example.com", office=office)
    assignment = UserRoleAssignment.objects.create(
        user=actor,
        role=ADMIN,
        scope_type=ScopeType.COMPANY,
        status=UserRoleAssignment.Status.ACTIVE,
    )

    with pytest.raises(ValidationError, match="last management role"):
        revoke_role_assignment(actor=actor, assignment=assignment)


@pytest.mark.django_db
def test_assignment_scope_drives_audit_union_queries():
    actor = User.objects.create_superuser(email="admin@example.com", password="x")
    office = assignable_office()
    other_office = Office.objects.get(slug="fairfax-va")
    manager = User.objects.create_user(email="manager@example.com", office=office)
    manager.user_permissions.add(
        Permission.objects.get(codename="can_view_audit_events")
    )
    create_role_assignment(
        actor=actor,
        target_user=manager,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    )
    create_role_assignment(
        actor=actor,
        target_user=manager,
        role=REGION_MANAGER,
        scope_type=ScopeType.REGION,
        scope_office=office.region,
    )
    local = log_event(
        "office.local",
        actor=actor_from_user(manager),
        target=AuditTarget(target_type="office", target_id=office.stable_key),
        office_id=office.stable_key,
        region_id=office.region.stable_key if office.region else "",
    )
    regional = log_event(
        "office.regional",
        actor=actor_from_user(manager),
        target=AuditTarget(target_type="office", target_id=other_office.stable_key),
        office_id=other_office.stable_key,
        region_id=other_office.region.stable_key if other_office.region else "",
    )
    outside = log_event(
        "office.outside",
        actor=actor_from_user(manager),
        target=AuditTarget(target_type="office", target_id="outside"),
        office_id="outside",
        region_id="outside",
    )

    events = list(query_audit_events(manager))

    assert local in events
    assert regional in events
    assert outside not in events


@pytest.mark.django_db
def test_backfill_creates_assignments_and_conflicts_for_invalid_legacy_scopes():
    agent_group = Group.objects.get_or_create(name=AGENT)[0]
    region_group = Group.objects.get_or_create(name=REGION_MANAGER)[0]
    office = assignable_office()
    valid_user = User.objects.create_user(email="valid@example.com", office=office)
    invalid_user = User.objects.create_user(email="invalid@example.com")
    valid_user.groups.add(agent_group)
    invalid_user.groups.add(region_group)

    backfill_role_assignments(apps=django_apps, schema_editor=None)

    assert UserRoleAssignment.objects.filter(
        user=valid_user,
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office=office,
    ).exists()
    assert UserRoleAssignmentMigrationConflict.objects.filter(
        user=invalid_user,
        legacy_role=REGION_MANAGER,
    ).exists()


@pytest.mark.django_db
def test_non_superuser_cannot_self_assign_protected_role():
    office = assignable_office()
    actor = User.objects.create_user(email="actor@example.com", office=office)

    with pytest.raises(PermissionDenied):
        create_role_assignment(
            actor=actor,
            target_user=actor,
            role=ADMIN,
            scope_type=ScopeType.COMPANY,
        )


# ---------------------------------------------------------------------------
# Row locking must be valid SQL on the database we actually deploy to
# ---------------------------------------------------------------------------


def test_assignment_lock_compiles_to_valid_postgresql(monkeypatch):
    """PostgreSQL rejects ``FOR UPDATE`` over the nullable side of an outer join.

    Local pytest and CI both run on SQLite, which drops row locking entirely,
    so this compiles the real production queryset with the PostgreSQL compiler
    rather than waiting for a deployed request to fail. Building the wrapper
    directly never opens a socket — ``as_sql()`` only reads the backend's
    operations and feature flags.
    """
    from django.db.backends.postgresql.base import DatabaseWrapper

    from apps.user.services.role_assignments import locked_assignment_queryset

    # django-stubs types settings_dict too narrowly for a literal like this.
    settings_dict: Any = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "compile-only",
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "OPTIONS": {},
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "AUTOCOMMIT": True,
        "ATOMIC_REQUESTS": False,
        "TIME_ZONE": None,
        "TEST": {},
    }
    postgres = DatabaseWrapper(settings_dict, alias="pg_compile_only")
    # The compiler refuses to emit FOR UPDATE outside a transaction, and
    # answering that question is the one thing here that would need a socket.
    monkeypatch.setattr(postgres, "get_autocommit", lambda: False)

    queryset = locked_assignment_queryset().filter(pk=1)
    sql, _params = queryset.query.get_compiler(connection=postgres).as_sql()

    # The outer join onto the nullable scope_office is what makes an
    # unqualified FOR UPDATE illegal here.
    assert "LEFT OUTER JOIN" in sql
    assert 'FOR UPDATE OF "user_userroleassignment"' in sql
    assert not sql.rstrip().endswith("FOR UPDATE")
