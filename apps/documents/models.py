"""Document families, versions, audience selectors, and protected files."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.documents.taxonomy import SYSTEM_CATEGORY_CODES, normalize_jurisdiction_codes
from apps.user.models import Office
from apps.user.storage import private_storage


class ProtectedCategoryError(Exception):
    """A category that governance does not allow to be destroyed."""


class DocumentCategoryQuerySet(models.QuerySet["DocumentCategory"]):
    def active(self) -> DocumentCategoryQuerySet:
        return self.filter(is_active=True)

    def delete(self):
        blocked = sorted(self.filter(is_system=True).values_list("code", flat=True))
        if blocked:
            raise ProtectedCategoryError(
                f"System categories cannot be deleted: {', '.join(blocked)}."
            )
        return super().delete()


class DocumentCategory(models.Model):
    code = models.SlugField(_("code"), max_length=40, unique=True)
    label = models.CharField(_("label"), max_length=80)
    description = models.CharField(_("description"), max_length=200, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    is_system = models.BooleanField(_("system category"), default=False, editable=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = DocumentCategoryQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "label"]
        verbose_name = _("document category")
        verbose_name_plural = _("document categories")

    def __str__(self):
        return self.label

    def delete(self, *args, **kwargs):
        if self.is_system or self.code in SYSTEM_CATEGORY_CODES:
            raise ProtectedCategoryError(
                f"System category {self.code!r} cannot be deleted. "
                "Deactivate it instead."
            )
        return super().delete(*args, **kwargs)


class DocumentFamily(models.Model):
    key = models.SlugField(
        _("key"),
        max_length=80,
        unique=True,
        help_text=_("Stable identity across successive versions."),
    )
    owner_office = models.ForeignKey(
        Office,
        verbose_name=_("owning office"),
        related_name="document_families",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name = _("document family")
        verbose_name_plural = _("document families")

    def __str__(self):
        return self.key

    @property
    def scope_level(self) -> str:
        if self.owner_office.kind == Office.Kind.HEAD_OFFICE:
            return "company"
        if self.owner_office.kind == Office.Kind.REGION:
            return "region"
        return "office"


class DocumentVersionQuerySet(models.QuerySet["DocumentVersion"]):
    def published(self) -> DocumentVersionQuerySet:
        return self.filter(status=DocumentVersion.Status.PUBLISHED)

    def within_window(self, *, now=None) -> DocumentVersionQuerySet:
        moment = now or timezone.now()
        return self.filter(
            Q(effective_at__isnull=True) | Q(effective_at__lte=moment),
            Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
        )


class DocumentVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        SUPERSEDED = "superseded", _("Superseded")
        RETIRED = "retired", _("Retired")

    IMMUTABLE_STATUSES = frozenset(
        {Status.PUBLISHED, Status.SUPERSEDED, Status.RETIRED}
    )

    family = models.ForeignKey(
        DocumentFamily,
        verbose_name=_("family"),
        related_name="versions",
        on_delete=models.PROTECT,
    )
    name = models.CharField(_("name"), max_length=180)
    description = models.TextField(_("description"), blank=True)
    category = models.ForeignKey(
        DocumentCategory,
        verbose_name=_("category"),
        related_name="versions",
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
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    effective_at = models.DateTimeField(_("effective at"), null=True, blank=True)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    version_number = models.PositiveIntegerField(_("version number"), default=1)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    owner_user = models.ForeignKey(
        "user.User",
        verbose_name=_("document owner"),
        related_name="owned_document_versions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    published_at = models.DateTimeField(
        _("published at"), null=True, blank=True, editable=False
    )
    published_by = models.ForeignKey(
        "user.User",
        verbose_name=_("published by"),
        related_name="document_versions_published",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        "user.User",
        verbose_name=_("created by"),
        related_name="document_versions_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    updated_by = models.ForeignKey(
        "user.User",
        verbose_name=_("last edited by"),
        related_name="document_versions_edited",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = DocumentVersionQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = _("document version")
        verbose_name_plural = _("document versions")
        constraints = [
            models.UniqueConstraint(
                fields=["family", "version_number"],
                name="documents_unique_family_version",
            ),
            models.CheckConstraint(
                condition=~Q(status="published") | Q(category__isnull=False),
                name="documents_published_requires_category",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(effective_at__isnull=True)
                | Q(expires_at__gt=F("effective_at")),
                name="documents_window_ordered",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "display_order"],
                name="documents_library_order",
            ),
            models.Index(
                fields=["family", "version_number"],
                name="documents_family_version",
            ),
        ]

    def __str__(self):
        return f"{self.name} (v{self.version_number})"

    @property
    def owner_office(self) -> Office:
        return self.family.owner_office

    @property
    def scope_level(self) -> str:
        return self.family.scope_level

    @property
    def is_immutable(self) -> bool:
        return self.status in self.IMMUTABLE_STATUSES

    def is_visible_at(self, moment) -> bool:
        if self.status != self.Status.PUBLISHED:
            return False
        if self.effective_at is not None and self.effective_at > moment:
            return False
        return self.expires_at is None or self.expires_at > moment

    def clean(self):
        super().clean()
        errors: dict[str, object] = {}
        if (
            self.expires_at
            and self.effective_at
            and self.expires_at <= self.effective_at
        ):
            errors["expires_at"] = _("Expiry must be after the effective time.")
        try:
            self.jurisdiction_state_codes = normalize_jurisdiction_codes(
                self.jurisdiction_state_codes
            )
        except ValidationError as exc:
            errors["jurisdiction_state_codes"] = exc.messages
        if (
            self.category is not None
            and not self.category.is_active
            and self._category_changed()
        ):
            errors["category"] = _("That category is retired. Choose an active one.")
        if self.status == self.Status.PUBLISHED:
            from apps.documents.services import validation_debt

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


class DocumentAudience(models.Model):
    class Kind(models.TextChoices):
        COMPANY = "company", _("Everyone at the brokerage")
        ROLE = "role", _("Everyone holding a role")
        REGION = "region", _("A region and the offices under it")
        OFFICE = "office", _("One office only")
        USER = "user", _("One named person")

    document_version = models.ForeignKey(
        DocumentVersion,
        verbose_name=_("document version"),
        related_name="audiences",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    role = models.CharField(_("role code"), max_length=64, blank=True)
    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="document_audiences",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        "user.User",
        verbose_name=_("person"),
        related_name="document_audiences",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("document audience")
        verbose_name_plural = _("document audiences")
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
                name="documents_audience_one_target",
            ),
            models.UniqueConstraint(
                fields=["document_version"],
                condition=Q(kind="company"),
                name="documents_audience_one_company",
            ),
            models.UniqueConstraint(
                fields=["document_version", "role"],
                condition=Q(kind="role"),
                name="documents_audience_unique_role",
            ),
            models.UniqueConstraint(
                fields=["document_version", "kind", "office"],
                condition=Q(office__isnull=False),
                name="documents_audience_unique_office",
            ),
            models.UniqueConstraint(
                fields=["document_version", "user"],
                condition=Q(kind="user"),
                name="documents_audience_unique_user",
            ),
        ]
        indexes = [
            models.Index(fields=["kind", "office"], name="documents_aud_office"),
            models.Index(fields=["kind", "role"], name="documents_aud_role"),
            models.Index(fields=["kind", "user"], name="documents_aud_user"),
        ]


def _file_upload_to(instance, filename):
    from apps.documents.media import storage_key

    return storage_key(filename)


class DocumentFileQuerySet(models.QuerySet["DocumentFile"]):
    def readable(self) -> DocumentFileQuerySet:
        return self.filter(
            is_active=True,
            processing_state=DocumentFile.ProcessingState.READY,
        )


class DocumentFile(models.Model):
    class ProcessingState(models.TextChoices):
        PENDING = "pending", _("Processing")
        READY = "ready", _("Ready")
        QUARANTINED = "quarantined", _("Quarantined")
        FAILED = "failed", _("Processing failed")

    document_version = models.ForeignKey(
        DocumentVersion,
        verbose_name=_("document version"),
        related_name="files",
        on_delete=models.CASCADE,
    )
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
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    uploaded_by = models.ForeignKey(
        "user.User",
        verbose_name=_("uploaded by"),
        related_name="document_files_uploaded",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = DocumentFileQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = _("document file")
        verbose_name_plural = _("document files")
        constraints = [
            models.CheckConstraint(
                condition=Q(byte_size__gt=0), name="documents_file_has_bytes"
            ),
        ]
        indexes = [
            models.Index(
                fields=["document_version", "is_active"],
                name="documents_file_active",
            ),
        ]

    @property
    def is_readable(self) -> bool:
        return (
            self.is_active
            and self.processing_state == self.ProcessingState.READY
            and bool(self.file)
        )
