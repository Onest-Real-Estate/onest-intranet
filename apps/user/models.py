from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .administration_fields import (
    ACTIVE as ACTIVE_AGENT_STATUS,
)
from .administration_fields import (
    AGENT_IDENTIFIER_MAX_LENGTH,
    AGENT_STATUS_CHOICES,
    LICENSE_VERIFICATION_CHOICES,
    VERIFICATION_NOTE_MAX_LENGTH,
    normalize_agent_identifier,
    normalize_agent_status,
    normalize_internal_notes,
    normalize_license_verification_state,
)
from .administration_fields import (
    UNVERIFIED as UNVERIFIED_LICENSE_STATE,
)
from .administration_fields import (
    VERIFIED as VERIFIED_LICENSE_STATE,
)
from .headshot import headshot_upload_path
from .profile_fields import (
    BIO_MAX_LENGTH,
    LANGUAGE_CHOICES,
    MAX_LICENSE_FUTURE_YEARS,
    MAX_URL_LENGTH,
    PREFERRED_CONTACT_CHOICES,
    SOCIAL_PLATFORMS,
    normalize_bio,
    normalize_languages,
    normalize_license_number,
    normalize_name,
    normalize_preferred_contact_method,
    normalize_url,
)
from .roles import ScopeType, is_valid_scope_type, normalize_role_code
from .us import (
    US_STATE_CHOICES,
    US_STATE_CODES,
    normalize_nrds,
    normalize_us_phone,
    normalize_us_zip,
)


