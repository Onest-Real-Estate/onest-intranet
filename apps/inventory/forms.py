"""Validated forms for inventory administration writes."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import cast

from django import forms
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.inventory.taxonomy import (
    CATEGORY_CHOICES,
    CONDITION_CHOICES,
    SUPPORTED_CURRENCIES,
    TRACKING_CHOICES,
    TrackingMode,
)
from apps.user.models import Office
from apps.web.contracts import validation_errors


def form_errors(form: forms.BaseForm) -> dict:
    return validation_errors(form)


class InventoryItemCreateForm(forms.Form):
    name = forms.CharField(max_length=200)
    owner_office = forms.ModelChoiceField(queryset=Office.objects.none())
    category = forms.ChoiceField(choices=CATEGORY_CHOICES)
    tracking_mode = forms.ChoiceField(choices=TRACKING_CHOICES)
    condition = forms.ChoiceField(choices=CONDITION_CHOICES)
    asset_id = forms.CharField(max_length=64, required=False)
    serial_number = forms.CharField(max_length=128, required=False)
    total_quantity = forms.IntegerField(min_value=1, initial=1)
    storage_location = forms.CharField(max_length=200, required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    internal_notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    replacement_value = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    replacement_currency = forms.CharField(max_length=3, required=False, initial="USD")
    requires_approval = forms.BooleanField(required=False)

    def __init__(self, *args, owner_queryset: QuerySet[Office] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner_queryset is not None:
            cast(
                forms.ModelChoiceField, self.fields["owner_office"]
            ).queryset = owner_queryset

    def clean(self):
        cleaned = super().clean()
        tracking = cleaned.get("tracking_mode")
        if tracking == TrackingMode.SERIALIZED:
            cleaned["total_quantity"] = 1
            if not (cleaned.get("asset_id") or "").strip():
                self.add_error("asset_id", _("Serialized items require an asset id."))
        elif tracking == TrackingMode.POOLED:
            cleaned["asset_id"] = ""
            cleaned["serial_number"] = ""
        currency = (cleaned.get("replacement_currency") or "USD").upper()
        cleaned["replacement_currency"] = currency
        value = cleaned.get("replacement_value")
        if value is not None and currency not in SUPPORTED_CURRENCIES:
            self.add_error(
                "replacement_currency",
                _("Unsupported currency."),
            )
        return cleaned


class InventoryItemUpdateForm(forms.Form):
    name = forms.CharField(max_length=200)
    category = forms.ChoiceField(choices=CATEGORY_CHOICES)
    condition = forms.ChoiceField(choices=CONDITION_CHOICES)
    storage_location = forms.CharField(max_length=200, required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    internal_notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    replacement_value = forms.CharField(required=False)
    replacement_currency = forms.CharField(max_length=3, required=False)
    total_quantity = forms.IntegerField(min_value=1, required=False)
    expected_version = forms.CharField()
    photo_is_public = forms.BooleanField(required=False)
    requires_approval = forms.BooleanField(required=False)

    def clean_replacement_value(self):
        raw = (self.cleaned_data.get("replacement_value") or "").strip()
        if not raw:
            return None
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise forms.ValidationError(_("Enter a valid amount.")) from exc
        if value < 0:
            raise forms.ValidationError(_("Replacement value must be nonnegative."))
        return value

    def clean_replacement_currency(self):
        raw = (self.cleaned_data.get("replacement_currency") or "USD").upper()
        if raw and raw not in SUPPORTED_CURRENCIES:
            raise forms.ValidationError(_("Unsupported currency."))
        return raw or "USD"


class InventoryItemTransitionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ("mark_temporarily_unavailable", _("Mark temporarily unavailable")),
            ("mark_damaged", _("Mark damaged")),
            ("mark_lost", _("Mark lost")),
            ("restore", _("Restore to available")),
            ("retire", _("Retire")),
        )
    )
    expected_version = forms.CharField()
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class InventoryItemTransferForm(forms.Form):
    to_office = forms.ModelChoiceField(queryset=Office.objects.none())
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    expected_version = forms.CharField()

    def __init__(self, *args, owner_queryset: QuerySet[Office] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner_queryset is not None:
            cast(
                forms.ModelChoiceField, self.fields["to_office"]
            ).queryset = owner_queryset


class InventoryPhotoForm(forms.Form):
    photo = forms.FileField()
    expected_version = forms.CharField()
