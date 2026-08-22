"""Forms for the announcement workspace.

Every choice set is rebuilt from the actor's own grant when the form is
constructed, so a submitted office, region, role, or person the actor may not
address fails validation before it reaches the service. The service checks the
same boundary again in :func:`apps.announcements.audience.assert_can_target` —
the form narrows the field, the service enforces the boundary. Neither is
load-bearing on its own, and the form is never the last word.
"""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.announcements.administration import (
    EDITABLE_FIELDS,
    TRANSITIONS,
    publishable_office_queryset,
)
from apps.announcements.audience import (
    AudienceSelector,
    targetable_office_ids,
    targetable_role_codes,
    targetable_user_queryset,
)
from apps.announcements.models import Announcement, AnnouncementCategory
from apps.announcements.taxonomy import PRIORITY_CHOICES
from apps.user.models import Office, User
from apps.user.roles import ROLE_BY_KEY


class AnnouncementForm(forms.ModelForm):
    """Create or edit one announcement's copy, window, CTA, and audience.

    Lifecycle is deliberately absent. A draft saved here reaches nobody, and
    publishing is a separate, separately permissioned action — which is what
    stops "fix a typo" from ever being the request that sends a notice.
    """

    owner_office = forms.ModelChoiceField(
        # Replaced per instance with the actor's own publishable offices.
        queryset=Office.objects.none(),
        label=_("Owning office"),
        help_text=_("Who is publishing. Never widens the audience by itself."),
    )
    category = forms.ModelChoiceField(
        queryset=AnnouncementCategory.objects.none(),
        required=False,
        label=_("Category"),
        # Keyed by the stable code, not the row id. ``code`` is what every
        # other surface already carries — filter URLs, audit payloads, the
        # presentation map, and the option lists this form's own controls are
        # built from — so accepting a primary key here would make the one
        # field that disagrees with the rest of the domain.
        to_field_name="code",
    )
    priority = forms.ChoiceField(
        choices=(("", "—"), *PRIORITY_CHOICES),
        required=False,
        label=_("Priority"),
    )
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
    expected_version = forms.CharField(required=False)

    class Meta:
        model = Announcement
        fields = ("owner_office", *EDITABLE_FIELDS)

    def __init__(self, *args: Any, actor: User, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.actor = actor

        owner_field = cast(forms.ModelChoiceField, self.fields["owner_office"])
        owner_field.queryset = publishable_office_queryset(actor)

        category_field = cast(forms.ModelChoiceField, self.fields["category"])
        # Retired categories stay assignable only on a row that already carries
        # one, so an editor fixing a typo is not forced to reclassify.
        current = self.instance.category_id if self.instance.pk else None
        category_field.queryset = AnnouncementCategory.objects.filter(
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

        for name in ("summary", "body", "publish_at", "expires_at"):
            self.fields[name].required = False
        self.fields["cta_label"].required = False
        self.fields["cta_url"].required = False
        if self.instance.pk:
            # Ownership is the publishing identity and part of the slug's
            # uniqueness scope. Moving it would silently re-aim an announcement
            # that people may already have read.
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
        label = (cleaned.get("cta_label") or "").strip()
        url = (cleaned.get("cta_url") or "").strip()
        if url and not label:
            self.add_error("cta_label", _("Give the button some words."))
        if label and not url:
            self.add_error("cta_url", _("Give the button somewhere to go."))
        cleaned["cta_label"] = label
        cleaned["cta_url"] = url
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
            for name in EDITABLE_FIELDS
            if name in self.cleaned_data
        }

    @property
    def selectors(self) -> list[AudienceSelector]:
        """The requested audience, as selector objects for re-authorization."""
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


class AnnouncementTransitionForm(forms.Form):
    """One lifecycle action plus the version token it must still match."""

    action = forms.ChoiceField(choices=[(value, value) for value in TRANSITIONS])
    expected_version = forms.CharField(required=False)


class AnnouncementPinForm(forms.Form):
    pinned = forms.BooleanField(required=False)
    expected_version = forms.CharField(required=False)
