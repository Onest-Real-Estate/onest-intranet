from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .us import US_STATE_CHOICES, normalize_nrds, normalize_us_phone, normalize_us_zip


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
    # Regions group offices but are not themselves a place someone "works at".
    is_assignable = models.BooleanField(
        _("assignable"),
        default=True,
        help_text=_("Whether a user can pick this office as their work location."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("office")
        verbose_name_plural = _("offices")

    def __str__(self):
        return self.path_label()

    def clean(self):
        super().clean()
        if self.kind == self.Kind.HEAD_OFFICE:
            if self.parent:
                raise ValidationError(
                    {"parent": _("The head office cannot have a parent.")}
                )
            return
        expected = self._PARENT_KIND.get(self.kind)
        if not self.parent:
            raise ValidationError(
                {"parent": _("This office must sit under a parent in the org tree.")}
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
        node: Office | None = self
        seen: set[int] = set()
        while node is not None and id(node) not in seen:
            seen.add(id(node))
            if node.kind == self.Kind.REGION:
                return node.name
            if node.kind == self.Kind.HEAD_OFFICE:
                return node.name
            node = node.parent
        return self.name

    @classmethod
    def assignable_queryset(cls):
        return (
            cls.objects.filter(is_assignable=True, is_active=True)
            .select_related("parent", "parent__parent", "parent__parent__parent")
            .order_by("sort_order", "name")
        )

    @classmethod
    def grouped_choices(cls) -> list[dict]:
        """Offices grouped by region, for a ``<select>`` with optgroups."""
        groups: dict[str, list[dict]] = {}
        order: list[str] = []
        for office in cls.assignable_queryset():
            group = office.region_name()
            if group not in groups:
                groups[group] = []
                order.append(group)
            groups[group].append({"id": office.pk, "name": office.name})
        return [{"label": label, "offices": groups[label]} for label in order]


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
