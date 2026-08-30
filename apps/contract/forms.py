"""Forms for contract template administration."""

from __future__ import annotations

import json
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.user.models import Office, User
from apps.user.us import US_STATE_CHOICES, US_STATE_CODES
from apps.web.authorization import scope_queryset_for_offices


class ContractTemplateCreateForm(forms.Form):
    stable_key = forms.SlugField()
    name = forms.CharField(max_length=180)
    description = forms.CharField(required=False, widget=forms.Textarea)
    jurisdiction_state_codes = forms.MultipleChoiceField(
        choices=US_STATE_CHOICES,
        required=False,
        help_text=_("Leave empty for all jurisdictions."),
    )
    company_wide = forms.BooleanField(required=False)
    applicable_offices = forms.ModelMultipleChoiceField(
        queryset=Office.objects.none(), required=False
    )
    applicable_regions = forms.ModelMultipleChoiceField(
        queryset=Office.objects.none(), required=False
    )
    effective_from = forms.DateField(required=False)
    effective_until = forms.DateField(required=False)
    version_label = forms.CharField(max_length=32)

    def __init__(self, *args: Any, actor: User, **kwargs: Any):
        super().__init__(*args, **kwargs)
        offices = scope_queryset_for_offices(
            actor,
            Office.objects.filter(is_active=True),
        )
        regions_field = self.fields["applicable_regions"]
        assert isinstance(regions_field, forms.ModelMultipleChoiceField)
        regions_field.queryset = offices.filter(kind=Office.Kind.REGION)
        offices_field = self.fields["applicable_offices"]
        assert isinstance(offices_field, forms.ModelMultipleChoiceField)
        offices_field.queryset = offices.exclude(
            kind__in=[Office.Kind.HEAD_OFFICE, Office.Kind.REGION]
        )

    def clean_jurisdiction_state_codes(self) -> list[str]:
        raw = self.cleaned_data.get("jurisdiction_state_codes") or []
        codes = sorted({str(code).strip().upper() for code in raw if str(code).strip()})
        unknown = [code for code in codes if code not in US_STATE_CODES]
        if unknown:
            raise forms.ValidationError(
                _("Unknown state codes: %(codes)s") % {"codes": ", ".join(unknown)}
            )
        return codes


class ContractTemplateVersionForm(forms.Form):
    display_name = forms.CharField(max_length=180, required=False)
    description = forms.CharField(required=False, widget=forms.Textarea)
    merge_schema_json = forms.CharField(
        widget=forms.Textarea,
        help_text=_("JSON array of merge-variable definitions."),
    )
    source_document = forms.FileField(required=False)
    expected_version = forms.CharField(required=False)

    def clean_merge_schema_json(self) -> list[dict]:
        raw = self.cleaned_data["merge_schema_json"]
        try:
            value = json.loads(raw or "[]")
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Enter valid JSON.") from exc
        if not isinstance(value, list):
            raise forms.ValidationError("Merge schema JSON must be an array.")
        if any(not isinstance(item, dict) for item in value):
            raise forms.ValidationError("Each merge schema item must be an object.")
        return value


class ContractTemplateActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=[
            ("preview", "preview"),
            ("suggest_fields", "suggest_fields"),
            ("publish", "publish"),
            ("activate", "activate"),
            ("retire", "retire"),
        ]
    )


class ContractTemplateFieldLayoutForm(forms.Form):
    field_layout_json = forms.CharField(required=False, widget=forms.Textarea)
    expected_version = forms.CharField(required=False)

    def clean_field_layout_json(self) -> list:
        raw = self.cleaned_data.get("field_layout_json") or "[]"
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Enter valid field layout JSON.") from exc
        if not isinstance(value, list):
            raise forms.ValidationError("Field layout must be an array.")
        return value
