from collections.abc import Mapping
from typing import Any, cast

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.web.contracts import empty_validation_errors, validation_errors

from .headshot import validate_headshot
from .models import Office, User
from .us import (
    US_STATE_CHOICES,
    normalize_nrds,
    normalize_us_phone,
    normalize_us_zip,
)


class ProfileForm(forms.ModelForm):
    """Shared onboarding + profile-edit form.

    Mass-assignment guard
    ---------------------
    Only the fields listed in ``Meta.fields`` can be set through this form.
    Administrative fields (is_staff, is_superuser, groups, user_permissions,
    profile_completed, onboarding_version) are excluded and cannot be set
    through a crafted POST.
    """

    headshot = forms.ImageField(
        label=_("Profile photo"),
        required=False,
        help_text=_("JPEG or PNG, at least 200×200 px, max 5 MB."),
    )
    first_name = forms.CharField(label=_("First name"), max_length=150, required=True)
    last_name = forms.CharField(label=_("Last name"), max_length=150, required=True)
    phone_number = forms.CharField(
        label=_("Phone number"),
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={
                "type": "tel",
                "placeholder": "(202) 555-0100",
                "autocomplete": "tel",
            }
        ),
    )
    street_address = forms.CharField(
        label=_("Street address"),
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={"autocomplete": "street-address"}),
    )
    city = forms.CharField(
        label=_("City"),
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"autocomplete": "address-level2"}),
    )
    state = forms.ChoiceField(
        label=_("State"),
        choices=[("", _("Select a state"))] + list(US_STATE_CHOICES),
        required=True,
    )
    zip_code = forms.CharField(
        label=_("ZIP code"),
        max_length=10,
        required=True,
        widget=forms.TextInput(
            attrs={"autocomplete": "postal-code", "placeholder": "12345"}
        ),
    )
    office = forms.ModelChoiceField(
        label=_("Office location"),
        queryset=Office.assignable_queryset(),
        required=True,
        empty_label=_("Select your office"),
    )
    mls_number = forms.CharField(
        label=_("MLS number"),
        max_length=32,
        required=False,
        help_text=_("Optional — you can add this later."),
    )
    nrds_number = forms.CharField(
        label=_("NRDS number"),
        max_length=9,
        required=False,
        help_text=_("Optional 8- or 9-digit ID — you can add this later."),
    )

    class Meta:
        model = User
        # Explicit allowlist — admin-controlled fields are NOT here.
        fields = (
            "headshot",
            "first_name",
            "last_name",
            "phone_number",
            "street_address",
            "city",
            "state",
            "zip_code",
            "office",
            "mls_number",
            "nrds_number",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        office_field = cast(forms.ModelChoiceField, self.fields["office"])
        office_field.queryset = Office.assignable_queryset()

    def clean_phone_number(self):
        return normalize_us_phone(self.cleaned_data["phone_number"])

    def clean_zip_code(self):
        return normalize_us_zip(self.cleaned_data["zip_code"])

    def clean_nrds_number(self):
        return normalize_nrds(self.cleaned_data.get("nrds_number", ""))

    def clean_mls_number(self):
        return (self.cleaned_data.get("mls_number") or "").strip()

    def clean_headshot(self):
        upload = self.cleaned_data.get("headshot")
        if upload:
            validate_headshot(upload)
        return upload

    def clean_office(self):
        office = self.cleaned_data.get("office")
        if office is not None and (not office.is_active or not office.is_assignable):
            raise forms.ValidationError(
                _("That office is no longer available. Please select an active office.")
            )
        return office

    def save(self, commit=True):
        user = super().save(commit=False)
        user.display_name = user.get_full_name().strip()
        if commit:
            user.save()
        return user


def form_errors(form: forms.BaseForm) -> dict:
    """Return the shared field/form validation payload for Inertia."""
    return validation_errors(form)


def profile_initial(user: User, posted: Mapping[str, Any] | None = None) -> dict:
    """Values for the React form. Posted data wins so a 422 doesn't wipe the form."""

    def value(name: str, attr: str | None = None):
        if posted is not None:
            return posted.get(name, "")
        raw = getattr(user, attr or name)
        if name == "office":
            return str(raw.pk) if raw else ""
        return raw or ""

    return {
        "firstName": value("first_name"),
        "lastName": value("last_name"),
        "phoneNumber": value("phone_number"),
        "streetAddress": value("street_address"),
        "city": value("city"),
        "state": value("state"),
        "zipCode": value("zip_code"),
        "officeId": value("office"),
        "mlsNumber": value("mls_number"),
        "nrdsNumber": value("nrds_number"),
        "headshotUrl": user.headshot.url if user.headshot else None,
    }


def profile_page_props(
    user: User,
    *,
    errors: dict | None = None,
    posted: Mapping[str, Any] | None = None,
):
    return {
        "initial": profile_initial(user, posted),
        "validation": errors or empty_validation_errors(),
        "offices": Office.grouped_choices(),
        "states": [{"code": code, "name": name} for code, name in US_STATE_CHOICES],
    }
