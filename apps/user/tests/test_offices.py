import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.user.models import Office, OfficeContactAssignment, User
from apps.user.office_payloads import (
    office_internal_payload,
    office_selector_payload,
    office_summary_payload,
)
from apps.user.office_seed import SeedConflictError, seed_offices

# ---------------------------------------------------------------------------
# Core seed correctness
# ---------------------------------------------------------------------------

EXPECTED_ASSIGNABLE = {
    "Onest Real Estate",
    "Charlottesville VA",
    "Connecticut",
    "District of Columbia",
    "Fairfax VA",
    "Harrisburg",
    "Maryland",
    "Massachusetts",
    "New Hampshire",
    "Philadelphia",
    "Pittsburgh",
    "Rhode Island",
}

EXPECTED_SLUGS = {
    "onest-head-office",
    "charlottesville-va",
    "connecticut",
    "district-of-columbia",
    "fairfax-va",
    "harrisburg",
    "maryland",
    "massachusetts",
    "new-hampshire",
    "philadelphia",
    "pittsburgh",
    "rhode-island",
}


@pytest.mark.django_db
def test_seed_creates_current_markets():
    names = set(
        Office.objects.filter(is_assignable=True).values_list("name", flat=True)
    )
    assert names >= EXPECTED_ASSIGNABLE
    # Grouping nodes are not pickable work locations.
    assert "Mid-Atlantic" not in names
    assert "Virginia" not in names
    assert "Pennsylvania" not in names
    assert "New England" not in names


@pytest.mark.django_db
def test_seed_canonical_slugs_exist():
    slugs = set(Office.objects.values_list("slug", flat=True))
    assert slugs >= EXPECTED_SLUGS


@pytest.mark.django_db
def test_existing_offices_backfilled_with_stable_keys():
    stable_keys = set(Office.objects.values_list("stable_key", flat=True))
    assert "charlottesville-va" in stable_keys
    assert "region-mid-atlantic" in stable_keys


@pytest.mark.django_db
def test_seed_display_names_exact():
    """Display names must match the approved list character-for-character."""
    for slug, expected_name in [
        ("charlottesville-va", "Charlottesville VA"),
        ("connecticut", "Connecticut"),
        ("district-of-columbia", "District of Columbia"),
        ("fairfax-va", "Fairfax VA"),
        ("harrisburg", "Harrisburg"),
        ("maryland", "Maryland"),
        ("massachusetts", "Massachusetts"),
        ("new-hampshire", "New Hampshire"),
        ("philadelphia", "Philadelphia"),
        ("pittsburgh", "Pittsburgh"),
        ("rhode-island", "Rhode Island"),
    ]:
        office = Office.objects.get(slug=slug)
        assert office.name == expected_name, (
            f"Slug '{slug}': expected name '{expected_name}', got '{office.name}'"
        )


@pytest.mark.django_db
def test_seed_deterministic_sort_order():
    """assignable_queryset must return offices in a stable, deterministic order."""
    first_run = list(Office.assignable_queryset().values_list("slug", flat=True))
    second_run = list(Office.assignable_queryset().values_list("slug", flat=True))
    assert first_run == second_run
    assert len(first_run) > 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_is_idempotent_count():
    count = Office.objects.count()
    seed_offices()
    assert Office.objects.count() == count


@pytest.mark.django_db
def test_seed_is_idempotent_report():
    report = seed_offices()
    assert report.created == []
    assert len(report.matched) > 0
    assert report.conflicting == []


@pytest.mark.django_db
def test_seed_twice_no_new_records():
    seed_offices()
    seed_offices()
    count_after_two = Office.objects.count()
    seed_offices()
    assert Office.objects.count() == count_after_two


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_conflict_on_wrong_name():
    """A slug that already belongs to a record with a different name must raise."""
    office = Office.objects.get(slug="charlottesville-va")
    office.name = "RENAMED OFFICE"
    office.save()

    with pytest.raises(SeedConflictError, match="charlottesville-va"):
        seed_offices()


@pytest.mark.django_db
def test_seed_conflict_on_wrong_kind():
    """A slug with the correct name but wrong kind is also a conflict."""
    office = Office.objects.get(slug="charlottesville-va")
    # Change kind to something the seed doesn't expect.
    office.kind = Office.Kind.REGIONAL_OFFICE
    office.save()

    with pytest.raises(SeedConflictError, match="charlottesville-va"):
        seed_offices()


