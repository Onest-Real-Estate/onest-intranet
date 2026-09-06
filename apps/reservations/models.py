from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.reservations.guards import office_transfer_is_allowed
from apps.reservations.taxonomy import (
    AmenityCategory,
    ExceptionKind,
    ExceptionVisibility,
    RecurrencePolicy,
    SpaceStatus,
    SpaceType,
    Weekday,
)
from apps.reservations.validators import (
    SPACE_PHOTO_EXTENSIONS,
    validate_space_photo,
)
from apps.user.models import Office
from apps.user.storage import private_storage


def space_photo_upload_to(instance: models.Model, filename: str) -> str:
    photo = cast("SpacePhoto", instance)
    suffix = Path(filename).suffix.lower()
    if suffix not in SPACE_PHOTO_EXTENSIONS:
        suffix = ".bin"
    return f"reservations/spaces/{photo.space.public_id}/{photo.public_id}{suffix}"


class SpaceQuerySet(models.QuerySet["Space"]):
    def active_catalog(self) -> SpaceQuerySet:
        return self.filter(status=SpaceStatus.ACTIVE)

    def reservable_catalog(self) -> SpaceQuerySet:
        return self.active_catalog().filter(is_reservable=True)

    def for_agent_office(self, office: Office | None) -> SpaceQuerySet:
        if office is None or not office.is_active or not office.is_assignable:
            return self.none()
        return self.filter(owner_office=office).reservable_catalog()

    def for_manager(self, user, *, access) -> SpaceQuerySet:
        if getattr(user, "is_anonymous", False):
            return self.none()
        if getattr(user, "is_superuser", False) or access.company_wide:
            return self.all()

        reach = Q(pk__in=[])
        if access.office_keys:
            reach |= Q(owner_office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            reach |= Q(owner_office__region__stable_key__in=sorted(access.region_keys))
        return self.filter(reach)

    def delete(self):
        raise ValidationError(_("Spaces must be retired rather than deleted."))


class Amenity(models.Model):
    code = models.SlugField(_("code"), max_length=64, unique=True)
    name = models.CharField(_("name"), max_length=120)
    category = models.CharField(
        _("category"), max_length=32, choices=AmenityCategory.choices
    )
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["display_order", "name", "pk"]
        verbose_name = _("space amenity")
        verbose_name_plural = _("space amenities")
        constraints = [
            models.CheckConstraint(
                condition=~Q(code=""), name="rsv_amenity_requires_code"
            ),
            models.CheckConstraint(
                condition=~Q(name=""), name="rsv_amenity_requires_name"
            ),
        ]
        indexes = [
            models.Index(
                fields=["is_active", "category", "display_order"],
                name="rsv_amenity_catalog_idx",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        self.code = self.code.strip().lower()
        self.name = self.name.strip()
        if self.pk:
            original = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("code", flat=True)
                .first()
            )
            if original is not None and original != self.code:
                raise ValidationError({"code": _("Amenity codes are immutable.")})


class Space(models.Model):
    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    owner_office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="reservable_spaces",
        verbose_name=_("owning office"),
    )
    name = models.CharField(_("name"), max_length=200)
    space_type = models.CharField(
        _("space type"), max_length=32, choices=SpaceType.choices
    )
    capacity = models.PositiveSmallIntegerField(_("capacity"))
    description = models.TextField(_("description"), blank=True)
    location = models.CharField(_("location"), max_length=240, blank=True)
    access_instructions = models.TextField(
        _("internal access instructions"),
        blank=True,
        help_text=_("Sensitive; omit unless the reader has the field permission."),
    )
    amenities = models.ManyToManyField(
        Amenity, through="SpaceAmenity", related_name="spaces", blank=True
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=SpaceStatus.choices,
        default=SpaceStatus.ACTIVE,
    )
    is_reservable = models.BooleanField(_("reservable"), default=True)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=0)

    minimum_duration_minutes = models.PositiveIntegerField(
        _("minimum duration in minutes"), default=30
    )
    maximum_duration_minutes = models.PositiveIntegerField(
        _("maximum duration in minutes"), default=480
    )
    booking_horizon_days = models.PositiveIntegerField(
        _("booking horizon in days"), default=90
    )
    minimum_notice_minutes = models.PositiveIntegerField(
        _("minimum notice in minutes"), default=0
    )
    buffer_before_minutes = models.PositiveIntegerField(
        _("buffer before in minutes"), default=0
    )
    buffer_after_minutes = models.PositiveIntegerField(
        _("cleanup buffer after in minutes"), default=0
    )
    requires_approval = models.BooleanField(_("requires approval"), default=False)
    cancellation_cutoff_minutes = models.PositiveIntegerField(
        _("cancellation cutoff in minutes"), default=0
    )
    recurrence_policy = models.CharField(
        _("recurrence policy"),
        max_length=24,
        choices=RecurrencePolicy.choices,
        default=RecurrencePolicy.NONE,
    )
    maximum_recurrence_occurrences = models.PositiveSmallIntegerField(
        _("maximum recurrence occurrences"), null=True, blank=True
    )

    booking_history_started_at = models.DateTimeField(
        _("booking history started at"),
        null=True,
        blank=True,
        help_text=_(
            "Set by the booking service on the first booking; ordinary office "
            "transfers then fail closed."
        ),
    )
    retired_at = models.DateTimeField(_("retired at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation_spaces_created",
        verbose_name=_("created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation_spaces_updated",
        verbose_name=_("updated by"),
    )

    if TYPE_CHECKING:
        owner_office_id: int
        created_by_id: int | None
        updated_by_id: int | None
        weekly_availability: models.Manager[WeeklyAvailability]
        availability_exceptions: models.Manager[SpaceAvailabilityException]
        photos: models.Manager[SpacePhoto]

    objects = SpaceQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "name", "pk"]
        verbose_name = _("reservable space")
        verbose_name_plural = _("reservable spaces")
        permissions = (
            ("view_spaces", _("Can view scoped office spaces")),
            ("manage_spaces", _("Can manage scoped office spaces")),
            (
                "manage_space_schedules",
                _("Can manage scoped space schedules and exceptions"),
            ),
            (
                "view_space_sensitive",
                _("Can view access instructions and internal exception details"),
            ),
        )
        constraints = [
            models.CheckConstraint(
                condition=~Q(name=""), name="rsv_space_requires_name"
            ),
            models.CheckConstraint(
                condition=Q(capacity__gte=1), name="rsv_space_capacity_positive"
            ),
            models.CheckConstraint(
                condition=Q(minimum_duration_minutes__gte=1),
                name="rsv_space_min_duration_positive",
            ),
            models.CheckConstraint(
                condition=Q(maximum_duration_minutes__gte=1),
                name="rsv_space_max_duration_positive",
            ),
            models.CheckConstraint(
                condition=Q(
                    maximum_duration_minutes__gte=models.F("minimum_duration_minutes")
                ),
                name="rsv_space_duration_order",
            ),
            models.CheckConstraint(
                condition=Q(booking_horizon_days__gte=1),
                name="rsv_space_horizon_positive",
            ),
            models.CheckConstraint(
                condition=Q(minimum_notice_minutes__gte=0),
                name="rsv_space_notice_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(buffer_before_minutes__gte=0),
                name="rsv_space_buffer_before_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(buffer_after_minutes__gte=0),
                name="rsv_space_buffer_after_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(cancellation_cutoff_minutes__gte=0),
                name="rsv_space_cancel_cutoff_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(is_reservable=False) | Q(status=SpaceStatus.ACTIVE),
                name="rsv_space_reservable_when_active",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=SpaceStatus.RETIRED, retired_at__isnull=False)
                    | (~Q(status=SpaceStatus.RETIRED) & Q(retired_at__isnull=True))
                ),
                name="rsv_space_retired_at_matches",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        recurrence_policy=RecurrencePolicy.NONE,
                        maximum_recurrence_occurrences__isnull=True,
                    )
                    | (
                        ~Q(recurrence_policy=RecurrencePolicy.NONE)
                        & Q(maximum_recurrence_occurrences__gte=2)
                    )
                ),
                name="rsv_space_recurrence_consistent",
            ),
        ]
        indexes = [
            models.Index(
                fields=["owner_office", "status", "space_type"],
                name="rsv_space_office_state_type",
            ),
            models.Index(
                fields=["owner_office", "is_reservable", "display_order"],
                name="rsv_space_office_res_order",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_retired(self) -> bool:
        return self.status == SpaceStatus.RETIRED

    def clean(self) -> None:
        super().clean()
        errors: dict[str, object] = {}
        self.name = self.name.strip()
        self.location = self.location.strip()

        if getattr(self, "owner_office_id", None) and (
            not self.owner_office.is_active or not self.owner_office.is_assignable
        ):
            errors["owner_office"] = _(
                "Only active, assignable offices may own reservable spaces."
            )

        if self.maximum_duration_minutes < self.minimum_duration_minutes:
            errors["maximum_duration_minutes"] = _(
                "Maximum duration must be at least the minimum duration."
            )

        if self.recurrence_policy == RecurrencePolicy.NONE:
            if self.maximum_recurrence_occurrences is not None:
                errors["maximum_recurrence_occurrences"] = _(
                    "A recurrence limit requires an enabled recurrence policy."
                )
        elif (
            self.maximum_recurrence_occurrences is None
            or self.maximum_recurrence_occurrences < 2
        ):
            errors["maximum_recurrence_occurrences"] = _(
                "Recurring bookings require a limit of at least two occurrences."
            )

        if self.status == SpaceStatus.RETIRED:
            if self.retired_at is None or self.is_reservable:
                errors["status"] = _(
                    "Retired spaces require a retirement timestamp and cannot "
                    "be reservable."
                )
        elif self.retired_at is not None:
            errors["retired_at"] = _(
                "Only retired spaces may have a retirement timestamp."
            )

        if self.pk:
            original = (
                type(self)
                .objects.filter(pk=self.pk)
                .values("public_id", "owner_office_id", "booking_history_started_at")
                .first()
            )
            if original and original["public_id"] != self.public_id:
                errors["public_id"] = _("Stable identity cannot be changed.")
            if (
                original
                and original["owner_office_id"] != self.owner_office_id
                and original["booking_history_started_at"] is not None
                and not office_transfer_is_allowed()
            ):
                errors["owner_office"] = _(
                    "Spaces with booking history require the explicit migration "
                    "operation."
                )

        if errors:
            raise ValidationError(errors)

    def delete(self, using=None, keep_parents=False):
        raise ValidationError(_("Spaces must be retired rather than deleted."))


class SpaceAmenity(models.Model):
    space = models.ForeignKey(
        Space, on_delete=models.CASCADE, related_name="amenity_assignments"
    )
    amenity = models.ForeignKey(
        Amenity, on_delete=models.PROTECT, related_name="space_assignments"
    )
    notes = models.CharField(_("notes"), max_length=160, blank=True)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        ordering = ["display_order", "amenity__display_order", "amenity__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["space", "amenity"], name="rsv_space_amenity_unique"
            )
        ]
        indexes = [
            models.Index(
                fields=["amenity", "space"], name="rsv_space_amenity_filter_idx"
            )
        ]


class SpacePhoto(models.Model):
    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    space = models.ForeignKey(
        Space, on_delete=models.PROTECT, related_name="photos", verbose_name=_("space")
    )
    file = models.ImageField(
        _("photo"),
        upload_to=space_photo_upload_to,
        storage=private_storage,
        max_length=255,
        validators=[validate_space_photo],
    )
    alt_text = models.CharField(_("alternative text"), max_length=240)
    is_public = models.BooleanField(
        _("visible to agents"),
        default=True,
        help_text=_("The object remains in protected storage in every state."),
    )
    display_order = models.PositiveSmallIntegerField(_("display order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation_space_photos_created",
    )

    class Meta:
        ordering = ["display_order", "created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(alt_text=""), name="rsv_space_photo_requires_alt"
            )
        ]
        indexes = [
            models.Index(
                fields=["space", "is_public", "display_order"],
                name="rsv_space_photo_listing_idx",
            )
        ]

    def clean(self) -> None:
        super().clean()
        self.alt_text = self.alt_text.strip()
        if not self.alt_text:
            raise ValidationError({"alt_text": _("Alternative text is required.")})


class WeeklyAvailability(models.Model):
    space = models.ForeignKey(
        Space,
        on_delete=models.CASCADE,
        related_name="weekly_availability",
        verbose_name=_("space"),
    )
    weekday = models.PositiveSmallIntegerField(_("weekday"), choices=Weekday.choices)
    starts_at = models.TimeField(_("starts at"))
    ends_at = models.TimeField(_("ends at"))
    display_order = models.PositiveSmallIntegerField(_("display order"), default=0)

    if TYPE_CHECKING:
        space_id: int

    class Meta:
        ordering = ["weekday", "starts_at", "display_order", "pk"]
        verbose_name = _("weekly space availability")
        verbose_name_plural = _("weekly space availability")
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="rsv_weekly_ends_after_start",
            ),
            models.UniqueConstraint(
                fields=["space", "weekday", "starts_at", "ends_at"],
                name="rsv_weekly_interval_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["space", "weekday", "starts_at", "ends_at"],
                name="rsv_weekly_space_day_time",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.starts_at.tzinfo is not None or self.ends_at.tzinfo is not None:
            raise ValidationError(
                {
                    "starts_at": _(
                        "Weekly times are office-local wall times without an offset."
                    )
                }
            )
        if self.starts_at >= self.ends_at:
            raise ValidationError({"ends_at": _("End time must be after start time.")})
        if not self.space_id:
            return
        overlaps = type(self).objects.filter(
            space_id=self.space_id,
            weekday=self.weekday,
            starts_at__lt=self.ends_at,
            ends_at__gt=self.starts_at,
        )
        if self.pk:
            overlaps = overlaps.exclude(pk=self.pk)
        if overlaps.exists():
            raise ValidationError(
                {"starts_at": _("Weekly availability intervals cannot overlap.")}
            )


class SpaceAvailabilityException(models.Model):
    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    space = models.ForeignKey(
        Space,
        on_delete=models.PROTECT,
        related_name="availability_exceptions",
        verbose_name=_("space"),
    )
    kind = models.CharField(_("kind"), max_length=20, choices=ExceptionKind.choices)
    starts_at = models.DateTimeField(_("starts at"))
    ends_at = models.DateTimeField(_("ends at"))
    reason = models.CharField(_("reason"), max_length=500)
    visibility = models.CharField(
        _("visibility"),
        max_length=16,
        choices=ExceptionVisibility.choices,
        default=ExceptionVisibility.INTERNAL,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation_space_exceptions_created",
        verbose_name=_("created by"),
    )

    class Meta:
        ordering = ["starts_at", "ends_at", "pk"]
        verbose_name = _("space availability exception")
        verbose_name_plural = _("space availability exceptions")
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="rsv_exception_ends_after_start",
            ),
            models.CheckConstraint(
                condition=~Q(reason=""), name="rsv_exception_requires_reason"
            ),
        ]
        indexes = [
            models.Index(
                fields=["space", "starts_at", "ends_at"],
                name="rsv_exception_space_time",
            ),
            models.Index(
                fields=["space", "kind", "starts_at"],
                name="rsv_exception_kind_time",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.reason = self.reason.strip()
        errors: dict[str, object] = {}
        if not timezone.is_aware(self.starts_at):
            errors["starts_at"] = _("Start time must include a timezone.")
        if not timezone.is_aware(self.ends_at):
            errors["ends_at"] = _("End time must include a timezone.")
        if not errors and self.ends_at <= self.starts_at:
            errors["ends_at"] = _("End time must be after start time.")
        if not self.reason:
            errors["reason"] = _("A reason is required.")
        if errors:
            raise ValidationError(errors)


class SpaceOfficeTransfer(models.Model):
    space = models.ForeignKey(
        Space,
        on_delete=models.PROTECT,
        related_name="office_transfers",
        verbose_name=_("space"),
    )
    from_office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="reservation_space_transfers_from",
    )
    to_office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="reservation_space_transfers_to",
    )
    preserves_booking_history = models.BooleanField(default=False)
    reason = models.CharField(_("reason"), max_length=500)
    performed_at = models.DateTimeField(_("performed at"), default=timezone.now)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reservation_space_transfers_performed",
    )

    if TYPE_CHECKING:
        space_id: int
        from_office_id: int
        to_office_id: int
        performed_by_id: int | None

    class Meta:
        ordering = ["-performed_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(from_office=models.F("to_office")),
                name="rsv_space_transfer_changes_office",
            ),
            models.CheckConstraint(
                condition=~Q(reason=""), name="rsv_space_transfer_reason"
            ),
        ]
        indexes = [
            models.Index(
                fields=["space", "-performed_at"], name="rsv_space_transfer_history"
            )
        ]

    def clean(self) -> None:
        super().clean()
        self.reason = self.reason.strip()
        errors: dict[str, object] = {}
        if self.from_office_id == self.to_office_id:
            errors["to_office"] = _("Destination must differ from the origin.")
        if self.to_office_id and (
            not self.to_office.is_active or not self.to_office.is_assignable
        ):
            errors["to_office"] = _("Destination must be an active, assignable office.")
        if not self.reason:
            errors["reason"] = _("A transfer reason is required.")
        if errors:
            raise ValidationError(errors)
