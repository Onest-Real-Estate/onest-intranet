"""Small, explicit forms for onboarding operations actions."""

from typing import cast

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.onboarding_tools.services import ToolWorkspaceAction
from apps.user.models import User


class VersionedOnboardingForm(forms.Form):
    expected_version = forms.CharField(required=True, widget=forms.HiddenInput)


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


class OnboardingToolActionForm(VersionedOnboardingForm):
    """One catalog row by stable slug. Adding a tool is data, not a deploy."""

    tool = forms.SlugField()
    action = forms.ChoiceField(
        choices=tuple(
            (str(action), action.name.replace("_", " ").title())
            for action in ToolWorkspaceAction
        )
    )
    #: The business reason a correction needs. Never a place for credentials.
    reason = forms.CharField(max_length=300, required=False)


class OnboardingContractForm(VersionedOnboardingForm):
    pass


class OnboardingNoticeForm(VersionedOnboardingForm):
    source = forms.ChoiceField(
        choices=(("contract", "Contract"), ("training", "Training"))
    )
    notice = forms.CharField(max_length=80)
    idempotency_key = forms.UUIDField()
