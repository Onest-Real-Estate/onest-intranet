from __future__ import annotations

from django import forms

from apps.reservations.taxonomy import CalendarView, SpaceType


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
