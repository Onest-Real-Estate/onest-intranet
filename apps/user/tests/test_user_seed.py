import pytest

from apps.user.models import User, UserRoleAssignment
from apps.user.office_seed import seed_offices
from apps.user.roles import (
    ADMIN,
    AGENT,
    BRANCH_MANAGER,
    REGION_MANAGER,
    ScopeType,
    role_group_name,
)
from apps.user.user_seed import (
    DEV_USER_SPECS,
    DEV_USER_TEMPLATES,
    STAFF_SEED_SPECS,
    UserSeedSpec,
    build_user_specs,
    seed_users,
)

EXPECTED_SEED_USERS = len(DEV_USER_TEMPLATES) + len(STAFF_SEED_SPECS)


@pytest.mark.django_db
def test_seed_users_creates_demo_accounts_with_roles():
    report = seed_users(password="test-seed-password")

    assert len(report.created) == EXPECTED_SEED_USERS
    assert User.objects.filter(email="admin@onest.test").exists()
    assert User.objects.filter(email="agent.fairfax@onest.test").exists()

    admin = User.objects.get(email="admin@onest.test")
    assert admin.display_name == f"{admin.first_name} {admin.last_name}"
    assert admin.first_name
    assert admin.last_name
    assert admin.street_address
    assert admin.city
    assert admin.state
    assert admin.zip_code
    assert admin.profile_completed is True
    assert admin.office.slug == "onest-head-office"

    assignment = UserRoleAssignment.objects.get(
        user=admin,
        role=ADMIN,
        scope_type=ScopeType.COMPANY,
    )
    assert assignment.status == UserRoleAssignment.Status.ACTIVE


@pytest.mark.django_db
def test_build_user_specs_is_deterministic_for_seed():
    first = build_user_specs(seed=99)
    second = build_user_specs(seed=99)
    assert first == second
    assert first[0].first_name != first[1].first_name


@pytest.mark.django_db
def test_seed_users_region_and_branch_scopes():
    seed_users(password="test-seed-password")

    region_manager = User.objects.get(email="region.midatlantic@onest.test")
    region_assignment = UserRoleAssignment.objects.get(
        user=region_manager,
        role=REGION_MANAGER,
    )
    assert region_assignment.scope_office is not None
    assert region_assignment.scope_office.slug == "region-mid-atlantic"

    branch_manager = User.objects.get(email="branch.charlottesville@onest.test")
    branch_assignment = UserRoleAssignment.objects.get(
        user=branch_manager,
        role=BRANCH_MANAGER,
    )
    assert branch_assignment.scope_office is not None
    assert branch_assignment.scope_office.slug == "charlottesville-va"


@pytest.mark.django_db
def test_seed_users_is_idempotent():
    first = seed_users(password="test-seed-password")
    second = seed_users(password="test-seed-password")

    assert len(first.created) == EXPECTED_SEED_USERS
    assert second.created == []
    assert len(second.matched) == EXPECTED_SEED_USERS
    assert second.assignments_created == []
    assert len(second.assignments_matched) == EXPECTED_SEED_USERS - 1
    assert second.contacts_created == []


@pytest.mark.django_db
def test_seed_users_requires_offices_when_prerequisites_skipped():
    missing_office_spec = UserSeedSpec(
        email="missing.office@onest.test",
        first_name="No",
        last_name="Office",
        display_name="No Office",
        office_slug="does-not-exist",
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="does-not-exist",
    )
    with pytest.raises(RuntimeError, match="seed_offices"):
        seed_users(
            ensure_prerequisites=False,
            specs=(missing_office_spec,),
            password="test-seed-password",
        )


@pytest.mark.django_db
def test_seed_users_with_existing_offices():
    seed_offices()
    report = seed_users(ensure_prerequisites=False, password="test-seed-password")
    assert len(report.created) == EXPECTED_SEED_USERS


@pytest.mark.django_db
def test_seed_users_agent_has_group_membership():
    seed_users(password="test-seed-password")
    agent = User.objects.get(email="agent.charlottesville@onest.test")
    assert list(agent.groups.values_list("name", flat=True)) == [role_group_name(AGENT)]


def test_dev_user_specs_matches_default_seed():
    assert build_user_specs() == DEV_USER_SPECS
