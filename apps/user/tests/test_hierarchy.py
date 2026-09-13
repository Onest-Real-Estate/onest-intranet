"""Organization hierarchy service and membership history."""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditEvent
from apps.user.models import Office, User, UserOfficeMembership
from apps.user.roles import AGENT, ScopeType
from apps.user.services.hierarchy import (
    ancestors,
    breadcrumb_segments,
    brokerage_root,
    descendant_ids,
    grant_secondary_membership,
    hierarchy_inconsistency,
    is_hierarchy_consistent,
    organization_snapshot,
    primary_region,
    sync_primary_membership,
    transfer_office,
)
from apps.user.services.role_assignments import (
    create_role_assignment,
    get_effective_access,
)


@pytest.fixture
def branch():
    return Office.objects.get(slug="charlottesville-va")


@pytest.fixture
def other_branch():
    return Office.objects.get(slug="fairfax-va")


@pytest.fixture
def actor(branch):
    user = User.objects.create_user(email="broker@example.com", office=branch)
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    return user


@pytest.mark.django_db
def test_brokerage_root_is_head_office():
    root = brokerage_root()
    assert root.kind == Office.Kind.HEAD_OFFICE
    assert root.parent is None


@pytest.mark.django_db
def test_ancestors_are_root_first(branch):
    path = [node.slug for node in ancestors(branch)]
    assert path[0] == "onest-head-office"
    assert path[-1] == "charlottesville-va"
    assert "region-mid-atlantic" in path


@pytest.mark.django_db
def test_descendants_include_self_and_children():
    region = Office.objects.get(slug="region-mid-atlantic")
    ids = descendant_ids(region)
    assert region.pk in ids
    assert Office.objects.get(slug="charlottesville-va").pk in ids
    assert Office.objects.get(slug="connecticut").pk not in ids


@pytest.mark.django_db
def test_breadcrumb_and_snapshot(branch):
    crumbs = breadcrumb_segments(branch)
    assert crumbs[0]["name"] == "Onest Real Estate"
    assert crumbs[-1]["name"] == "Charlottesville VA"
    snap = organization_snapshot(branch)
    assert snap is not None
    assert snap["officeStableKey"] == branch.stable_key
    assert snap["regionStableKey"] == "region-mid-atlantic"
    assert snap["pathLabel"].endswith("Charlottesville VA")


@pytest.mark.django_db
def test_primary_region_derives_from_office(branch):
    user = User.objects.create_user(email="agent@example.com", office=branch)
    region = primary_region(user)
    assert region is not None
    assert region.slug == "region-mid-atlantic"


@pytest.mark.django_db
def test_sync_primary_membership_creates_and_transfers(actor, branch, other_branch):
    user = User.objects.create_user(email="mover@example.com", office=branch)
    first = sync_primary_membership(user, actor=actor, business_reason="Initial seat")
    assert first is not None
    assert first.kind == UserOfficeMembership.Kind.PRIMARY
    assert first.status == UserOfficeMembership.Status.ACTIVE
    assert first.office.pk == branch.pk

    user.office = other_branch
    user.save(update_fields=["office"])
    second = sync_primary_membership(
        user, actor=actor, business_reason="Transferred to Fairfax"
    )
    first.refresh_from_db()
    assert first.status == UserOfficeMembership.Status.ENDED
    assert first.ends_on == dt.date.today()
    assert second is not None
    assert second.office.pk == other_branch.pk
    assert (
        UserOfficeMembership.objects.filter(
            user=user, kind="primary", status="active"
        ).count()
        == 1
    )
    assert AuditEvent.objects.filter(action="user.office_membership.created").exists()


@pytest.mark.django_db
def test_secondary_membership_does_not_change_primary(actor, branch, other_branch):
    user = User.objects.create_user(email="dual@example.com", office=branch)
    sync_primary_membership(user, actor=actor)
    secondary = grant_secondary_membership(
        actor=actor,
        user=user,
        office=other_branch,
        business_reason="Coverage desk",
    )
    user.refresh_from_db()
    assert user.office == branch
    assert secondary.kind == UserOfficeMembership.Kind.SECONDARY
    with pytest.raises(ValidationError):
        grant_secondary_membership(actor=actor, user=user, office=branch)


@pytest.mark.django_db
def test_overlapping_secondary_rejected(actor, branch, other_branch):
    user = User.objects.create_user(email="overlap@example.com", office=branch)
    grant_secondary_membership(actor=actor, user=user, office=other_branch)
    with pytest.raises(ValidationError):
        grant_secondary_membership(actor=actor, user=user, office=other_branch)


@pytest.mark.django_db
def test_transfer_office_requires_brokerage_admin(branch):
    regional = Office.objects.get(slug="ro-pennsylvania")
    agent = User.objects.create_user(email="agent@example.com", office=branch)
    with pytest.raises(PermissionDenied):
        transfer_office(
            actor=agent,
            office=branch,
            new_parent=regional,
            business_reason="Nope",
        )


@pytest.mark.django_db
def test_transfer_office_moves_branch_and_refreshes_region(actor, branch):
    pennsylvania = Office.objects.get(slug="ro-pennsylvania")
    before_region = branch.region.stable_key
    moved = transfer_office(
        actor=actor,
        office=branch,
        new_parent=pennsylvania,
        business_reason="Market realignment",
    )
    moved.refresh_from_db()
    assert moved.parent == pennsylvania
    assert moved.region is not None
    assert moved.region.stable_key == "region-mid-atlantic"
    assert before_region == "region-mid-atlantic"
    assert AuditEvent.objects.filter(action="user.office.transferred").exists()
    # Restore seed shape for later tests in the same DB session.
    virginia = Office.objects.get(slug="ro-virginia")
    transfer_office(
        actor=actor,
        office=moved,
        new_parent=virginia,
        business_reason="Restore fixture",
    )


@pytest.mark.django_db
def test_inconsistent_scope_office_fails_closed(branch):
    user = User.objects.create_user(email="scoped@example.com", office=branch)
    admin = User.objects.create_user(email="admin@example.com", office=branch)
    admin.is_superuser = True
    admin.save(update_fields=["is_superuser"])
    create_role_assignment(
        actor=admin,
        target_user=user,
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office=branch,
    )
    access = get_effective_access(user)
    assert branch.stable_key in access.office_keys

    # Clear the denormalized region without clean()/save() — fail closed.
    Office.objects.filter(pk=branch.pk).update(region=None)
    broken = Office.objects.select_related("region", "parent").get(pk=branch.pk)
    assert not is_hierarchy_consistent(broken)
    assert hierarchy_inconsistency(broken) is not None
    # Fresh instance ≈ fresh request: effective access is memoized on the user
    # instance for the request's lifetime, so re-resolving after the hierarchy
    # break must go through a newly fetched user.
    access_after = get_effective_access(User.objects.get(pk=user.pk))
    assert branch.stable_key not in access_after.office_keys
    # Restore for other tests sharing the DB.
    Office.objects.filter(pk=branch.pk).update(
        region=Office.objects.get(slug="region-mid-atlantic")
    )


@pytest.mark.django_db
def test_migration_backfill_creates_primary_for_existing_users(branch):
    user = User.objects.create_user(email="legacy@example.com", office=branch)
    # Simulate pre-migration state: office set, no membership row.
    UserOfficeMembership.objects.filter(user=user).delete()
    sync_primary_membership(user, business_reason="Repair")
    assert UserOfficeMembership.objects.filter(
        user=user, kind="primary", status="active", office=branch
    ).exists()
