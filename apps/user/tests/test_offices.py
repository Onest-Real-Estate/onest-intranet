import pytest
from django.core.exceptions import ValidationError

from apps.user.models import Office
from apps.user.office_seed import seed_offices


@pytest.mark.django_db
def test_seed_creates_current_markets():
    names = set(
        Office.objects.filter(is_assignable=True).values_list("name", flat=True)
    )
    assert names >= {
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
    # Grouping nodes are not pickable work locations.
    assert "Mid-Atlantic" not in names
    assert "Virginia" not in names
    assert "Pennsylvania" not in names


@pytest.mark.django_db
def test_seed_is_idempotent():
    count = Office.objects.count()
    seed_offices()
    assert Office.objects.count() == count


@pytest.mark.django_db
def test_branch_path_and_region():
    office = Office.objects.get(slug="charlottesville-va")
    assert office.kind == Office.Kind.BRANCH
    assert office.path_label() == (
        "Onest Real Estate / Mid-Atlantic / Virginia / Charlottesville VA"
    )
    assert office.region_name() == "Mid-Atlantic"


@pytest.mark.django_db
def test_grouped_choices_uses_regions():
    groups = {group["label"]: group["offices"] for group in Office.grouped_choices()}
    assert "Mid-Atlantic" in groups
    assert "New England" in groups
    mid_names = {office["name"] for office in groups["Mid-Atlantic"]}
    assert "Charlottesville VA" in mid_names
    assert "Fairfax VA" in mid_names
    assert "Virginia" not in mid_names


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
