"""Forms for Quick Access administration.

Every choice set is rebuilt from the actor's own scope when the form is
constructed, so a submitted office id that the actor may not target fails
validation rather than reaching the service. The service checks the same thing
again — the form narrows the field, the service enforces the boundary.
"""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.user.models import Office, User
from apps.user.roles import ROLE_BY_KEY, ROLE_DEFINITIONS
from apps.web.models import QuickAccessLink
from apps.web.quick_access.administration import (
    EDITABLE_FIELDS,
    targetable_office_queryset,
)
from apps.web.quick_access.catalog import ICON_KEYS, internal_destination_options
from apps.web.quick_access.destinations import validate_destination

#: Integration attributes that fall back to their model default.
OPTIONAL_WITH_DEFAULT: tuple[str, ...] = (
    "sso_capability",
    "integration_health",
    "setup_behavior",
)

ROLE_CHOICES = tuple(
    (definition.code, definition.label) for definition in ROLE_DEFINITIONS
)


class QuickAccessLinkForm(forms.ModelForm):
    """Create or edit one link, bounded by the actor's grant scope."""

    stable_key = forms.SlugField(
        label=_("Stable key"),
        help_text=_("Lower-case identifier. Permanent once saved."),
    )
    roles = forms.MultipleChoiceField(
        choices=ROLE_CHOICES,
        required=False,
        label=_("Role audience"),
        help_text=_("Leave empty to show this link to every role."),
    )
    offices = forms.ModelMultipleChoiceField(
        # Replaced per instance with the actor's own targetable offices.
        queryset=Office.objects.none(),
        required=False,
        label=_("Office audience"),
    )
    company_wide = forms.BooleanField(required=False, label=_("Publish company-wide"))
    is_active = forms.BooleanField(required=False, initial=True, label=_("Active"))
    acknowledge_exposure = forms.BooleanField(required=False)
    expected_version = forms.CharField(required=False)

    class Meta:
        model = QuickAccessLink
        fields = EDITABLE_FIELDS

    def __init__(self, *args: Any, actor: User, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.actor = actor
        offices_field = cast(forms.ModelMultipleChoiceField, self.fields["offices"])
        offices_field.queryset = targetable_office_queryset(actor)
        self.fields["description"].required = False
        for name in ("publish_start_at", "publish_end_at"):
            self.fields[name].required = False
        # Integration metadata describes a tool rather than identifying it, and
        # every value has a reviewed default. Leaving one out of a submission
        # is not a mistake worth a validation error.
        for name in OPTIONAL_WITH_DEFAULT:
            self.fields[name].required = False
            self.fields[name].initial = QuickAccessLink._meta.get_field(
                name
            ).get_default()
        if self.instance.pk:
            # Identity is permanent: the field stays visible so an
            # administrator can read it, but a submitted change is ignored
            # rather than silently applied.
            self.fields["stable_key"].disabled = True
            self.initial["stable_key"] = self.instance.stable_key

    def clean_icon(self) -> str:
        icon = self.cleaned_data["icon"]
        if icon not in ICON_KEYS:
            raise forms.ValidationError(_("Choose one of the approved icons."))
        return icon

    def clean_stable_key(self) -> str:
        key = (self.cleaned_data.get("stable_key") or "").strip().lower()
        if len(key) > 64:
            raise forms.ValidationError(_("That stable key is too long."))
        if self.instance.pk:
            return self.instance.stable_key
        if QuickAccessLink.objects.filter(stable_key=key).exists():
            raise forms.ValidationError(_("Another link already uses this stable key."))
        return key

    def clean_roles(self) -> list[str]:
        codes = self.cleaned_data.get("roles") or []
        unknown = [code for code in codes if code not in ROLE_BY_KEY]
        if unknown:
            raise forms.ValidationError(_("That role is not in the catalog."))
        return sorted(set(codes))

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        for name in OPTIONAL_WITH_DEFAULT:
            if not cleaned.get(name):
                cleaned[name] = QuickAccessLink._meta.get_field(name).get_default()
        destination_type = cleaned.get("destination_type")
        destination_value = cleaned.get("destination_value")
        if destination_type and destination_value:
            try:
                cleaned["destination_value"] = validate_destination(
                    destination_type, destination_value
                )
            except forms.ValidationError as exc:
                self.add_error("destination_value", exc)
        start = cleaned.get("publish_start_at")
        end = cleaned.get("publish_end_at")
        if start and end and end <= start:
            self.add_error(
                "publish_end_at", _("The publish window must end after it starts.")
            )
        if not cleaned.get("company_wide") and not cleaned.get("offices"):
            self.add_error(
                "offices",
                _("Choose at least one office, or publish company-wide."),
            )
        return cleaned

    @property
    def office_ids(self) -> list[int]:
        return [office.pk for office in self.cleaned_data.get("offices", [])]

    @property
    def field_values(self) -> dict[str, Any]:
        return {
            name: self.cleaned_data[name]
            for name in EDITABLE_FIELDS
            if name in self.cleaned_data
        }


class QuickAccessStateForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ("activate", "activate"),
            ("deactivate", "deactivate"),
            ("archive", "archive"),
            ("restore", "restore"),
        )
    )


class QuickAccessReorderForm(forms.Form):
    """A comma-separated id sequence — the whole reorder contract."""

    order = forms.CharField()

    def clean_order(self) -> list[int]:
        raw = self.cleaned_data["order"]
        try:
            ids = [int(part) for part in raw.split(",") if part.strip()]
        except ValueError as exc:
            raise forms.ValidationError(_("Send link ids as numbers.")) from exc
        if not ids:
            raise forms.ValidationError(_("Send the new order."))
        return ids


def destination_help_options() -> list[dict[str, str]]:
    return internal_destination_options()
