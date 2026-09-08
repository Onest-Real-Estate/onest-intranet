from __future__ import annotations

from django import forms

from apps.reservations.taxonomy import (
    CalendarView,
    ExceptionKind,
    ExceptionVisibility,
    SpaceStatus,
    SpaceType,
)


class AvailabilityQueryForm(forms.Form):
    date = forms.DateField(required=False)
    view = forms.ChoiceField(
        required=False, choices=[(item.value, item.value) for item in CalendarView]
    )
    office = forms.SlugField(required=False)
    type = forms.ChoiceField(required=False, choices=[("", "Any"), *SpaceType.choices])
    capacity = forms.IntegerField(required=False, min_value=1, max_value=10000)
    amenities = forms.CharField(required=False, max_length=500)
    space = forms.UUIDField(required=False)

    def clean_amenities(self) -> tuple[str, ...]:
        value = self.cleaned_data.get("amenities", "")
        return tuple(
            sorted({item.strip() for item in value.split(",") if item.strip()})
        )


class RoomReservationSelectionForm(forms.Form):
    space = forms.UUIDField()
    startsAt = forms.DateTimeField()
    endsAt = forms.DateTimeField()


class RoomReservationForm(RoomReservationSelectionForm):
    purpose = forms.CharField(max_length=240, strip=True)
    attendeeCount = forms.IntegerField(required=False, min_value=1)
    submissionKey = forms.CharField(max_length=64, strip=True)


class SpaceAdminFilterForm(forms.Form):
    """URL-backed filters for the administration list."""

    q = forms.CharField(required=False, max_length=120, strip=True)
    office = forms.SlugField(required=False)
    type = forms.ChoiceField(required=False, choices=[("", "Any"), *SpaceType.choices])
    status = forms.ChoiceField(
        required=False, choices=[("", "Any"), *SpaceStatus.choices]
    )
    capacity = forms.IntegerField(required=False, min_value=1, max_value=10000)
    amenities = forms.CharField(required=False, max_length=500)
    page = forms.IntegerField(required=False, min_value=1, max_value=10000)

    def clean_amenities(self) -> tuple[str, ...]:
        value = self.cleaned_data.get("amenities", "")
        return tuple(
            sorted({item.strip() for item in value.split(",") if item.strip()})
        )


class SpaceIdentityForm(forms.Form):
    """Identity, description, and presentation fields."""

    name = forms.CharField(max_length=200, strip=True)
    spaceType = forms.ChoiceField(choices=SpaceType.choices)
    capacity = forms.IntegerField(min_value=1, max_value=10000)
    description = forms.CharField(required=False, max_length=2000, strip=True)
    location = forms.CharField(required=False, max_length=240, strip=True)
    accessInstructions = forms.CharField(required=False, max_length=2000, strip=True)
    displayOrder = forms.IntegerField(required=False, min_value=0, max_value=32767)


class SpacePolicyForm(forms.Form):
    """Booking limits and approval/cancellation rules."""

    minimumDurationMinutes = forms.IntegerField(min_value=5, max_value=1440)
    maximumDurationMinutes = forms.IntegerField(min_value=5, max_value=1440)
    bookingHorizonDays = forms.IntegerField(min_value=1, max_value=366)
    minimumNoticeMinutes = forms.IntegerField(min_value=0, max_value=20160)
    bufferBeforeMinutes = forms.IntegerField(min_value=0, max_value=240)
    bufferAfterMinutes = forms.IntegerField(min_value=0, max_value=240)
    cancellationCutoffMinutes = forms.IntegerField(min_value=0, max_value=20160)
    requiresApproval = forms.BooleanField(required=False)
    isReservable = forms.BooleanField(required=False)

    def clean(self) -> dict:
        cleaned = super().clean()
        minimum = cleaned.get("minimumDurationMinutes")
        maximum = cleaned.get("maximumDurationMinutes")
        if minimum and maximum and minimum > maximum:
            raise forms.ValidationError(
                {"maximumDurationMinutes": "Maximum must be at least the minimum."}
            )
        return cleaned


class SpaceEditForm(SpaceIdentityForm, SpacePolicyForm):
    """The workspace saves identity and policy together, with a stale guard."""

    expectedUpdatedAt = forms.DateTimeField(required=False)
    acknowledgeImpact = forms.BooleanField(required=False)


class SpaceCreateForm(SpaceIdentityForm):
    office = forms.SlugField()


class SpaceActivationForm(forms.Form):
    active = forms.BooleanField(required=False)
    reason = forms.CharField(required=False, max_length=240, strip=True)
    acknowledgeImpact = forms.BooleanField(required=False)


class SpaceRetireForm(forms.Form):
    reason = forms.CharField(max_length=240, strip=True)


class ScheduleIntervalForm(forms.Form):
    weekday = forms.IntegerField(min_value=0, max_value=6)
    startsAt = forms.TimeField()
    endsAt = forms.TimeField()


class AvailabilityBlockForm(forms.Form):
    kind = forms.ChoiceField(choices=ExceptionKind.choices)
    startsAt = forms.DateTimeField()
    endsAt = forms.DateTimeField()
    reason = forms.CharField(max_length=240, strip=True)
    visibility = forms.ChoiceField(choices=ExceptionVisibility.choices)


class ReservationMoveForm(forms.Form):
    destination = forms.UUIDField()
    reason = forms.CharField(max_length=240, strip=True)


class ReservationCancelForm(forms.Form):
    reason = forms.CharField(max_length=240, strip=True)
