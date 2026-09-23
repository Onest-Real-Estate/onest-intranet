"""Validation for the catalog management screen.

A Django form rather than hand-rolled parsing, so the field rules live in one
place and the repository's standard validation shape falls out of
``form.errors`` for free.

The two fields worth explaining are the ones that are not plain scalars:

* ``setup_steps`` arrives as repeated ``step`` values, because a guide is an
  ordered list and a textarea split on newlines loses the ordering the moment
  somebody pastes a wrapped paragraph.
* ``offices`` arrives as repeated ids, and is only meaningful when the tool is
  *not* company-wide.
"""

from __future__ import annotations

from typing import cast

from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.onboarding_tools.models import (
    OnboardingTool,
    Provisioning,
    ToolGroup,
)
from apps.user.models import Office

#: A guide longer than this is a manual, and belongs in a document the tool
#: links to rather than in a checklist row.
MAX_STEPS = 12
MAX_STEP_LENGTH = 200


class OnboardingToolForm(forms.ModelForm):
    """Create or edit one catalog row."""

    offices = forms.ModelMultipleChoiceField(
        queryset=Office.objects.none(),
        required=False,
        label=_("Applies to"),
    )

    class Meta:
        model = OnboardingTool
        fields = (
            "name",
            "slug",
            "description",
            "group",
            "provisioning",
            "open_url",
            "help_url",
            "contact_label",
            "request_path",
            "company_wide",
            "is_required",
            "is_active",
            "sort_order",
        )

    def __init__(self, *args, scoped_offices=None, steps=None, **kwargs):
        super().__init__(*args, **kwargs)
        # The office choices are the caller's scoped set, so a posted id outside
        # it fails validation rather than being silently accepted.
        offices_field = cast(forms.ModelMultipleChoiceField, self.fields["offices"])
        offices_field.queryset = (
            scoped_offices if scoped_offices is not None else Office.objects.none()
        )
        self._raw_steps = steps
        slug_field = self.fields["slug"]
        if self.instance.pk:
            # Training items and audit records join on the identifier, so a
            # saved tool keeps it. A disabled field ignores whatever is posted
            # and validates the stored value instead.
            slug_field.disabled = True
        else:
            # Derived from the name when left blank, which is almost always.
            slug_field.required = False

    def clean_slug(self) -> str:
        if self.instance.pk:
            return self.instance.slug
        raw = self.cleaned_data.get("slug") or self.data.get("name") or ""
        slug = slugify(str(raw))[:60].strip("-")
        if not slug:
            raise forms.ValidationError(_("Give the tool a short identifier."))
        if OnboardingTool.objects.filter(slug=slug).exists():
            raise forms.ValidationError(
                _("Another tool already uses “%(slug)s”. Choose a different one.")
                % {"slug": slug}
            )
        return slug

    def clean_request_path(self) -> str:
        """An in-app path only.

        It renders as a link on every agent's card, so anything that is not a
        same-origin path — another site, ``//host``, ``javascript:`` — is
        refused rather than trusted because an administrator typed it.
        """
        path = (self.cleaned_data.get("request_path") or "").strip()
        if not path:
            return ""
        if not path.startswith("/") or path.startswith("//") or "\\" in path:
            raise forms.ValidationError(
                _("Use a path inside the Hub that starts with /, such as /support/it.")
            )
        return path

    def clean_group(self) -> str:
        group = str(self.cleaned_data.get("group") or "")
        if group not in ToolGroup.values:
            raise forms.ValidationError(_("Choose which shelf this belongs on."))
        return group

    def clean_provisioning(self) -> str:
        value = str(self.cleaned_data.get("provisioning") or "")
        if value not in Provisioning.values:
            raise forms.ValidationError(_("Choose who creates the account."))
        return value

    def clean_steps(self) -> list[str]:
        """Ordered, trimmed, and bounded. Blank lines are dropped rather than
        stored: an empty step renders as a numbered nothing."""
        steps = [
            str(step).strip()[:MAX_STEP_LENGTH]
            for step in (self._raw_steps or [])
            if str(step).strip()
        ]
        if len(steps) > MAX_STEPS:
            raise forms.ValidationError(
                _("A guide is at most %(count)d steps. Link to a document for more.")
                % {"count": MAX_STEPS}
            )
        return steps

    def clean(self):
        cleaned = super().clean()
        steps = self.clean_steps()
        cleaned["setup_steps"] = steps

        # The rule the database also enforces, surfaced here so the writer is
        # told which field to fix rather than seeing an integrity error.
        if not steps and not (cleaned.get("contact_label") or "").strip():
            self.add_error(
                "contact_label",
                _(
                    "Say who to contact, or give the steps. A tool an agent "
                    "cannot act on is a dead row on their checklist."
                ),
            )

        if not cleaned.get("company_wide") and not cleaned.get("offices"):
            self.add_error(
                "offices",
                _(
                    "Name at least one office or region, or mark the tool as "
                    "applying everywhere."
                ),
            )
        return cleaned