# ---------------------------------------------------------------------------
# Extra/unlisted offices are preserved
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_extra_offices_preserved():
    """Offices not in the seed list must survive a seed run."""
    extra = Office.objects.create(
        slug="future-market",
        name="Future Market",
        kind=Office.Kind.BRANCH,
        parent=Office.objects.get(slug="ro-pennsylvania"),
        is_active=True,
        sort_order=99,
    )
    seed_offices()
    assert Office.objects.filter(slug="future-market").exists()
    extra.refresh_from_db()
    assert extra.name == "Future Market"


# ---------------------------------------------------------------------------
# Inactive office is NOT reactivated
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_inactive_office_not_reactivated():
    """Seeding must not reactivate an office that an admin has deactivated."""
    office = Office.objects.get(slug="charlottesville-va")
    office.is_active = False
    office.save()

    seed_offices()

    office.refresh_from_db()
    assert office.is_active is False, (
        "seed_offices must not reactivate offices that were deactivated by an admin"
    )


# ---------------------------------------------------------------------------
# Org tree structure
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_branch_path_and_region():
    office = Office.objects.get(slug="charlottesville-va")
    assert office.kind == Office.Kind.BRANCH
    assert office.path_label() == (
        "Onest Real Estate / Mid-Atlantic / Virginia / Charlottesville VA"
    )
    assert office.region_name() == "Mid-Atlantic"
    assert office.region is not None
    assert office.region.slug == "region-mid-atlantic"


@pytest.mark.django_db
def test_region_points_to_itself_for_direct_lookup():
    office = Office.objects.get(slug="region-mid-atlantic")
    assert office.region_id == office.pk


@pytest.mark.django_db
def test_grouped_choices_uses_regions():
    groups = {group["label"]: group["offices"] for group in Office.grouped_choices()}
    assert "Mid-Atlantic" in groups
    assert "New England" in groups
    mid_names = {office["name"] for office in groups["Mid-Atlantic"]}
    assert "Charlottesville VA" in mid_names
    assert "Fairfax VA" in mid_names
    assert "Virginia" not in mid_names


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_head_office_rejects_parent():
    region = Office.objects.get(slug="region-mid-atlantic")
    office = Office(
        name="Other HQ",
        slug="other-hq",
        kind=Office.Kind.HEAD_OFFICE,
        parent=region,
    )
    with pytest.raises(ValidationError):
        office.full_clean()


@pytest.mark.django_db
def test_branch_must_sit_under_regional_office():
    region = Office.objects.get(slug="region-mid-atlantic")
    office = Office(
        name="Orphan",
        slug="orphan-branch",
        kind=Office.Kind.BRANCH,
        parent=region,
    )
    with pytest.raises(ValidationError):
        office.full_clean()


@pytest.mark.django_db
def test_office_rejects_self_parenting():
    office = Office.objects.get(slug="charlottesville-va")
    office.parent = office
    with pytest.raises(ValidationError):
        office.full_clean()


@pytest.mark.django_db
def test_office_rejects_parent_cycle():
    regional = Office.objects.get(slug="ro-virginia")
    branch = Office.objects.get(slug="charlottesville-va")
    regional.parent = branch
    with pytest.raises(ValidationError):
        regional.full_clean()


@pytest.mark.django_db
def test_stable_key_is_immutable_after_creation():
    office = Office.objects.get(slug="charlottesville-va")
    office.stable_key = "new-key"
    with pytest.raises(ValidationError):
        office.full_clean()


@pytest.mark.django_db
def test_office_validates_optional_contact_fields():
    office = Office.objects.get(slug="charlottesville-va")
    office.state = "ZZ"
    office.zip_code = "bad"
    office.main_phone = "123"
    with pytest.raises(ValidationError):
        office.full_clean()


@pytest.mark.django_db
def test_for_region_returns_only_that_region_members():
    region = Office.objects.get(slug="region-mid-atlantic")
    slugs = set(Office.for_region(region).values_list("slug", flat=True))
    assert "charlottesville-va" in slugs
    assert "connecticut" not in slugs


# ---------------------------------------------------------------------------
# Inactive offices excluded from new assignments but remain in DB
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_inactive_office_excluded_from_assignable_queryset():
    office = Office.objects.get(slug="charlottesville-va")
    office.is_active = False
    office.save()

    slugs = set(Office.assignable_queryset().values_list("slug", flat=True))
    assert "charlottesville-va" not in slugs

    # But the record still exists for historical references.
    assert Office.objects.filter(slug="charlottesville-va").exists()


