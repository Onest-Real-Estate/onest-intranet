"""Forms for the training workspace."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.training.administration import (
    DRAFT_EDITABLE_FIELDS,
    TRANSITIONS,
    publishable_office_queryset,
)
from apps.training.audience import (
    AudienceSelector,
    targetable_office_ids,
    targetable_role_codes,
    targetable_user_queryset,
)
from apps.training.models import TrainingCategory, TrainingContent
from apps.training.taxonomy import CONTENT_TYPE_CHOICES
from apps.user.models import Office, User
from apps.user.roles import ROLE_BY_KEY


class TrainingContentForm(forms.ModelForm):
    owner_office = forms.ModelChoiceField(
        queryset=Office.objects.none(),
        label=_("Owning office"),
    )
    category = forms.ModelChoiceField(
        queryset=TrainingCategory.objects.none(),
        required=False,
        label=_("Category"),
        to_field_name="code",
    )
    content_type = forms.ChoiceField(choices=CONTENT_TYPE_CHOICES, label=_("Type"))
    audience_company = forms.BooleanField(
        required=False, label=_("Everyone at the brokerage")
    )
    audience_roles = forms.MultipleChoiceField(
        choices=(), required=False, label=_("Roles")
    )
    audience_regions = forms.ModelMultipleChoiceField(
        queryset=Office.objects.none(), required=False, label=_("Regions")
    )
    audience_offices = forms.ModelMultipleChoiceField(
        queryset=Office.objects.none(), required=False, label=_("Offices")
    )
    audience_users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False, label=_("Named people")
    )
    embed_url = forms.CharField(required=False, label=_("Video embed URL"))
    expected_version = forms.CharField(required=False)

    class Meta:
        model = TrainingContent
        fields = (
            "owner_office",
            "title",
            "summary",
            "body",
            "category",
            "content_type",
            "estimated_minutes",
            "tool_code",
            "external_url",
            "publish_at",
            "expires_at",
            "is_required",
        )

    def __init__(self, *args: Any, actor: User, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.actor = actor

        owner_field = cast(forms.ModelChoiceField, self.fields["owner_office"])
        owner_field.queryset = publishable_office_queryset(actor)

        category_field = cast(forms.ModelChoiceField, self.fields["category"])
        current = self.instance.category_id if self.instance.pk else None
        category_field.queryset = TrainingCategory.objects.filter(
            Q(is_active=True) | Q(pk=current)
        )

        targetable = Office.objects.filter(
            pk__in=targetable_office_ids(actor), is_active=True
        ).order_by("sort_order", "name")
        regions = cast(forms.ModelMultipleChoiceField, self.fields["audience_regions"])
        regions.queryset = targetable.filter(
            kind__in=[Office.Kind.HEAD_OFFICE, Office.Kind.REGION]
        )
        offices = cast(forms.ModelMultipleChoiceField, self.fields["audience_offices"])
        offices.queryset = targetable.exclude(
            kind__in=[Office.Kind.HEAD_OFFICE, Office.Kind.REGION]
        )
        people = cast(forms.ModelMultipleChoiceField, self.fields["audience_users"])
        people.queryset = targetable_user_queryset(actor)
        roles = cast(forms.MultipleChoiceField, self.fields["audience_roles"])
        roles.choices = [
            (code, ROLE_BY_KEY[code].label if code in ROLE_BY_KEY else code)
            for code in sorted(targetable_role_codes(actor))
        ]

        for name in (
            "summary",
            "body",
            "publish_at",
            "expires_at",
            "estimated_minutes",
            "tool_code",
            "external_url",
        ):
            self.fields[name].required = False
        self.fields["is_required"].required = False
        if self.instance.pk:
            owner_field.disabled = True
            self.initial["owner_office"] = self.instance.owner_office_id

    def clean_owner_office(self) -> Office:
        if self.instance.pk:
            return self.instance.owner_office
        return self.cleaned_data["owner_office"]

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        start = cleaned.get("publish_at")
        end = cleaned.get("expires_at")
        if start and end and end <= start:
            self.add_error("expires_at", _("Expiry must be after the publish time."))
        if not any(
            (
                cleaned.get("audience_company"),
                cleaned.get("audience_roles"),
                cleaned.get("audience_regions"),
                cleaned.get("audience_offices"),
                cleaned.get("audience_users"),
            )
        ):
            self.add_error(
                "audience_company",
                _("Choose at least one audience. A draft with none reaches nobody."),
            )
        return cleaned

    @property
    def field_values(self) -> dict[str, Any]:
        return {
            name: self.cleaned_data[name]
            for name in DRAFT_EDITABLE_FIELDS
            if name in self.cleaned_data
        }

    @property
    def selectors(self) -> list[AudienceSelector]:
        cleaned = self.cleaned_data
        selectors: list[AudienceSelector] = []
        if cleaned.get("audience_company"):
            selectors.append(AudienceSelector(kind="company"))
        for code in cleaned.get("audience_roles") or []:
            selectors.append(AudienceSelector(kind="role", role=code))
        for office in cleaned.get("audience_regions") or []:
            selectors.append(AudienceSelector(kind="region", office=office))
        for office in cleaned.get("audience_offices") or []:
            selectors.append(AudienceSelector(kind="office", office=office))
        for person in cleaned.get("audience_users") or []:
            selectors.append(AudienceSelector(kind="user", user=person))
        return selectors


class TrainingTransitionForm(forms.Form):
    action = forms.ChoiceField(choices=[(value, value) for value in TRANSITIONS])
    expected_version = forms.CharField(required=False)


class TrainingDuplicateForm(forms.Form):
    expected_version = forms.CharField(required=False)
