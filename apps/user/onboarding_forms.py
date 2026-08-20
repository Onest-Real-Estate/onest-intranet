"""Small, explicit forms for onboarding operations actions."""

from typing import cast

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.user.models import OnboardingToolSetup, User


class VersionedOnboardingForm(forms.Form):
    expected_version = forms.CharField(required=False, widget=forms.HiddenInput)


class OnboardingOwnerForm(VersionedOnboardingForm):
    owner = forms.ModelChoiceField(
        label=_("Onboarding owner"),
        queryset=User.objects.none(),
        required=False,
        empty_label=_("Unassigned"),
    )

    def __init__(self, *args, owner_queryset, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ModelChoiceField, self.fields["owner"]).queryset = owner_queryset


class OnboardingTaskCreateForm(VersionedOnboardingForm):
    title = forms.CharField(label=_("Task"), max_length=200)
    due_on = forms.DateField(
        label=_("Due date"),
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    is_blocking = forms.BooleanField(label=_("Blocks activation"), required=False)


class OnboardingTaskResolveForm(VersionedOnboardingForm):
    task = forms.IntegerField(widget=forms.HiddenInput)


class OnboardingToolForm(VersionedOnboardingForm):
    tool = forms.ChoiceField(choices=OnboardingToolSetup.Tool.choices)
    state = forms.ChoiceField(choices=OnboardingToolSetup.State.choices)


class OnboardingNoticeForm(forms.Form):
    source = forms.ChoiceField(
        choices=(("contract", "Contract"), ("training", "Training"))
    )
    notice = forms.CharField(max_length=80)
    idempotency_key = forms.UUIDField()