# ---------------------------------------------------------------------------
# Integration: onboarding office selector uses DB records
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_onboarding_office_choices_from_database():
    """grouped_choices must be driven by live DB records, not hard-coded strings."""
    all_choices = Office.grouped_choices()
    all_office_names = {
        office["name"] for group in all_choices for office in group["offices"]
    }
    # Canonical offices must appear.
    assert "Charlottesville VA" in all_office_names
    assert "Connecticut" in all_office_names

    # Deactivating a record must remove it from choices without a code change.
    office = Office.objects.get(slug="charlottesville-va")
    office.is_active = False
    office.save()

    choices_after = Office.grouped_choices()
    names_after = {o["name"] for g in choices_after for o in g["offices"]}
    assert "Charlottesville VA" not in names_after


# ---------------------------------------------------------------------------
# Office contact assignments
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_office_contact_assignment_rejects_cross_office_user():
    office = Office.objects.get(slug="charlottesville-va")
    other_office = Office.objects.get(slug="fairfax-va")
    user = User.objects.create_user(
        email="agent@example.com",
        office=other_office,
    )
    assignment = OfficeContactAssignment(
        office=office,
        user=user,
        assignment_type=OfficeContactAssignment.AssignmentType.MANAGER,
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


@pytest.mark.django_db
def test_office_contact_assignment_rejects_invalid_date_range():
    office = Office.objects.get(slug="charlottesville-va")
    user = User.objects.create_user(email="agent@example.com", office=office)
    assignment = OfficeContactAssignment(
        office=office,
        user=user,
        assignment_type=OfficeContactAssignment.AssignmentType.ADMIN,
        starts_at="2026-08-10",
        ends_at="2026-08-09",
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


@pytest.mark.django_db
def test_office_contact_assignment_unique_per_user_and_type():
    office = Office.objects.get(slug="charlottesville-va")
    user = User.objects.create_user(email="agent@example.com", office=office)
    OfficeContactAssignment.objects.create(
        office=office,
        user=user,
        assignment_type=OfficeContactAssignment.AssignmentType.BROKER_CONTACT,
    )
    with pytest.raises(IntegrityError):
        OfficeContactAssignment.objects.create(
            office=office,
            user=user,
            assignment_type=OfficeContactAssignment.AssignmentType.BROKER_CONTACT,
        )


@pytest.mark.django_db
def test_office_contact_assignment_only_one_primary_per_type():
    office = Office.objects.get(slug="charlottesville-va")
    user1 = User.objects.create_user(email="agent1@example.com", office=office)
    user2 = User.objects.create_user(email="agent2@example.com", office=office)
    OfficeContactAssignment.objects.create(
        office=office,
        user=user1,
        assignment_type=OfficeContactAssignment.AssignmentType.BROKER_CONTACT,
        is_primary=True,
    )
    with pytest.raises(IntegrityError):
        OfficeContactAssignment.objects.create(
            office=office,
            user=user2,
            assignment_type=OfficeContactAssignment.AssignmentType.BROKER_CONTACT,
            is_primary=True,
        )


# ---------------------------------------------------------------------------
# Public / internal payload boundaries
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_office_selector_payload_is_minimal():
    office = Office.objects.get(slug="charlottesville-va")
    payload = office_selector_payload(office)
    assert payload["name"] == "Charlottesville VA"
    assert "internalEmail" not in payload
    assert "accessInstructions" not in payload


@pytest.mark.django_db
def test_office_summary_payload_excludes_internal_fields():
    office = Office.objects.get(slug="charlottesville-va")
    office.internal_email = "internal@example.com"
    office.access_instructions = "Use side entrance."
    office.save()
    payload = office_summary_payload(office)
    assert "internalEmail" not in payload
    assert "accessInstructions" not in payload


@pytest.mark.django_db
def test_office_internal_payload_includes_internal_fields():
    office = Office.objects.get(slug="charlottesville-va")
    office.internal_email = "internal@example.com"
    office.access_instructions = "Use side entrance."
    office.save()
    payload = office_internal_payload(office)
    assert payload["internalEmail"] == "internal@example.com"
    assert payload["accessInstructions"] == "Use side entrance."


@pytest.mark.django_db
def test_office_admin_locks_stable_identity_after_create():
    from django.test import RequestFactory

    from apps.user.admin import OfficeAdmin

    office = Office.objects.get(slug="charlottesville-va")
    request = RequestFactory().get("/")
    admin = OfficeAdmin(Office, None)
    readonly = admin.get_readonly_fields(request, office)
    assert "stable_key" in readonly
    assert "region" in readonly
