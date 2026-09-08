from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, time

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.reservations.models import (
    Amenity,
    Occupancy,
    Reservation,
    Space,
    SpaceAvailabilityException,
    SpacePhoto,
    WeeklyAvailability,
)
from apps.reservations.taxonomy import (
    AmenityCategory,
    ExceptionKind,
    RecurrencePolicy,
    ReservationPermission,
    SpacePermission,
    SpaceType,
    Weekday,
)
from apps.reservations.tests.factories import make_space, office
from apps.user.storage import PrivateLocalStorage


def test_valid_space_policy_is_representable(seeded):
    space = make_space(
        capacity=12,
        minimum_duration_minutes=30,
        maximum_duration_minutes=240,
        booking_horizon_days=60,
        minimum_notice_minutes=120,
        buffer_before_minutes=10,
        buffer_after_minutes=15,
        cancellation_cutoff_minutes=180,
        recurrence_policy=RecurrencePolicy.WEEKLY,
        maximum_recurrence_occurrences=8,
    )

    assert space.capacity == 12
    assert space.maximum_recurrence_occurrences == 8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capacity", 0),
        ("minimum_duration_minutes", 0),
        ("maximum_duration_minutes", 0),
        ("booking_horizon_days", 0),
    ],
)
def test_positive_space_values_are_validated(seeded, field, value):
    space = Space(
        owner_office=office("fairfax-va"),
        name="Invalid room",
        space_type=SpaceType.MEETING_ROOM,
        capacity=4,
    )
    setattr(space, field, value)

    with pytest.raises(ValidationError):
        space.full_clean()


def test_duration_policy_must_be_internally_consistent(seeded):
    space = Space(
        owner_office=office("fairfax-va"),
        name="Invalid room",
        space_type=SpaceType.MEETING_ROOM,
        capacity=4,
        minimum_duration_minutes=120,
        maximum_duration_minutes=60,
    )

    with pytest.raises(ValidationError, match="Maximum duration"):
        space.full_clean()


def test_recurrence_policy_requires_a_governed_limit(seeded):
    space = Space(
        owner_office=office("fairfax-va"),
        name="Recurring room",
        space_type=SpaceType.MEETING_ROOM,
        capacity=4,
        recurrence_policy=RecurrencePolicy.WEEKLY,
    )

    with pytest.raises(ValidationError, match="limit"):
        space.full_clean()


def test_only_active_assignable_office_can_own_a_space(seeded):
    space = Space(
        owner_office=office("region-mid-atlantic"),
        name="Region room",
        space_type=SpaceType.MEETING_ROOM,
        capacity=4,
    )

    with pytest.raises(ValidationError, match="assignable"):
        space.full_clean()


def test_public_identity_is_immutable(seeded):
    space = make_space()
    space.public_id = uuid.uuid4()

    with pytest.raises(ValidationError, match="Stable identity"):
        space.full_clean()


def test_spaces_cannot_be_hard_deleted(seeded):
    space = make_space()

    with pytest.raises(ValidationError, match="retired"):
        space.delete()
    with pytest.raises(ValidationError, match="retired"):
        Space.objects.filter(pk=space.pk).delete()


def test_amenity_code_is_immutable_and_has_no_ui_styling_fields(seeded):
    amenity = Amenity.objects.create(
        code="video-conference",
        name="Video conference",
        category=AmenityCategory.AUDIO_VISUAL,
    )
    amenity.code = "arbitrary-new-code"

    with pytest.raises(ValidationError, match="immutable"):
        amenity.full_clean()
    field_names = {field.name for field in Amenity._meta.fields}
    assert "icon" not in field_names
    assert "color" not in field_names


def test_weekly_interval_must_end_after_it_starts(seeded):
    interval = WeeklyAvailability(
        space=make_space(),
        weekday=Weekday.MONDAY,
        starts_at=time(17),
        ends_at=time(9),
    )

    with pytest.raises(ValidationError, match="after start"):
        interval.full_clean()


def test_weekly_intervals_cannot_overlap(seeded):
    space = make_space()
    WeeklyAvailability.objects.create(
        space=space,
        weekday=Weekday.MONDAY,
        starts_at=time(9),
        ends_at=time(12),
    )
    overlap = WeeklyAvailability(
        space=space,
        weekday=Weekday.MONDAY,
        starts_at=time(11),
        ends_at=time(13),
    )

    with pytest.raises(ValidationError, match="cannot overlap"):
        overlap.full_clean()


def test_exception_requires_aware_ordered_interval(seeded):
    space = make_space()
    naive = SpaceAvailabilityException(
        space=space,
        kind=ExceptionKind.MAINTENANCE,
        starts_at=datetime(2026, 1, 5, 10),
        ends_at=datetime(2026, 1, 5, 11),
        reason="HVAC service",
    )
    backwards = SpaceAvailabilityException(
        space=space,
        kind=ExceptionKind.MAINTENANCE,
        starts_at=datetime(2026, 1, 5, 11, tzinfo=UTC),
        ends_at=datetime(2026, 1, 5, 10, tzinfo=UTC),
        reason="HVAC service",
    )

    with pytest.raises(ValidationError, match="timezone"):
        naive.full_clean()
    with pytest.raises(ValidationError, match="after start"):
        backwards.full_clean()


def test_office_timezone_must_be_an_iana_name(seeded):
    branch = office("fairfax-va")
    branch.timezone = "EST"

    with pytest.raises(ValidationError, match="IANA"):
        branch.full_clean()


def test_photo_validation_rejects_non_image_content(seeded):
    photo = SpacePhoto(
        space=make_space(),
        file=SimpleUploadedFile("room.png", b"not-an-image", content_type="image/png"),
        alt_text="Conference room",
    )

    with pytest.raises(ValidationError, match="valid"):
        photo.full_clean()


def test_valid_photo_uses_protected_storage(seeded):
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    photo = SpacePhoto(
        space=make_space(),
        file=SimpleUploadedFile("room.png", png, content_type="image/png"),
        alt_text="Conference room",
    )
    photo.full_clean()

    assert isinstance(photo.file.storage, PrivateLocalStorage)
    assert photo.file.storage.location.endswith("/private")


def test_schema_declares_calendar_indexes_and_permissions():
    index_names = {index.name for index in Space._meta.indexes}
    exception_indexes = {
        index.name for index in SpaceAvailabilityException._meta.indexes
    }
    permissions = {code for code, _ in Space._meta.permissions}
    booking_permissions = {code for code, _ in Reservation._meta.permissions}
    occupancy_indexes = {index.name for index in Occupancy._meta.indexes}
    booking_indexes = {index.name for index in Reservation._meta.indexes}

    assert "rsv_space_office_state_type" in index_names
    assert "rsv_exception_space_time" in exception_indexes
    assert "rsv_occupancy_calendar_idx" in occupancy_indexes
    assert "rsv_booking_space_state_time" in booking_indexes
    assert "rsv_booking_owner_time" in booking_indexes
    assert permissions == {
        permission.value.rsplit(".", 1)[1] for permission in SpacePermission
    }
    assert booking_permissions == {
        permission.value.rsplit(".", 1)[1] for permission in ReservationPermission
    }
