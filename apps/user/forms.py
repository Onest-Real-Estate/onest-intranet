from collections.abc import Mapping
from typing import Any, cast

from django import forms
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.web.contracts import (
    empty_validation_errors,
    validation_errors,
)

from .administration_fields import (
    AGENT_IDENTIFIER_MAX_LENGTH,
    AGENT_STATUS_CHOICES,
    INTERNAL_NOTES_MAX_LENGTH,
    LICENSE_VERIFICATION_CHOICES,
    VERIFICATION_NOTE_MAX_LENGTH,
    VERIFIED,
    agent_status_options,
    license_verification_options,
    normalize_agent_identifier,
    normalize_internal_notes,
)
from .headshot import MAX_BYTES, MIN_DIM, headshot_public_url, validate_headshot
from .models import Office, User
from .profile_fields import (
    BIO_MAX_LENGTH,
    LANGUAGE_CHOICES,
    MAX_LANGUAGES,
    PREFERRED_CONTACT_CHOICES,
    SOCIAL_PLATFORMS,
    contact_method_options,
    language_options,
    normalize_bio,
    normalize_languages,
    normalize_license_number,
    normalize_name,
    normalize_preferred_contact_method,
    normalize_url,
    social_platform_options,
)
from .roles import ScopeType, is_valid_scope_type
from .services.account_state import (
    BUSINESS_REASON_MAX_LENGTH as ACCOUNT_STATE_REASON_MAX_LENGTH,
)
from .services.agent_administration import (
    ADMINISTERED_FIELDS,
    administration_page_payload,
    administration_summary,
    assignable_office_queryset,
    delegable_role_options,
    scope_target_queryset,
)
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
        office_field = self.fields.get("office")
        if office_field is not None:
            cast(
                forms.ModelChoiceField, office_field
            ).queryset = Office.assignable_queryset()

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


