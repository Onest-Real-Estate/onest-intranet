"""Marketing asset records, audience selectors, and protected files."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.marketing.taxonomy import (
    ASSET_TYPE_CHOICES,
    SYSTEM_CATEGORY_CODES,
    normalize_brand_codes,
    normalize_jurisdiction_codes,
)
from apps.user.models import Office
from apps.user.storage import private_storage


class ProtectedCategoryError(Exception):
    """A category that governance does not allow to be destroyed."""


class MarketingCategoryQuerySet(models.QuerySet["MarketingCategory"]):
    def active(self) -> MarketingCategoryQuerySet:
        return self.filter(is_active=True)

    def delete(self):
        blocked = sorted(self.filter(is_system=True).values_list("code", flat=True))
        if blocked:
            raise ProtectedCategoryError(
                f"System categories cannot be deleted: {', '.join(blocked)}."
            )
        return super().delete()


class MarketingCategory(models.Model):
    code = models.SlugField(_("code"), max_length=40, unique=True)
    label = models.CharField(_("label"), max_length=80)
    description = models.CharField(_("description"), max_length=200, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    is_system = models.BooleanField(_("system category"), default=False, editable=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = MarketingCategoryQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "label"]
        verbose_name = _("marketing category")
        verbose_name_plural = _("marketing categories")

    def __str__(self):
        return self.label

    def delete(self, *args, **kwargs):
        if self.is_system or self.code in SYSTEM_CATEGORY_CODES:
            raise ProtectedCategoryError(
                f"System category {self.code!r} cannot be deleted. "
                "Deactivate it instead."
            )
        return super().delete(*args, **kwargs)


class MarketingAssetQuerySet(models.QuerySet["MarketingAsset"]):
    def published(self) -> MarketingAssetQuerySet:
        return self.filter(status=MarketingAsset.Status.PUBLISHED)

    def within_window(self, *, now=None) -> MarketingAssetQuerySet:
        moment = now or timezone.now()
        return self.filter(
            Q(publish_at__isnull=True) | Q(publish_at__lte=moment),
            Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
        )


class MarketingAsset(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    owner_office = models.ForeignKey(
        Office,
        verbose_name=_("owning office"),
        related_name="marketing_assets",
        on_delete=models.PROTECT,
    )
    slug = models.SlugField(_("slug"), max_length=80)
    title = models.CharField(_("title"), max_length=180)
    description = models.TextField(_("description"), blank=True)
    usage_instructions = models.TextField(_("usage instructions"), blank=True)
    asset_type = models.CharField(
        _("asset type"),
        max_length=32,
        choices=ASSET_TYPE_CHOICES,
    )
    category = models.ForeignKey(
        MarketingCategory,
        verbose_name=_("category"),
        related_name="assets",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    jurisdiction_state_codes = models.JSONField(
        _("jurisdiction state codes"),
        default=list,
        blank=True,
        help_text=_("Empty means all jurisdictions."),
    )
    brand_codes = models.JSONField(
        _("brand codes"),
        default=list,
        blank=True,
        help_text=_("Empty means all brands."),
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    publish_at = models.DateTimeField(_("publishes at"), null=True, blank=True)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    published_at = models.DateTimeField(
        _("published at"), null=True, blank=True, editable=False
    )
    archived_at = models.DateTimeField(
        _("archived at"), null=True, blank=True, editable=False
    )
    version_family = models.UUIDField(
        _("version family"),
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text=_("Shared across successive versions of the same asset."),
    )
    version_number = models.PositiveIntegerField(_("version number"), default=1)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    created_by = models.ForeignKey(
        "user.User",
        verbose_name=_("created by"),
        related_name="marketing_assets_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    updated_by = models.ForeignKey(
        "user.User",
        verbose_name=_("last edited by"),
        related_name="marketing_assets_edited",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = MarketingAssetQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "title"]
        verbose_name = _("marketing asset")
        verbose_name_plural = _("marketing assets")
        constraints = [
            models.UniqueConstraint(
                fields=["owner_office", "slug"],
                name="marketing_asset_unique_slug_per_office",
            ),
            models.CheckConstraint(
                condition=~Q(status="published") | Q(category__isnull=False),
                name="marketing_published_requires_category",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(publish_at__isnull=True)
                | Q(expires_at__gt=F("publish_at")),
                name="marketing_window_ordered",
            ),
            models.UniqueConstraint(
                fields=["version_family", "version_number"],
                name="marketing_asset_unique_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "display_order"],
                name="marketing_library_order",
            ),
            models.Index(
                fields=["status", "asset_type"],
                name="marketing_status_type",
            ),
            models.Index(
                fields=["version_family", "version_number"],
                name="marketing_version_family",
            ),
        ]

    def __str__(self):
        return f"{self.owner_office} / {self.slug}"

    @property
    def scope_level(self) -> str:
        if self.owner_office.kind == Office.Kind.HEAD_OFFICE:
            return "company"
        if self.owner_office.kind == Office.Kind.REGION:
            return "region"
        return "office"

    def is_visible_at(self, moment) -> bool:
        if self.status != self.Status.PUBLISHED:
            return False
        if self.publish_at is not None and self.publish_at > moment:
            return False
        return self.expires_at is None or self.expires_at > moment

    def clean(self):
        super().clean()
        errors: dict[str, object] = {}
        if self.expires_at and self.publish_at and self.expires_at <= self.publish_at:
            errors["expires_at"] = _("Expiry must be after the publish time.")
        try:
            self.jurisdiction_state_codes = normalize_jurisdiction_codes(
                self.jurisdiction_state_codes
            )
        except ValidationError as exc:
            errors["jurisdiction_state_codes"] = exc.messages
        try:
            self.brand_codes = normalize_brand_codes(self.brand_codes)
        except ValidationError as exc:
            errors["brand_codes"] = exc.messages
        if (
            self.category is not None
            and not self.category.is_active
            and self._category_changed()
        ):
            errors["category"] = _("That category is retired. Choose an active one.")
        if self.status == self.Status.PUBLISHED:
            from apps.marketing.services import validation_debt

            for field, message in validation_debt(self):
                errors.setdefault(field, message)
        if errors:
            raise ValidationError(errors)

    def _category_changed(self) -> bool:
        if not self.pk:
            return True
        previous = (
            type(self)
            .objects.filter(pk=self.pk)
            .values_list("category__code", flat=True)
            .first()
        )
        return previous != (self.category.code if self.category else None)


class MarketingAudience(models.Model):
    class Kind(models.TextChoices):
        COMPANY = "company", _("Everyone at the brokerage")
        ROLE = "role", _("Everyone holding a role")
        REGION = "region", _("A region and the offices under it")
        OFFICE = "office", _("One office only")
        USER = "user", _("One named person")

    asset = models.ForeignKey(
        MarketingAsset,
        verbose_name=_("asset"),
        related_name="audiences",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    role = models.CharField(_("role code"), max_length=64, blank=True)
    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="marketing_audiences",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        "user.User",
        verbose_name=_("person"),
        related_name="marketing_audiences",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("marketing audience")
        verbose_name_plural = _("marketing audiences")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(kind="company", role="", office__isnull=True, user__isnull=True)
                    | (
                        Q(kind="role", office__isnull=True, user__isnull=True)
                        & ~Q(role="")
                    )
                    | Q(
                        kind__in=["region", "office"],
                        role="",
                        office__isnull=False,
                        user__isnull=True,
                    )
                    | Q(kind="user", role="", office__isnull=True, user__isnull=False)
                ),
                name="marketing_audience_one_target_per_kind",
            ),
            models.UniqueConstraint(
                fields=["asset"],
                condition=Q(kind="company"),
                name="marketing_audience_one_company_row",
            ),
            models.UniqueConstraint(
                fields=["asset", "role"],
                condition=Q(kind="role"),
                name="marketing_audience_unique_role",
            ),
            models.UniqueConstraint(
                fields=["asset", "kind", "office"],
                condition=Q(office__isnull=False),
                name="marketing_audience_unique_office",
            ),
            models.UniqueConstraint(
                fields=["asset", "user"],
                condition=Q(kind="user"),
                name="marketing_audience_unique_user",
            ),
        ]
        indexes = [
            models.Index(fields=["kind", "office"], name="marketing_aud_office"),
            models.Index(fields=["kind", "role"], name="marketing_aud_role"),
            models.Index(fields=["kind", "user"], name="marketing_aud_user"),
        ]


def _file_upload_to(instance, filename):
    from apps.marketing.media import storage_key

    return storage_key(filename)


class MarketingFileQuerySet(models.QuerySet["MarketingFile"]):
    def readable(self) -> MarketingFileQuerySet:
        return self.filter(
            is_active=True,
            processing_state=MarketingFile.ProcessingState.READY,
        )


class MarketingFile(models.Model):
    class Role(models.TextChoices):
        EXPORT = "export", _("Approved export")
        SOURCE = "source", _("Editable source")
        PREVIEW = "preview", _("Generated preview")

    class ProcessingState(models.TextChoices):
        PENDING = "pending", _("Processing")
        READY = "ready", _("Ready")
        QUARANTINED = "quarantined", _("Quarantined")
        FAILED = "failed", _("Processing failed")

    asset = models.ForeignKey(
        MarketingAsset,
        verbose_name=_("asset"),
        related_name="files",
        on_delete=models.CASCADE,
    )
    role = models.CharField(_("role"), max_length=16, choices=Role.choices)
    display_name = models.CharField(_("display name"), max_length=180)
    file = models.FileField(
        _("file"),
        max_length=255,
        storage=private_storage,
        upload_to=_file_upload_to,
    )
    media_type = models.CharField(_("media type"), max_length=120)
    byte_size = models.PositiveBigIntegerField(_("size in bytes"))
    checksum = models.CharField(_("checksum"), max_length=64)
    processing_state = models.CharField(
        _("processing state"),
        max_length=16,
        choices=ProcessingState.choices,
        default=ProcessingState.PENDING,
    )
    processing_note = models.CharField(_("processing note"), max_length=255, blank=True)
    variants = models.JSONField(_("variants"), default=dict, blank=True)
    width = models.PositiveIntegerField(_("width"), null=True, blank=True)
    height = models.PositiveIntegerField(_("height"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    uploaded_by = models.ForeignKey(
        "user.User",
        verbose_name=_("uploaded by"),
        related_name="marketing_files_uploaded",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = MarketingFileQuerySet.as_manager()

    class Meta:
        ordering = ["role", "sort_order", "pk"]
        verbose_name = _("marketing file")
        verbose_name_plural = _("marketing files")
        constraints = [
            models.CheckConstraint(
                condition=Q(byte_size__gt=0), name="marketing_file_has_bytes"
            ),
        ]
        indexes = [
            models.Index(
                fields=["asset", "role", "is_active"],
                name="marketing_file_role",
            ),
        ]

    @property
    def is_image(self) -> bool:
        return self.media_type.startswith("image/")

    @property
    def is_readable(self) -> bool:
        return (
            self.is_active
            and self.processing_state == self.ProcessingState.READY
            and bool(self.file)
        )