class UserManager(BaseUserManager):
    """Manager for the email-based User model."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_("The given email must be set"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(email, password, **extra_fields)


class Office(models.Model):
    """Org tree node: head office → region → regional office → branch."""

    class Kind(models.TextChoices):
        HEAD_OFFICE = "head_office", _("Head office")
        REGION = "region", _("Region")
        REGIONAL_OFFICE = "regional_office", _("Regional office")
        BRANCH = "branch", _("Branch")

    # Parent kind required for each child kind. Head office is the root.
    _PARENT_KIND = {
        Kind.REGION: Kind.HEAD_OFFICE,
        Kind.REGIONAL_OFFICE: Kind.REGION,
        Kind.BRANCH: Kind.REGIONAL_OFFICE,
    }

    name = models.CharField(_("name"), max_length=150)
    stable_key = models.SlugField(_("stable key"), unique=True, max_length=80)
    slug = models.SlugField(_("slug"), unique=True, max_length=80)
    kind = models.CharField(_("kind"), max_length=32, choices=Kind.choices)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("parent"),
        related_name="children",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    region = models.ForeignKey(
        "self",
        verbose_name=_("region"),
        related_name="region_offices",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    # Regions group offices but are not themselves a place someone "works at".
    is_assignable = models.BooleanField(
        _("assignable"),
        default=True,
        help_text=_("Whether a user can pick this office as their work location."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    street_address = models.CharField(_("street address"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    state = models.CharField(
        _("state"), max_length=2, choices=US_STATE_CHOICES, blank=True
    )
    zip_code = models.CharField(_("ZIP code"), max_length=10, blank=True)
    main_phone = models.CharField(_("main phone"), max_length=30, blank=True)
    public_email = models.EmailField(_("public email"), blank=True)
    internal_email = models.EmailField(_("internal email"), blank=True)
    office_hours = models.JSONField(_("office hours"), default=list, blank=True)
    parking_instructions = models.TextField(_("parking instructions"), blank=True)
    access_instructions = models.TextField(_("access instructions"), blank=True)
    access_instructions_internal = models.BooleanField(
        _("access instructions are internal"),
        default=True,
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("office")
        verbose_name_plural = _("offices")
        indexes = [
            models.Index(fields=["parent"], name="user_office_parent"),
            models.Index(
                fields=["is_active", "is_assignable"],
                name="user_office_active_assignable",
            ),
            models.Index(
                fields=["region", "is_active"], name="user_office_region_active"
            ),
            models.Index(fields=["kind", "is_active"], name="user_office_kind_active"),
        ]

    def __str__(self):
        return self.path_label()

    def clean(self):
        super().clean()
        if self.pk:
            original = (
                type(self).objects.filter(pk=self.pk).values("stable_key").first()
            )
            if original and original["stable_key"] != self.stable_key:
                raise ValidationError(
                    {"stable_key": _("Stable identity cannot be changed once created.")}
                )
        if self.kind == self.Kind.HEAD_OFFICE and self.parent:
            raise ValidationError(
                {"parent": _("The head office cannot have a parent.")}
            )
        if self.kind == self.Kind.HEAD_OFFICE:
            pass
        else:
            expected = self._PARENT_KIND.get(self.kind)
            if not self.parent:
                raise ValidationError(
                    {
                        "parent": _(
                            "This office must sit under a parent in the org tree."
                        )
                    }
                )
            parent_kind = getattr(self.parent, "kind", None)
            if parent_kind != expected:
                raise ValidationError(
                    {
                        "parent": _("A %(kind)s must sit under a %(parent)s.")
                        % {
                            "kind": self.Kind(self.kind).label.lower(),
                            "parent": self.Kind(expected).label.lower(),
                        }
                    }
                )
        parent = self.parent
        if parent is not None and parent.pk == self.pk:
            raise ValidationError({"parent": _("An office cannot be its own parent.")})
        self._validate_parent_cycle()
        self._validate_region_consistency()
        errors = {}
        if self.state and self.state not in US_STATE_CODES:
            errors["state"] = _("Enter a valid US state code.")
        if self.zip_code:
            try:
                self.zip_code = normalize_us_zip(self.zip_code)
            except ValidationError as exc:
                errors["zip_code"] = exc
        if self.main_phone:
            try:
                self.main_phone = normalize_us_phone(self.main_phone)
            except ValidationError as exc:
                errors["main_phone"] = exc
        if errors:
            raise ValidationError(errors)

    def _validate_parent_cycle(self) -> None:
        seen: set[int] = set()
        node = self.parent
        while node is not None:
            if node.pk == self.pk:
                raise ValidationError(
                    {"parent": _("This parent selection creates a hierarchy cycle.")}
                )
            if node.pk in seen:
                raise ValidationError(
                    {"parent": _("This parent selection creates a hierarchy cycle.")}
                )
            seen.add(node.pk)
            node = node.parent

    def _nearest_region(self) -> "Office | None":
        if self.kind == self.Kind.HEAD_OFFICE:
            return None
        if self.kind == self.Kind.REGION:
            return self
        node = self.parent
        seen: set[int] = set()
        while node is not None and node.pk not in seen:
            seen.add(node.pk)
            if node.kind == self.Kind.REGION:
                return node
            node = node.parent
        return None

    def _validate_region_consistency(self) -> None:
        expected_region = self._nearest_region()
        if self.kind == self.Kind.HEAD_OFFICE and self.region is not None:
            raise ValidationError(
                {"region": _("The head office must not belong to a region.")}
            )
        if self.kind == self.Kind.REGION and self.region_id not in {None, self.pk}:
            raise ValidationError(
                {"region": _("A region office must point to itself as its region.")}
            )
        if expected_region is not None and self.region_id not in {
            None,
            expected_region.pk,
        }:
            raise ValidationError(
                {"region": _("Region must match the nearest region in the hierarchy.")}
            )

    def path_label(self) -> str:
        """Human path, e.g. ``Mid-Atlantic / Virginia / Charlottesville VA``."""
        names: list[str] = []
        node: Office | None = self
        seen: set[int] = set()
        while node is not None and id(node) not in seen:
            seen.add(id(node))
            names.append(node.name)
            node = node.parent
        names.reverse()
        return " / ".join(names)

    def region_name(self) -> str:
        """Nearest region (or 'Head office') for grouping pick-lists."""
        region = self.region or self._nearest_region()
        if region is not None:
            return region.name
        return self.name

    @classmethod
    def active_queryset(cls):
        return cls.objects.filter(is_active=True)

    @classmethod
    def assignable_queryset(cls):
        return (
            cls.active_queryset()
            .filter(is_assignable=True)
            .select_related(
                "parent", "parent__parent", "parent__parent__parent", "region"
            )
            .order_by("sort_order", "name")
        )

    @classmethod
    def visible_queryset(cls):
        return cls.objects.select_related(
            "parent", "parent__parent", "parent__parent__parent", "region"
        ).order_by("sort_order", "name")

    @classmethod
    def for_region(cls, region: "Office"):
        return cls.visible_queryset().filter(region=region)

    @classmethod
    def grouped_choices(cls) -> list[dict]:
        """Offices grouped by region, for a ``<select>`` with optgroups."""
        from apps.user.office_payloads import office_selector_payload

        groups: dict[str, list[dict]] = {}
        order: list[str] = []
        for office in cls.assignable_queryset():
            group = office.region_name()
            if group not in groups:
                groups[group] = []
                order.append(group)
            groups[group].append(office_selector_payload(office))
        return [{"label": label, "offices": groups[label]} for label in order]

    @property
    def branch_manager(self):
        return (
            OfficeContactAssignment.objects.filter(
                office=self,
                assignment_type=OfficeContactAssignment.AssignmentType.MANAGER,
            )
            .select_related("user")
            .first()
        )

    @property
    def branch_admin(self):
        return (
            OfficeContactAssignment.objects.filter(
                office=self,
                assignment_type=OfficeContactAssignment.AssignmentType.ADMIN,
            )
            .select_related("user")
            .first()
        )

    @property
    def broker_contacts(self):
        return OfficeContactAssignment.objects.filter(
            office=self,
            assignment_type=OfficeContactAssignment.AssignmentType.BROKER_CONTACT,
        ).select_related("user")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        desired_region_id = None
        if self.kind == self.Kind.REGION:
            desired_region_id = self.pk
        elif self.kind != self.Kind.HEAD_OFFICE:
            nearest_region = self._nearest_region()
            desired_region_id = nearest_region.pk if nearest_region else None
        if self.region_id != desired_region_id:
            type(self).objects.filter(pk=self.pk).update(region_id=desired_region_id)
            self.region_id = desired_region_id


class OfficeContactAssignment(models.Model):
    class AssignmentType(models.TextChoices):
        MANAGER = "manager", _("Manager")
        ADMIN = "admin", _("Admin")
        BROKER_CONTACT = "broker_contact", _("Broker contact")

    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="contact_assignments",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        "User",
        verbose_name=_("user"),
        related_name="office_contact_assignments",
        on_delete=models.PROTECT,
    )
    assignment_type = models.CharField(
        _("assignment type"),
        max_length=32,
        choices=AssignmentType.choices,
    )
    is_primary = models.BooleanField(_("primary"), default=False)
    starts_at = models.DateField(_("starts at"), null=True, blank=True)
    ends_at = models.DateField(_("ends at"), null=True, blank=True)

    class Meta:
        ordering = ["assignment_type", "-is_primary", "user__email"]
        verbose_name = _("office contact assignment")
        verbose_name_plural = _("office contact assignments")
        constraints = [
            models.UniqueConstraint(
                fields=["office", "user", "assignment_type"],
                name="user_office_contact_unique",
            ),
            models.UniqueConstraint(
                fields=["office", "assignment_type"],
                condition=Q(is_primary=True),
                name="user_office_contact_primary_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["office", "assignment_type"],
                name="user_office_contact_type",
            ),
        ]

    def __str__(self):
        return f"{self.office} / {self.assignment_type} / {self.user}"

    def clean(self):
        super().clean()
        errors = {}
        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            errors["ends_at"] = _("End date cannot be earlier than the start date.")
        user_office = self.user.office
        office_pk = self.office.pk if self.office else None
        if user_office is not None and user_office.pk != office_pk:
            errors["user"] = _("Assigned staff must belong to the same office.")
        if errors:
            raise ValidationError(errors)


class User(AbstractUser):
    """Custom user identified by email (no username) — used with allauth SSO.

    first_name/last_name (from AbstractUser) are populated by the Microsoft
    provider; display_name is the name shown in the UI, falling back to email.
    """

    username = None
    email = models.EmailField(_("email address"), unique=True)
    display_name = models.CharField(_("display name"), max_length=150, blank=True)
    phone_number = models.CharField(_("phone number"), max_length=30, blank=True)
    street_address = models.CharField(_("street address"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    state = models.CharField(
        _("state"), max_length=2, choices=US_STATE_CHOICES, blank=True
    )
    zip_code = models.CharField(_("ZIP code"), max_length=10, blank=True)
    mls_number = models.CharField(
        _("MLS number"),
        max_length=32,
        blank=True,
        help_text=_("Optional. Can be added later from the profile page."),
    )
    nrds_number = models.CharField(
        _("NRDS number"),
        max_length=9,
        blank=True,
        help_text=_("Optional 8- or 9-digit NRDS ID. Can be added later."),
    )
    preferred_name = models.CharField(
        _("preferred name"),
        max_length=150,
        blank=True,
        help_text=_(
            "What colleagues and clients should call you, if not your legal first name."
        ),
    )
    license_number = models.CharField(
        _("license number"),
        max_length=32,
        blank=True,
        help_text=_("Real estate license number, as printed on the license."),
    )
    license_state = models.CharField(
        _("license state"),
        max_length=2,
        choices=US_STATE_CHOICES,
        blank=True,
    )
    license_expires_on = models.DateField(
        _("license expires on"),
        null=True,
        blank=True,
    )
    website_url = models.URLField(_("website"), max_length=MAX_URL_LENGTH, blank=True)
    linkedin_url = models.URLField(_("LinkedIn"), max_length=MAX_URL_LENGTH, blank=True)
    facebook_url = models.URLField(_("Facebook"), max_length=MAX_URL_LENGTH, blank=True)
    instagram_url = models.URLField(
        _("Instagram"), max_length=MAX_URL_LENGTH, blank=True
    )
    x_url = models.URLField(_("X"), max_length=MAX_URL_LENGTH, blank=True)
    bio = models.TextField(
        _("professional bio"),
        max_length=BIO_MAX_LENGTH,
        blank=True,
        help_text=_("A short introduction shown alongside your name in the hub."),
    )
    # A short, closed set of codes with no per-language reporting need: a JSON
    # list keeps the value together instead of spreading it over a join table.
    languages = models.JSONField(
        _("languages"),
        default=list,
        blank=True,
        help_text=_("Language codes from %(count)d supported options.")
        % {"count": len(LANGUAGE_CHOICES)},
    )
    preferred_contact_method = models.CharField(
        _("preferred contact method"),
        max_length=16,
        choices=PREFERRED_CONTACT_CHOICES,
        blank=True,
    )
    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="members",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    headshot = models.ImageField(
        _("headshot"),
        # The callable, not its dotted name: quoting it turned the path into a
        # literal directory and stored the browser-supplied filename, which is
        # exactly what ``headshot_upload_path`` exists to prevent.
        upload_to=headshot_upload_path,
        null=True,
        blank=True,
        help_text=_("Profile photo. Must be JPEG/PNG, ≤5 MB, at least 200×200 px."),
    )
    profile_completed = models.BooleanField(
        _("profile completed"),
        default=False,
        help_text=_(
            "Whether the user finished the post-signup details flow "
            "(onboarding). New SSO users are redirected to /onboarding "
            "until this is true."
        ),
    )
    profile_completed_at = models.DateTimeField(
        _("profile completed at"),
        null=True,
        blank=True,
    )
    onboarding_version = models.PositiveSmallIntegerField(
        _("onboarding version"),
        default=0,
        help_text=_(
            "Incremented on each admin reset so historical completions remain "
            "distinguishable from re-onboardings."
        ),
    )

    # ------------------------------------------------------------------
    # Broker-controlled administration. Never writable from /profile — see
    # ``apps.user.services.agent_administration`` for the policy that owns
    # every one of these, and ``docs/agent-administration.md`` for why.
    # ------------------------------------------------------------------
    agent_status = models.CharField(
        _("agent status"),
        max_length=16,
        choices=AGENT_STATUS_CHOICES,
        default=ACTIVE_AGENT_STATUS,
        help_text=_("Where this person stands with the brokerage."),
    )
    start_date = models.DateField(
        _("start date"),
        null=True,
        blank=True,
        help_text=_("The date this person joined the brokerage."),
    )
    agent_identifier = models.CharField(
        _("agent ID"),
        max_length=AGENT_IDENTIFIER_MAX_LENGTH,
        blank=True,
        help_text=_("Internal identifier used by back-office systems."),
    )
    internal_notes = models.TextField(
        _("operational notes"),
        blank=True,
        help_text=_(
            "Administrative notes about this person. Visible only to "
            "administrators with the change permission; never shown to the "
            "person themselves and never written into audit values."
        ),
    )
    license_verification_state = models.CharField(
        _("license verification"),
        max_length=16,
        choices=LICENSE_VERIFICATION_CHOICES,
        default=UNVERIFIED_LICENSE_STATE,
        help_text=_("Set by the broker after checking the state license record."),
    )
    license_verified_at = models.DateTimeField(
        _("license verified at"), null=True, blank=True
    )
    license_verified_by = models.ForeignKey(
        "self",
        verbose_name=_("license verified by"),
        related_name="verified_licenses",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    license_verification_note = models.CharField(
        _("verification note"),
        max_length=VERIFICATION_NOTE_MAX_LENGTH,
        blank=True,
    )
    # Doubles as the optimistic-concurrency token for the administration
    # form: two administrators editing the same record cannot silently
    # overwrite each other because the second save no longer matches.
    administration_updated_at = models.DateTimeField(
        _("administration updated at"), null=True, blank=True
    )
    administration_updated_by = models.ForeignKey(
        "self",
        verbose_name=_("administration updated by"),
        related_name="administered_users",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        # Restated rather than inherited from ``AbstractUser.Meta`` so the
        # static checker can see it; the values are identical.
        verbose_name = _("user")
        verbose_name_plural = _("users")
        # Separate from Django's ``change_user``: holding the broad model
        # permission through the admin site is not the same grant as editing
        # the administrative half of somebody's profile in the hub.
        permissions = (
            ("view_user_administration", _("Can view administrative profile fields")),
            (
                "change_user_administration",
                _("Can change administrative profile fields"),
            ),
            # Disabling somebody is not "changing a field": it ends their
            # sessions and their access. It carries its own grant so an
            # administrator who maintains records is not, by that fact, an
            # administrator who can lock people out.
            (
                "manage_account_state",
                _("Can disable or reactivate user accounts"),
            ),
        )
        constraints = [
            models.UniqueConstraint(
                fields=["agent_identifier"],
                condition=~Q(agent_identifier=""),
                name="user_agent_identifier_unique_when_set",
            ),
        ]

    def __str__(self):
        return self.display_name or self.get_full_name() or self.email

    def clean(self):
        super().clean()
        errors = {}
        if self.phone_number:
            try:
                self.phone_number = normalize_us_phone(self.phone_number)
            except ValidationError as exc:
                errors["phone_number"] = exc
        if self.zip_code:
            try:
                self.zip_code = normalize_us_zip(self.zip_code)
            except ValidationError as exc:
                errors["zip_code"] = exc
        if self.nrds_number:
            try:
                self.nrds_number = normalize_nrds(self.nrds_number)
            except ValidationError as exc:
                errors["nrds_number"] = exc
        if self.office and (not self.office.is_assignable or not self.office.is_active):
            # An office that closed under somebody already seated in it is a
            # fact about the org, not a mistake in this submission. Only a
            # *move* into a closed office is rejected — otherwise the record
            # of someone leaving a closed branch could never be saved.
            stored = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("office", flat=True)
                .first()
                if self.pk
                else None
            )
            if stored != self.office.pk:
                errors["office"] = _(
                    "Pick an active office from the locations we serve."
                )
        # Verifying a license nobody recorded verifies nothing.
        if self.license_verification_state == VERIFIED_LICENSE_STATE and not (
            self.license_number
        ):
            errors["license_verification_state"] = _(
                "Record the license number before marking it verified."
            )
        if errors:
            raise ValidationError(errors)

    def clean_fields(self, exclude=None):
        """Normalize the professional fields before Django validates them.

        ``full_clean`` runs ``clean_fields`` before ``clean``, so normalizing
        any later would be too late: ``URLField``'s validator would reject a
        perfectly good ``example.com`` before it was ever upgraded to
        ``https://example.com``. A field we could not normalize is excluded
        from the built-in pass so it is reported once, in our wording.
        """
        excluded = set(exclude or ())
        errors = self._normalize_professional_profile()
        errors.update(self._normalize_administration())
        try:
            super().clean_fields(exclude=excluded | set(errors))
        except ValidationError as exc:
            errors.update(exc.error_dict or {})
        reportable = {
            field: error for field, error in errors.items() if field not in excluded
        }
        if reportable:
            raise ValidationError(reportable)

    def _normalize_professional_profile(self) -> dict:
        """Normalize the self-service professional fields in one pass.

        Kept beside the onboarding normalization above so a value written by
        onboarding and the same value written by the profile editor cannot end
        up stored in two different shapes.
        """
        errors: dict = {}
        self.preferred_name = normalize_name(self.preferred_name)
        self.license_number = normalize_license_number(self.license_number)

        if self.license_state and self.license_state not in US_STATE_CODES:
            errors["license_state"] = _("Enter a valid US state code.")

        if self.license_expires_on is not None:
            latest = timezone.localdate().replace(
                year=timezone.localdate().year + MAX_LICENSE_FUTURE_YEARS
            )
            if self.license_expires_on > latest:
                errors["license_expires_on"] = _(
                    "Enter the expiration date printed on your license."
                )

        # A state or an expiry with no number identifies nothing.
        if not self.license_number and (self.license_state or self.license_expires_on):
            errors["license_number"] = _(
                "Add your license number alongside its state or expiration date."
            )

        for field, allowed_hosts, label in (
            ("website_url", (), "website"),
            *(
                (platform.field, platform.hosts, platform.label)
                for platform in SOCIAL_PLATFORMS
            ),
        ):
            try:
                setattr(
                    self,
                    field,
                    normalize_url(
                        getattr(self, field), allowed_hosts=allowed_hosts, label=label
                    ),
                )
            except ValidationError as exc:
                errors[field] = exc

        try:
            self.bio = normalize_bio(self.bio)
        except ValidationError as exc:
            errors["bio"] = exc

        try:
            self.languages = normalize_languages(self.languages)
        except ValidationError as exc:
            errors["languages"] = exc

        try:
            self.preferred_contact_method = normalize_preferred_contact_method(
                self.preferred_contact_method
            )
        except ValidationError as exc:
            errors["preferred_contact_method"] = exc

        return errors

    def _normalize_administration(self) -> dict:
        """Normalize the broker-controlled fields in one pass.

        Beside the self-service normalization above for the same reason: a
        value written by the administration form and the same value written by
        a management command cannot end up stored in two different shapes.
        """
        errors: dict = {}

        try:
            self.agent_status = normalize_agent_status(self.agent_status)
        except ValidationError as exc:
            errors["agent_status"] = exc

        try:
            self.license_verification_state = normalize_license_verification_state(
                self.license_verification_state
            )
        except ValidationError as exc:
            errors["license_verification_state"] = exc

        try:
            self.agent_identifier = normalize_agent_identifier(self.agent_identifier)
        except ValidationError as exc:
            errors["agent_identifier"] = exc

        try:
            self.internal_notes = normalize_internal_notes(self.internal_notes)
        except ValidationError as exc:
            errors["internal_notes"] = exc

        self.license_verification_note = (self.license_verification_note or "").strip()[
            :VERIFICATION_NOTE_MAX_LENGTH
        ]

        return errors

    def preferred_display_name(self) -> str:
        """The name to greet this person by — preferred first, then legal."""
        return (
            self.preferred_name
            or self.first_name
            or self.display_name
            or self.email.split("@")[0]
        )


class UserOfficeMembership(models.Model):
    """Primary/secondary office affiliation with effective-dated history.

    ``User.office`` remains the live primary pointer for hot paths. This table
    is the auditable history and the home for approved secondary affiliations
    that must not change the primary assignment. Hierarchy membership never
    grants permissions by itself — see ``apps.user.services.hierarchy``.
    """

    class Kind(models.TextChoices):
        PRIMARY = "primary", _("Primary")
        SECONDARY = "secondary", _("Secondary")

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        ACTIVE = "active", _("Active")
        ENDED = "ended", _("Ended")
        CANCELLED = "cancelled", _("Cancelled")

    user = models.ForeignKey(
        User,
        verbose_name=_("user"),
        related_name="office_memberships",
        on_delete=models.CASCADE,
    )
    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="memberships",
        on_delete=models.PROTECT,
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    starts_on = models.DateField(_("starts on"))
    ends_on = models.DateField(_("ends on"), null=True, blank=True)
    changed_by = models.ForeignKey(
        User,
        verbose_name=_("changed by"),
        related_name="office_membership_changes",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    business_reason = models.TextField(_("business reason"), blank=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["user_id", "kind", "-starts_on", "-pk"]
        verbose_name = _("user office membership")
        verbose_name_plural = _("user office memberships")
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__isnull=True)
                | Q(ends_on__gte=models.F("starts_on")),
                name="user_office_membership_valid_dates",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(kind="primary", status="active"),
                name="user_office_membership_one_active_primary",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "kind", "status"],
                name="user_office_memb_user_kind",
            ),
            models.Index(
                fields=["office", "status"],
                name="user_office_memb_office_stat",
            ),
            models.Index(
                fields=["starts_on", "ends_on"],
                name="user_office_memb_effective",
            ),
        ]

    def __str__(self):
        return f"{self.user.pk}:{self.kind}:{self.office.pk}:{self.status}"

    def clean(self):
        super().clean()
        errors = {}
        if self.ends_on and self.starts_on and self.ends_on < self.starts_on:
            errors["ends_on"] = _("End date cannot be earlier than the start date.")
        if (
            self.kind == self.Kind.PRIMARY
            and self.office is not None
            and not self.office.is_assignable
            and self.status
            in {
                self.Status.SCHEDULED,
                self.Status.ACTIVE,
            }
        ):
            errors["office"] = _("Primary membership requires an assignable office.")
        if errors:
            raise ValidationError(errors)


class BrokerageRole(models.Model):
    """Persisted mirror of the code-owned brokerage role catalog.

    System roles are seeded from ``apps.user.roles.ROLE_DEFINITIONS``. Rows are
    never hard-deleted while historical assignments reference the code;
    deactivate with ``is_active`` / ``is_assignable`` instead.
    """

    code = models.SlugField(_("code"), max_length=64, unique=True)
    display_name = models.CharField(_("display name"), max_length=128)
    description = models.TextField(_("description"), blank=True)
    group_name = models.CharField(_("django group name"), max_length=150)
    is_active = models.BooleanField(_("active"), default=True)
    is_assignable = models.BooleanField(_("assignable"), default=True)
    is_system = models.BooleanField(_("system managed"), default=True)
    is_protected = models.BooleanField(_("protected"), default=False)
    valid_scope_types = models.JSONField(_("valid scope types"), default=list)
    priority = models.PositiveSmallIntegerField(_("priority"), default=100)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["priority", "code"]
        verbose_name = _("brokerage role")
        verbose_name_plural = _("brokerage roles")
        indexes = [
            models.Index(
                fields=["is_active", "is_assignable"], name="brokerage_role_assign"
            ),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.code})"

    def delete(self, *args, **kwargs):
        from django.apps import apps as django_apps

        Assignment = django_apps.get_model("user", "UserRoleAssignment")
        if Assignment.objects.filter(role=self.code).exists():
            raise ValidationError(
                _(
                    "This role is referenced by historical assignments. "
                    "Deactivate it instead of deleting."
                )
            )
        if self.is_system:
            raise ValidationError(_("System roles cannot be deleted."))
        return super().delete(*args, **kwargs)


class UserRoleAssignment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        ACTIVE = "active", _("Active")
        EXPIRED = "expired", _("Expired")
        REVOKED = "revoked", _("Revoked")

    user = models.ForeignKey(
        "User",
        verbose_name=_("user"),
        related_name="role_assignments",
        on_delete=models.PROTECT,
    )
    role = models.CharField(_("role"), max_length=64, db_index=True)
    scope_type = models.CharField(
        _("scope type"), max_length=32, choices=ScopeType.CHOICES
    )
    scope_office = models.ForeignKey(
        Office,
        verbose_name=_("scope office"),
        related_name="role_assignments",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    starts_at = models.DateTimeField(_("starts at"), null=True, blank=True)
    ends_at = models.DateTimeField(_("ends at"), null=True, blank=True)
    assigned_by = models.ForeignKey(
        "User",
        verbose_name=_("assigned by"),
        related_name="granted_role_assignments",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    revoked_by = models.ForeignKey(
        "User",
        verbose_name=_("revoked by"),
        related_name="revoked_role_assignments",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    revoked_at = models.DateTimeField(_("revoked at"), null=True, blank=True)
    business_reason = models.TextField(_("business reason"), blank=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["user__email", "role", "-created_at"]
        verbose_name = _("user role assignment")
        verbose_name_plural = _("user role assignments")
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True)
                | Q(starts_at__isnull=True)
                | Q(ends_at__gte=models.F("starts_at")),
                name="user_role_assignment_valid_dates",
            ),
            models.CheckConstraint(
                condition=Q(scope_type=ScopeType.COMPANY, scope_office__isnull=True)
                | ~Q(scope_type=ScopeType.COMPANY),
                name="user_role_assignment_company_scope_empty",
            ),
            models.CheckConstraint(
                condition=~Q(scope_type__in=[ScopeType.REGION, ScopeType.OFFICE])
                | Q(scope_office__isnull=False),
                name="user_role_assignment_scoped_office_required",
            ),
            models.UniqueConstraint(
                fields=["user", "role", "scope_type", "scope_office"],
                condition=Q(status__in=["scheduled", "active"]),
                name="user_role_assignment_unique_live_scope",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "status", "starts_at", "ends_at"],
                name="user_role_asgn_user_idx",
            ),
            models.Index(
                fields=["scope_type", "scope_office", "status"],
                name="user_role_asgn_scope_idx",
            ),
        ]

    def __str__(self):
        scope = self.scope_label()
        return f"{self.user} / {self.role} / {scope}"

    def scope_label(self) -> str:
        if self.scope_type == ScopeType.COMPANY:
            return "Company"
        if self.scope_office is None:
            return self.scope_type
        return self.scope_office.path_label()

    def clean(self):
        super().clean()
        errors = {}
        normalized = normalize_role_code(self.role) if self.role else None
        if normalized is None:
            errors["role"] = _("Pick a supported role.")
        else:
            if self.role != normalized:
                self.role = normalized
            if not is_valid_scope_type(self.role, self.scope_type):
                errors["scope_type"] = _(
                    "This role cannot be assigned with that scope."
                )

        if self.scope_type == ScopeType.COMPANY and self.scope_office is not None:
            errors["scope_office"] = _("Company-scoped roles cannot target an office.")
        if (
            self.scope_type in {ScopeType.REGION, ScopeType.OFFICE}
            and self.scope_office is None
        ):
            errors["scope_office"] = _("This scope requires an office target.")
        if (
            self.scope_type == ScopeType.REGION
            and self.scope_office is not None
            and self.scope_office.kind != Office.Kind.REGION
        ):
            errors["scope_office"] = _("Region scope must target a region office.")
        if (
            self.scope_type == ScopeType.OFFICE
            and self.scope_office is not None
            and self.scope_office.kind
            not in {Office.Kind.BRANCH, Office.Kind.REGIONAL_OFFICE}
        ):
            errors["scope_office"] = _("Office scope must target an assignable office.")
        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            errors["ends_at"] = _("End date cannot be earlier than the start date.")
        if self.status == self.Status.REVOKED and self.revoked_at is None:
            errors["revoked_at"] = _(
                "Revoked assignments must record when they were revoked."
            )
        if self.revoked_at and self.status != self.Status.REVOKED:
            errors["status"] = _(
                "Only revoked assignments may store a revocation timestamp."
            )
        if errors:
            raise ValidationError(errors)

    def is_effective(self, at=None) -> bool:
        at = at or timezone.now()
        if self.status != self.Status.ACTIVE:
            return False
        if self.starts_at and self.starts_at > at:
            return False
        if self.ends_at and self.ends_at <= at:
            return False
        return not (self.revoked_at and self.revoked_at <= at)

    def resolve_status(self, at=None) -> str:
        at = at or timezone.now()
        if self.revoked_at and self.revoked_at <= at:
            return self.Status.REVOKED
        if self.ends_at and self.ends_at <= at:
            return self.Status.EXPIRED
        if self.starts_at and self.starts_at > at:
            return self.Status.SCHEDULED
        return self.Status.ACTIVE

    def refresh_status(self, at=None) -> str:
        resolved = self.resolve_status(at=at)
        if self.status != resolved:
            self.status = resolved
        return self.status


class UserRoleAssignmentMigrationConflict(models.Model):
    user = models.ForeignKey(
        "User",
        verbose_name=_("user"),
        related_name="role_assignment_migration_conflicts",
        on_delete=models.CASCADE,
    )
    legacy_role = models.CharField(_("legacy role"), max_length=64)
    detail = models.TextField(_("detail"))
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        ordering = ["user__email", "legacy_role", "created_at"]
        verbose_name = _("user role assignment migration conflict")
        verbose_name_plural = _("user role assignment migration conflicts")

    def __str__(self):
        return f"{self.user} / {self.legacy_role}"


class UserOnboardingCase(models.Model):
    """Operational coordination around source-owned onboarding milestones.

    Profile, SSO, contract, and training completion deliberately do not live on
    this model.  ``services.onboarding_state`` derives those facts from their
    owning domains so an operations user cannot check them off by hand.
    """

    user = models.OneToOneField(
        User,
        verbose_name=_("user"),
        related_name="onboarding_case",
        on_delete=models.PROTECT,
    )
    owner = models.ForeignKey(
        User,
        verbose_name=_("onboarding owner"),
        related_name="owned_onboarding_cases",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        User,
        verbose_name=_("updated by"),
        related_name="updated_onboarding_cases",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__email"]
        verbose_name = _("user onboarding case")
        verbose_name_plural = _("user onboarding cases")

    def __str__(self):
        return f"Onboarding / {self.user}"


class OnboardingTask(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        RESOLVED = "resolved", _("Resolved")

    case = models.ForeignKey(
        UserOnboardingCase,
        verbose_name=_("onboarding case"),
        related_name="tasks",
        on_delete=models.CASCADE,
    )
    title = models.CharField(
        _("task"),
        max_length=200,
        help_text=_("A brief operational instruction; do not include sensitive data."),
    )
    due_on = models.DateField(_("due on"), null=True, blank=True)
    is_blocking = models.BooleanField(_("blocks activation"), default=False)
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_by = models.ForeignKey(
        User,
        verbose_name=_("created by"),
        related_name="created_onboarding_tasks",
        on_delete=models.PROTECT,
    )
    resolved_by = models.ForeignKey(
        User,
        verbose_name=_("resolved by"),
        related_name="resolved_onboarding_tasks",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["status", "due_on", "created_at"]
        verbose_name = _("onboarding task")
        verbose_name_plural = _("onboarding tasks")
        indexes = [
            models.Index(
                fields=["case", "status", "due_on"],
                name="user_onboard_task_state",
            )
        ]

    def __str__(self):
        return f"{self.case.user} / {self.title}"


class OnboardingToolSetup(models.Model):
    class Tool(models.TextChoices):
        LOFTY = "lofty", _("Lofty")
        SKYSLOPE = "skyslope", _("SkySlope")
        MICROSOFT_365 = "microsoft365", _("Microsoft 365")
        DOTLOOP = "dotloop", _("Dotloop")

    class State(models.TextChoices):
        NOT_STARTED = "not_started", _("Not started")
        IN_PROGRESS = "in_progress", _("In progress")
        READY = "ready", _("Ready")
        BLOCKED = "blocked", _("Blocked")
        NOT_REQUIRED = "not_required", _("Not required")

    case = models.ForeignKey(
        UserOnboardingCase,
        verbose_name=_("onboarding case"),
        related_name="tool_setups",
        on_delete=models.CASCADE,
    )
    tool = models.CharField(_("tool"), max_length=32, choices=Tool.choices)
    state = models.CharField(
        _("state"),
        max_length=16,
        choices=State.choices,
        default=State.NOT_STARTED,
    )
    updated_by = models.ForeignKey(
        User,
        verbose_name=_("updated by"),
        related_name="updated_onboarding_tools",
        on_delete=models.PROTECT,
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["tool"]
        verbose_name = _("onboarding tool setup")
        verbose_name_plural = _("onboarding tool setups")
        constraints = [
            models.UniqueConstraint(
                fields=["case", "tool"],
                name="user_onboard_tool_unique",
            )
        ]

    def __str__(self):
        tool_label = dict(self.Tool.choices).get(self.tool, self.tool)
        return f"{self.case.user} / {tool_label} / {self.state}"
