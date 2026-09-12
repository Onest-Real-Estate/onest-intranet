"""Small, explicit forms for onboarding operations actions."""

from typing import cast

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.onboarding_tools.models import ToolState
from apps.user.models import User


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
    """One catalog row by stable slug. Adding a tool is data, not a deploy."""

    tool = forms.SlugField()
    state = forms.ChoiceField(choices=ToolState.choices)
    #: The business reason a correction needs. Never a place for credentials.
    note = forms.CharField(max_length=300, required=False)


class OnboardingNoticeForm(forms.Form):
    source = forms.ChoiceField(
        choices=(("contract", "Contract"), ("training", "Training"))
    )
    notice = forms.CharField(max_length=80)
    idempotency_key = forms.UUIDField()
