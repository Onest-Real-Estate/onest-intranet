from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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
            models.Index(
                fields=["is_active", "is_assignable"],
                name="user_office_active_assignable",
            ),
            models.Index(
                fields=["region", "is_active"], name="user_office_region_active"
            ),
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
        upload_to="apps.user.headshot.headshot_upload_path",
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

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

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
            errors["office"] = _("Pick an active office from the locations we serve.")
        if errors:
            raise ValidationError(errors)