class SelfProfileForm(ProfileForm):
    """Everything an agent may maintain about themselves.

    Extends the onboarding contract rather than restating it, so the fields
    both surfaces share are declared, validated, and normalized exactly once.
    ``Meta.fields`` remains the single self-editable allowlist: email, roles,
    permissions, account status, onboarding state, and internal identifiers
    are absent and cannot be reached through this form.
    """

    preferred_name = forms.CharField(
        label=_("Preferred name"),
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "nickname"}),
    )
    preferred_contact_method = forms.ChoiceField(
        label=_("Preferred contact method"),
        choices=[("", _("No preference"))] + list(PREFERRED_CONTACT_CHOICES),
        required=False,
    )
    license_number = forms.CharField(
        label=_("License number"), max_length=32, required=False
    )
    license_state = forms.ChoiceField(
        label=_("License state"),
        choices=[("", _("Select a state"))] + list(US_STATE_CHOICES),
        required=False,
    )
    license_expires_on = forms.DateField(
        label=_("License expiration"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )
    bio = forms.CharField(
        label=_("Professional bio"),
        required=False,
        max_length=BIO_MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 6}),
    )
    languages = forms.MultipleChoiceField(
        label=_("Languages"),
        choices=LANGUAGE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    # Declared as text, not URLField: a bare "example.com" is what people type,
    # and ``normalize_url`` upgrades it rather than rejecting it.
    website_url = forms.CharField(label=_("Website"), required=False)
    linkedin_url = forms.CharField(label=_("LinkedIn"), required=False)
    facebook_url = forms.CharField(label=_("Facebook"), required=False)
    instagram_url = forms.CharField(label=_("Instagram"), required=False)
    x_url = forms.CharField(label=_("X"), required=False)

    class Meta(ProfileForm.Meta):
        fields = ProfileForm.Meta.fields + (
            "preferred_name",
            "preferred_contact_method",
            "license_number",
            "license_state",
            "license_expires_on",
            "bio",
            "languages",
            "website_url",
            "linkedin_url",
            "facebook_url",
            "instagram_url",
            "x_url",
        )

    def __init__(self, *args, can_change_office: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_change_office = can_change_office
        if not can_change_office:
            # Removing the bound field is the enforcement: ``construct_instance``
            # only writes model attributes that survive in ``cleaned_data``.
            self.fields.pop("office", None)

    def clean_preferred_name(self):
        return normalize_name(self.cleaned_data.get("preferred_name", ""))

    def clean_preferred_contact_method(self):
        return normalize_preferred_contact_method(
            self.cleaned_data.get("preferred_contact_method", "")
        )

    def clean_license_number(self):
        return normalize_license_number(self.cleaned_data.get("license_number", ""))

    def clean_bio(self):
        return normalize_bio(self.cleaned_data.get("bio", ""))

    def clean_languages(self):
        return normalize_languages(self.cleaned_data.get("languages", []))

    def clean_website_url(self):
        return normalize_url(self.cleaned_data.get("website_url", ""), label="website")

    def _clean_social(self, field: str) -> str:
        platform = next(item for item in SOCIAL_PLATFORMS if item.field == field)
        return normalize_url(
            self.cleaned_data.get(field, ""),
            allowed_hosts=platform.hosts,
            label=platform.label,
        )

    def clean_linkedin_url(self):
        return self._clean_social("linkedin_url")

    def clean_facebook_url(self):
        return self._clean_social("facebook_url")

    def clean_instagram_url(self):
        return self._clean_social("instagram_url")

    def clean_x_url(self):
        return self._clean_social("x_url")

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("license_number", "")
        if not number and (
            cleaned.get("license_state") or cleaned.get("license_expires_on")
        ):
            self.add_error(
                "license_number",
                _("Add your license number alongside its state or expiration date."),
            )
        return cleaned


# Django field names a user is allowed to submit for themselves. Anything not
# listed is either administrative or derived, and the view rejects it outright.
SELF_EDITABLE_FIELDS: frozenset[str] = frozenset(SelfProfileForm.Meta.fields)


def form_errors(form: forms.BaseForm) -> dict:
    """Return the shared field/form validation payload for Inertia."""
    return validation_errors(form)


# camelCase Inertia prop → Django field name. One map per surface so the two
# forms and the two pages cannot drift out of step.
ONBOARDING_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("firstName", "first_name"),
    ("lastName", "last_name"),
    ("phoneNumber", "phone_number"),
    ("streetAddress", "street_address"),
    ("city", "city"),
    ("state", "state"),
    ("zipCode", "zip_code"),
    ("officeId", "office"),
    ("mlsNumber", "mls_number"),
    ("nrdsNumber", "nrds_number"),
)

SELF_PROFILE_FIELD_MAP: tuple[tuple[str, str], ...] = (
    *ONBOARDING_FIELD_MAP,
    ("preferredName", "preferred_name"),
    ("preferredContactMethod", "preferred_contact_method"),
    ("licenseNumber", "license_number"),
    ("licenseState", "license_state"),
    ("licenseExpiresOn", "license_expires_on"),
    ("bio", "bio"),
    ("websiteUrl", "website_url"),
    *tuple((platform.prop, platform.field) for platform in SOCIAL_PLATFORMS),
)


def _stored_value(user: User, field: str):
    if field == "office":
        return str(user.office.pk) if user.office else ""
    value = getattr(user, field)
    if field == "license_expires_on":
        return value.isoformat() if value else ""
    return value or ""


def _posted_languages(user: User, posted: Mapping[str, Any] | None) -> list[str]:
    """Language codes, preferring what was just submitted over what is stored."""
    if posted is None:
        return list(user.languages or [])
    # QueryDict keeps every checked box; a plain mapping keeps only the last.
    getlist = getattr(posted, "getlist", None)
    if callable(getlist):
        return [str(code) for code in getlist("languages")]
    raw = posted.get("languages", [])
    if isinstance(raw, (list, tuple)):
        return [str(code) for code in raw]
    return [str(raw)] if raw else []


def profile_initial(
    user: User,
    posted: Mapping[str, Any] | None = None,
    *,
    request=None,
    field_map: tuple[tuple[str, str], ...] = ONBOARDING_FIELD_MAP,
    include_languages: bool = False,
) -> dict:
    """Values for the React form. Posted data wins so a 422 doesn't wipe the form."""

    initial = {
        prop: (
            posted.get(field, "") if posted is not None else _stored_value(user, field)
        )
        for prop, field in field_map
    }
    if include_languages:
        initial["languages"] = _posted_languages(user, posted)
    initial["headshotUrl"] = (
        headshot_public_url(request, user)
        if request
        else (user.headshot.url if user.headshot else None)
    )
    return initial


def profile_page_props(
    user: User,
    *,
    request=None,
    errors: dict | None = None,
    posted: Mapping[str, Any] | None = None,
):
    """Props for the onboarding page — the essential fields only."""
    return {
        "initial": profile_initial(user, posted, request=request),
        "validation": errors or empty_validation_errors(),
        "offices": Office.grouped_choices(),
        "states": [{"code": code, "name": name} for code, name in US_STATE_CHOICES],
    }


def _office_payload(user: User) -> dict | None:
    office = user.office
    if office is None:
        return None
    return {
        "id": office.pk,
        "name": office.name,
        "pathLabel": office.path_label(),
        "regionName": office.region_name(),
        "streetAddress": office.street_address,
        "city": office.city,
        "state": office.state,
        "zipCode": office.zip_code,
        "mainPhone": office.main_phone,
    }


def profile_identity(user: User) -> dict:
    """Facts about the account that the account holder cannot change.

    Rendered read-only on the page and never accepted back from it: the
    Microsoft directory owns the email, and an administrator owns the rest.
    """
    from .services.profile import license_status, role_labels

    return {
        "email": user.email,
        "legalName": user.get_full_name().strip(),
        "displayName": str(user),
        "preferredDisplayName": user.preferred_display_name(),
        "roles": role_labels(user),
        "office": _office_payload(user),
        "accountStatus": "active" if user.is_active else "inactive",
        "isStaff": user.is_staff,
        "memberSince": user.date_joined.isoformat() if user.date_joined else None,
        "onboardingCompletedAt": (
            user.profile_completed_at.isoformat() if user.profile_completed_at else None
        ),
        "licenseStatus": license_status(user),
        # Broker-controlled values, read-only here and rejected by
        # ``profile_submit`` if they ever appear in a POST. Operational notes
        # are never part of this payload.
        "administrative": administration_summary(user),
    }


def self_profile_page_props(
    user: User,
    *,
    request=None,
    errors: dict | None = None,
    posted: Mapping[str, Any] | None = None,
):
    """Props for the self-service profile page."""
    from .services.profile import can_self_assign_office, profile_completeness

    can_change_office = can_self_assign_office(user)
    return {
        "initial": profile_initial(
            user,
            posted,
            request=request,
            field_map=SELF_PROFILE_FIELD_MAP,
            include_languages=True,
        ),
        "validation": errors or empty_validation_errors(),
        "offices": Office.grouped_choices() if can_change_office else [],
        "states": [{"code": code, "name": name} for code, name in US_STATE_CHOICES],
        "languageOptions": language_options(),
        "contactMethods": contact_method_options(),
        "socialPlatforms": social_platform_options(),
        "identity": profile_identity(user),
        "editable": {"office": can_change_office},
        "completeness": profile_completeness(user),
        "limits": {
            "headshotMaxBytes": MAX_BYTES,
            "headshotMinDimension": MIN_DIM,
            "bioMaxLength": BIO_MAX_LENGTH,
            "maxLanguages": MAX_LANGUAGES,
        },
    }


# ---------------------------------------------------------------------------
# Administrative profile (broker-controlled)
# ---------------------------------------------------------------------------


class AgentAdministrationForm(forms.ModelForm):
    """The broker-controlled half of a profile.

    Mass-assignment guard
    ---------------------
    ``Meta.fields`` is exactly ``ADMINISTERED_FIELDS``. Roles, permissions,
    staff flags, account status, email, and every self-service field are absent
    and cannot be reached through this form — role assignments are granted
    through their own service, which enforces its own delegation rules.

    The office queryset is built from the *actor's* scope, never from the
    submitted value, so an office id from outside their region fails here as
    well as in the service.
    """

    expected_version = forms.CharField(required=False, widget=forms.HiddenInput)

    office = forms.ModelChoiceField(
        label=_("Office"),
        queryset=Office.objects.none(),
        required=True,
        empty_label=_("Select an office"),
    )
    agent_status = forms.ChoiceField(
        label=_("Agent status"),
        choices=AGENT_STATUS_CHOICES,
        required=True,
    )
    start_date = forms.DateField(
        label=_("Start date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )
    agent_identifier = forms.CharField(
        label=_("Agent ID"),
        max_length=AGENT_IDENTIFIER_MAX_LENGTH,
        required=False,
    )
    license_verification_state = forms.ChoiceField(
        label=_("License verification"),
        choices=LICENSE_VERIFICATION_CHOICES,
        required=True,
    )
    license_verification_note = forms.CharField(
        label=_("Verification note"),
        max_length=VERIFICATION_NOTE_MAX_LENGTH,
        required=False,
    )
    internal_notes = forms.CharField(
        label=_("Operational notes"),
        required=False,
        max_length=INTERNAL_NOTES_MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    class Meta:
        model = User
        fields = tuple(ADMINISTERED_FIELDS)

    def __init__(self, *args, actor: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        # Captured before ``_post_clean`` mutates the instance — see
        # ``_get_validation_exclusions``.
        self._original_office = getattr(self.instance, "office", None)
        office_field = cast(forms.ModelChoiceField, self.fields["office"])
        allowed = assignable_office_queryset(actor)
        current = getattr(self.instance, "office_id", None)
        if current:
            # An office that has since been retired stays selectable so the
            # record can be corrected without first being moved out of it.
            allowed = Office.objects.filter(
                Q(pk__in=allowed.values("pk")) | Q(pk=current)
            ).select_related("region", "parent")
        office_field.queryset = allowed.order_by("sort_order", "name")

    def clean_office(self):
        office = self.cleaned_data.get("office")
        if office is None:
            return office
        unchanged = office == self._original_office
        if not unchanged and (not office.is_active or not office.is_assignable):
            raise forms.ValidationError(
                _("That office is closed. Pick an office that is still open.")
            )
        return office

    def clean_agent_identifier(self):
        raw = self.cleaned_data.get("agent_identifier") or ""
        value = normalize_agent_identifier(raw)
        if not value:
            return value
        clash = User.objects.filter(agent_identifier=value)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("Another user already has that agent ID."))
        return value

    def clean_internal_notes(self):
        return normalize_internal_notes(self.cleaned_data.get("internal_notes") or "")

    def clean_start_date(self):
        value = self.cleaned_data.get("start_date")
        if value is None:
            return value
        today = timezone.localdate()
        if value > today.replace(year=today.year + 1):
            raise forms.ValidationError(
                _("Start dates more than a year out are almost always a typo.")
            )
        if value.year < 1950:
            raise forms.ValidationError(_("Enter a start date after 1950."))
        return value

    def clean(self):
        cleaned = super().clean()
        state = cleaned.get("license_verification_state")
        if state == VERIFIED and not self.instance.license_number:
            self.add_error(
                "license_verification_state",
                _(
                    "This user has not recorded a license number yet, so there "
                    "is nothing to verify."
                ),
            )
        return cleaned


class RoleAssignmentGrantForm(forms.Form):
    """Grant one role at one scope, optionally dated.

    The role and scope choices are rebuilt from the actor's own delegation
    every time: a role that is not offered is a role the assignment service
    would refuse anyway, and both checks run server-side.
    """

    role = forms.ChoiceField(label=_("Role"), choices=())
    scope_type = forms.ChoiceField(label=_("Scope"), choices=ScopeType.CHOICES)
    scope_office = forms.ModelChoiceField(
        label=_("Office or region"),
        queryset=Office.objects.none(),
        required=False,
    )
    starts_at = forms.DateTimeField(
        label=_("Effective from"),
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    ends_at = forms.DateTimeField(
        label=_("Effective until"),
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    business_reason = forms.CharField(
        label=_("Business reason"),
        required=True,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    expected_version = forms.CharField(required=False, widget=forms.HiddenInput)
    confirmed = forms.BooleanField(required=False)

    def __init__(self, *args, actor: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        options = delegable_role_options(actor)
        cast(forms.ChoiceField, self.fields["role"]).choices = [
            (option["value"], option["label"]) for option in options
        ]
        allowed_scopes = {
            scope["value"] for option in options for scope in option["scopes"]
        }
        cast(forms.ChoiceField, self.fields["scope_type"]).choices = [
            (value, label)
            for value, label in ScopeType.CHOICES
            if value in allowed_scopes
        ]
        cast(
            forms.ModelChoiceField, self.fields["scope_office"]
        ).queryset = scope_target_queryset(actor)

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        scope_type = cleaned.get("scope_type")
        scope_office = cleaned.get("scope_office")
        if role and scope_type and not is_valid_scope_type(role, scope_type):
            self.add_error("scope_type", _("This role cannot use that scope."))
        if scope_type in ScopeType.ORG_LESS and scope_office is not None:
            self.add_error(
                "scope_office",
                _("This scope does not target an office or region."),
            )
        if scope_type in {ScopeType.REGION, ScopeType.OFFICE} and scope_office is None:
            self.add_error("scope_office", _("Choose the office or region to cover."))
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        if starts_at and ends_at and ends_at < starts_at:
            self.add_error("ends_at", _("The end date comes before the start date."))
        if ends_at and ends_at <= timezone.now():
            self.add_error("ends_at", _("An end date in the past grants nothing."))
        return cleaned


class RoleAssignmentRevokeForm(forms.Form):
    assignment = forms.IntegerField(widget=forms.HiddenInput)
    business_reason = forms.CharField(required=True, max_length=500)
    expected_version = forms.CharField(required=False, widget=forms.HiddenInput)
    confirmed = forms.BooleanField(required=False)


class RoleAssignmentEditForm(forms.Form):
    assignment = forms.IntegerField(widget=forms.HiddenInput)
    starts_at = forms.DateTimeField(
        label=_("Effective from"),
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    ends_at = forms.DateTimeField(
        label=_("Effective until"),
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    business_reason = forms.CharField(
        label=_("Business reason"),
        required=True,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    expected_version = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        if starts_at and ends_at and ends_at < starts_at:
            self.add_error("ends_at", _("The end date comes before the start date."))
        return cleaned


class RoleAssignmentPreviewForm(forms.Form):
    """Dry-run a grant, edit, or revoke before confirmation."""

    action = forms.ChoiceField(
        choices=(
            ("grant", "grant"),
            ("edit", "edit"),
            ("revoke", "revoke"),
        )
    )
    role = forms.CharField(required=False)
    scope_type = forms.CharField(required=False)
    scope_office = forms.ModelChoiceField(
        queryset=Office.objects.none(), required=False
    )
    assignment = forms.IntegerField(required=False)
    starts_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"],
    )
    ends_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"],
    )

    def __init__(self, *args, actor: User, **kwargs):
        super().__init__(*args, **kwargs)
        cast(
            forms.ModelChoiceField, self.fields["scope_office"]
        ).queryset = scope_target_queryset(actor)


ADMINISTRATION_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("officeId", "office"),
    ("agentStatus", "agent_status"),
    ("startDate", "start_date"),
    ("agentIdentifier", "agent_identifier"),
    ("licenseVerificationState", "license_verification_state"),
    ("licenseVerificationNote", "license_verification_note"),
    ("internalNotes", "internal_notes"),
)


def administration_page_props(
    actor: User,
    target: User,
    *,
    errors: dict | None = None,
    posted: Mapping[str, Any] | None = None,
):
    """Props for the administration page, already narrowed to the actor's scope.

    Posted data wins over stored values so a 422 or a version conflict does not
    wipe what the administrator typed.
    """
    payload = administration_page_payload(actor, target)
    if posted is not None:
        # Only echo back the props the payload already carries: a field the
        # actor may not read must not reappear because they posted it.
        payload["values"] = {
            prop: posted.get(field, "")
            for prop, field in ADMINISTRATION_FIELD_MAP
            if prop in payload["values"]
        }
    return {
        "administration": payload,
        "validation": errors or empty_validation_errors(),
        "statusOptions": agent_status_options(),
        "verificationOptions": license_verification_options(),
    }


class AccountStateForm(forms.Form):
    """Disable or reactivate one account. Nothing else travels on this POST.

    Deliberately not a ``ModelForm``: ``is_active`` reached through a generic
    model form is one crafted field away from ``is_staff``. The intent arrives
    as a verb, the freshness token arrives beside it, and the service re-checks
    both.
    """

    action = forms.ChoiceField(
        choices=(("disable", _("Disable")), ("reactivate", _("Reactivate"))),
        error_messages={"invalid_choice": _("Choose disable or reactivate.")},
    )
    business_reason = forms.CharField(
        label=_("Business reason"),
        required=True,
        max_length=ACCOUNT_STATE_REASON_MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"required": _("Say why this account is changing hands.")},
    )
    expected_version = forms.CharField(required=False, widget=forms.HiddenInput)

    @property
    def enabled(self) -> bool:
        return self.cleaned_data["action"] == "reactivate"

    def clean_business_reason(self):
        value = " ".join((self.cleaned_data.get("business_reason") or "").split())
        if not value:
            raise forms.ValidationError(_("Say why this account is changing hands."))
        return value
