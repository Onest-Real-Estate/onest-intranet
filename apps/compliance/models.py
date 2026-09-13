"""Policy records, audience selectors, protected files, and acknowledgements."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.announcements.richtext import unsafe_links
from apps.compliance.taxonomy import SYSTEM_CATEGORY_CODES, normalize_jurisdiction_codes
from apps.user.models import Office
from apps.user.storage import private_storage


class ProtectedCategoryError(Exception):
    """A category that governance does not allow to be destroyed."""


class PolicyCategoryQuerySet(models.QuerySet["PolicyCategory"]):
    def active(self) -> PolicyCategoryQuerySet:
        return self.filter(is_active=True)

    def delete(self):
        blocked = sorted(self.filter(is_system=True).values_list("code", flat=True))
        if blocked:
            raise ProtectedCategoryError(
                f"System categories cannot be deleted: {', '.join(blocked)}."
            )
        return super().delete()


class PolicyCategory(models.Model):
    code = models.SlugField(_("code"), max_length=40, unique=True)
    label = models.CharField(_("label"), max_length=80)
    description = models.CharField(_("description"), max_length=200, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    is_system = models.BooleanField(_("system category"), default=False, editable=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = PolicyCategoryQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "label"]
        verbose_name = _("policy category")
        verbose_name_plural = _("policy categories")

    def __str__(self):
        return self.label

    def delete(self, *args, **kwargs):
        if self.is_system or self.code in SYSTEM_CATEGORY_CODES:
            raise ProtectedCategoryError(
                f"System category {self.code!r} cannot be deleted. "
                "Deactivate it instead."
            )
        return super().delete(*args, **kwargs)


class PolicyVersionQuerySet(models.QuerySet["PolicyVersion"]):
    def published(self) -> PolicyVersionQuerySet:
        return self.filter(status=PolicyVersion.Status.PUBLISHED)

    def within_window(self, *, now=None) -> PolicyVersionQuerySet:
        moment = now or timezone.now()
        return self.filter(
            Q(effective_at__isnull=True) | Q(effective_at__lte=moment),
            Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
        )


class PolicyVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        IN_REVIEW = "in_review", _("In review")
        APPROVED = "approved", _("Approved")
        PUBLISHED = "published", _("Published")
        SUPERSEDED = "superseded", _("Superseded")
        RETIRED = "retired", _("Retired")

    IMMUTABLE_STATUSES = frozenset(
        {Status.PUBLISHED, Status.SUPERSEDED, Status.RETIRED}
    )

    owner_office = models.ForeignKey(
        Office,
        verbose_name=_("owning office"),
        related_name="policy_versions",
        on_delete=models.PROTECT,
    )
    owner_user = models.ForeignKey(
        "user.User",
        verbose_name=_("policy owner"),
        related_name="owned_policy_versions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    title = models.CharField(_("title"), max_length=180)
    summary = models.CharField(_("summary"), max_length=280, blank=True)
    body = models.TextField(_("body"), blank=True)
    category = models.ForeignKey(
        PolicyCategory,
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
    content_checksum = models.CharField(
        _("content checksum"),
        max_length=64,
        blank=True,
        help_text=_("Sealed on publish over body and ready document files."),
    )
    is_mandatory = models.BooleanField(
        _("mandatory acknowledgement"),
        default=False,
        help_text=_("Audience must acknowledge this published version."),
    )
    reacknowledge_on_supersede = models.BooleanField(
        _("require re-acknowledgement on supersede"),
        default=True,
        help_text=_(
            "When a newer family sibling is published, create a fresh "
            "acknowledgement requirement."
        ),
    )
    acknowledgement_disclosure = models.TextField(
        _("acknowledgement disclosure"),
        blank=True,
        help_text=_("Text the reader must confirm when acknowledging."),
    )
    disclosure_version = models.PositiveIntegerField(
        _("disclosure version"),
        default=1,
        help_text=_("Bumped when acknowledgement disclosure text changes."),
    )
    version_family = models.UUIDField(
        _("version family"),
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text=_("Shared across successive versions of the same policy."),
    )
    version_number = models.PositiveIntegerField(_("version number"), default=1)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    published_at = models.DateTimeField(
        _("published at"), null=True, blank=True, editable=False
    )
    published_by = models.ForeignKey(
        "user.User",
        verbose_name=_("published by"),
        related_name="policy_versions_published",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        "user.User",
        verbose_name=_("created by"),
        related_name="policy_versions_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    updated_by = models.ForeignKey(
        "user.User",
        verbose_name=_("last edited by"),
        related_name="policy_versions_edited",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = PolicyVersionQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "title"]
        verbose_name = _("policy version")
        verbose_name_plural = _("policy versions")
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="published") | Q(category__isnull=False),
                name="compliance_published_requires_category",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(effective_at__isnull=True)
                | Q(expires_at__gt=F("effective_at")),
                name="compliance_window_ordered",
            ),
            models.UniqueConstraint(
                fields=["version_family", "version_number"],
                name="compliance_policy_unique_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "display_order"],
                name="compliance_library_order",
            ),
            models.Index(
                fields=["status", "is_mandatory"],
                name="compliance_status_mandatory",
            ),
            models.Index(
                fields=["version_family", "version_number"],
                name="compliance_version_family",
            ),
        ]

    def __str__(self):
        return f"{self.title} (v{self.version_number})"

    @property
    def scope_level(self) -> str:
        if self.owner_office.kind == Office.Kind.HEAD_OFFICE:
            return "company"
        if self.owner_office.kind == Office.Kind.REGION:
            return "region"
        return "office"

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
        refused = unsafe_links(self.body)
        if refused:
            errors["body"] = _("Body contains disallowed links: %(links)s.") % {
                "links": ", ".join(refused[:5])
            }
        if (
            self.category is not None
            and not self.category.is_active
            and self._category_changed()
        ):
            errors["category"] = _("That category is retired. Choose an active one.")
        if self.status == self.Status.PUBLISHED and self.category is None:
            errors["category"] = _("A published policy needs a category.")
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


class PolicyAudience(models.Model):
    class Kind(models.TextChoices):
        COMPANY = "company", _("Everyone at the brokerage")
        ROLE = "role", _("Everyone holding a role")
        REGION = "region", _("A region and the offices under it")
        OFFICE = "office", _("One office only")
        USER = "user", _("One named person")

    policy_version = models.ForeignKey(
        PolicyVersion,
        verbose_name=_("policy version"),
        related_name="audiences",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    role = models.CharField(_("role code"), max_length=64, blank=True)
    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="policy_audiences",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        "user.User",
        verbose_name=_("person"),
        related_name="policy_audiences",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("policy audience")
        verbose_name_plural = _("policy audiences")
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
                name="compliance_audience_one_target_per_kind",
            ),
            models.UniqueConstraint(
                fields=["policy_version"],
                condition=Q(kind="company"),
                name="compliance_audience_one_company_row",
            ),
            models.UniqueConstraint(
                fields=["policy_version", "role"],
                condition=Q(kind="role"),
                name="compliance_audience_unique_role",
            ),
            models.UniqueConstraint(
                fields=["policy_version", "kind", "office"],
                condition=Q(office__isnull=False),
                name="compliance_audience_unique_office",
            ),
            models.UniqueConstraint(
                fields=["policy_version", "user"],
                condition=Q(kind="user"),
                name="compliance_audience_unique_user",
            ),
        ]
        indexes = [
            models.Index(fields=["kind", "office"], name="compliance_aud_office"),
            models.Index(fields=["kind", "role"], name="compliance_aud_role"),
            models.Index(fields=["kind", "user"], name="compliance_aud_user"),
        ]


def _file_upload_to(instance, filename):
    from apps.compliance.media import storage_key

    return storage_key(filename)


class PolicyFileQuerySet(models.QuerySet["PolicyFile"]):
    def readable(self) -> PolicyFileQuerySet:
        return self.filter(
            is_active=True,
            processing_state=PolicyFile.ProcessingState.READY,
        )


class PolicyFile(models.Model):
    class Role(models.TextChoices):
        DOCUMENT = "document", _("Policy document")
        SOURCE = "source", _("Editable source")

    class ProcessingState(models.TextChoices):
        PENDING = "pending", _("Processing")
        READY = "ready", _("Ready")
        QUARANTINED = "quarantined", _("Quarantined")
        FAILED = "failed", _("Processing failed")

    policy_version = models.ForeignKey(
        PolicyVersion,
        verbose_name=_("policy version"),
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
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    uploaded_by = models.ForeignKey(
        "user.User",
        verbose_name=_("uploaded by"),
        related_name="policy_files_uploaded",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = PolicyFileQuerySet.as_manager()

    class Meta:
        ordering = ["role", "sort_order", "pk"]
        verbose_name = _("policy file")
        verbose_name_plural = _("policy files")
        constraints = [
            models.CheckConstraint(
                condition=Q(byte_size__gt=0), name="compliance_file_has_bytes"
            ),
        ]
        indexes = [
            models.Index(
                fields=["policy_version", "role", "is_active"],
                name="compliance_file_role",
            ),
        ]

    @property
    def is_readable(self) -> bool:
        return (
            self.is_active
            and self.processing_state == self.ProcessingState.READY
            and bool(self.file)
        )


class PolicyVersionAccess(models.Model):
    """Evidence that a user opened the current policy version or document."""

    class Kind(models.TextChoices):
        DETAIL = "detail", _("Policy detail")
        DOCUMENT = "document", _("Policy document")

    user = models.ForeignKey(
        "user.User",
        verbose_name=_("user"),
        related_name="policy_version_accesses",
        on_delete=models.CASCADE,
    )
    policy_version = models.ForeignKey(
        PolicyVersion,
        verbose_name=_("policy version"),
        related_name="accesses",
        on_delete=models.CASCADE,
    )
    policy_file = models.ForeignKey(
        PolicyFile,
        verbose_name=_("policy file"),
        related_name="accesses",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    content_checksum = models.CharField(_("content checksum"), max_length=64)
    accessed_at = models.DateTimeField(_("accessed at"), auto_now=True)

    class Meta:
        verbose_name = _("policy version access")
        verbose_name_plural = _("policy version accesses")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "policy_version"],
                condition=Q(kind="detail"),
                name="compliance_access_unique_detail",
            ),
            models.UniqueConstraint(
                fields=["user", "policy_version", "policy_file"],
                condition=Q(kind="document"),
                name="compliance_access_unique_document",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind="detail", policy_file__isnull=True)
                    | Q(kind="document", policy_file__isnull=False)
                ),
                name="compliance_access_kind_file",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "policy_version", "kind"],
                name="compliance_access_lookup",
            ),
        ]

    def __str__(self):
        return f"Access {self.user} / {self.policy_version} / {self.kind}"


class PolicyRequirement(models.Model):
    """Acknowledgement obligation for one published policy version."""

    policy_version = models.ForeignKey(
        PolicyVersion,
        verbose_name=_("policy version"),
        related_name="requirements",
        on_delete=models.CASCADE,
    )
    due_at = models.DateTimeField(_("due at"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("policy requirement")
        verbose_name_plural = _("policy requirements")
        constraints = [
            models.UniqueConstraint(
                fields=["policy_version"],
                condition=Q(is_active=True),
                name="compliance_one_active_requirement",
            ),
        ]
        indexes = [
            models.Index(
                fields=["is_active", "due_at"],
                name="compliance_requirement_due",
            ),
        ]

    def __str__(self):
        return f"Requirement for {self.policy_version}"


class PolicyAcknowledgement(models.Model):
    """Immutable acknowledgement evidence for one user and policy version."""

    user = models.ForeignKey(
        "user.User",
        verbose_name=_("user"),
        related_name="policy_acknowledgements",
        on_delete=models.CASCADE,
    )
    policy_version = models.ForeignKey(
        PolicyVersion,
        verbose_name=_("policy version"),
        related_name="acknowledgements",
        on_delete=models.PROTECT,
    )
    content_checksum = models.CharField(_("content checksum"), max_length=64)
    disclosure_version = models.PositiveIntegerField(_("disclosure version"))
    disclosure_text = models.TextField(_("disclosure text"), blank=True)
    acknowledged_at = models.DateTimeField(_("acknowledged at"), auto_now_add=True)
    request_meta = models.JSONField(_("request metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("policy acknowledgement")
        verbose_name_plural = _("policy acknowledgements")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "policy_version"],
                name="compliance_ack_unique_user_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["policy_version", "acknowledged_at"],
                name="compliance_ack_version",
            ),
        ]

    def __str__(self):
        return f"Ack {self.user} / {self.policy_version}"


class PolicyAcknowledgementWaiver(models.Model):
    """Scoped waiver that satisfies a requirement without deleting evidence."""

    user = models.ForeignKey(
        "user.User",
        verbose_name=_("user"),
        related_name="policy_acknowledgement_waivers",
        on_delete=models.CASCADE,
    )
    policy_version = models.ForeignKey(
        PolicyVersion,
        verbose_name=_("policy version"),
        related_name="acknowledgement_waivers",
        on_delete=models.PROTECT,
    )
    reason = models.TextField(_("reason"))
    waived_by = models.ForeignKey(
        "user.User",
        verbose_name=_("waived by"),
        related_name="policy_acknowledgement_waivers_granted",
        on_delete=models.PROTECT,
    )
    waived_at = models.DateTimeField(_("waived at"), auto_now_add=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("policy acknowledgement waiver")
        verbose_name_plural = _("policy acknowledgement waivers")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "policy_version"],
                name="compliance_waiver_unique_user_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["policy_version", "waived_at"],
                name="compliance_waiver_version",
            ),
        ]

    def __str__(self):
        return f"Waiver {self.user} / {self.policy_version}"


class PolicyAcknowledgementCorrection(models.Model):
    """Append-only clerical correction. Never deletes acknowledgement evidence."""

    class Kind(models.TextChoices):
        CLERICAL = "clerical", _("Clerical note")
        REVOKE_WAIVER = "revoke_waiver", _("Revoke waiver")

    user = models.ForeignKey(
        "user.User",
        verbose_name=_("user"),
        related_name="policy_acknowledgement_corrections",
        on_delete=models.CASCADE,
    )
    policy_version = models.ForeignKey(
        PolicyVersion,
        verbose_name=_("policy version"),
        related_name="acknowledgement_corrections",
        on_delete=models.PROTECT,
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    reason = models.TextField(_("reason"))
    corrected_by = models.ForeignKey(
        "user.User",
        verbose_name=_("corrected by"),
        related_name="policy_acknowledgement_corrections_made",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("policy acknowledgement correction")
        verbose_name_plural = _("policy acknowledgement corrections")
        indexes = [
            models.Index(
                fields=["policy_version", "created_at"],
                name="compliance_correction_version",
            ),
        ]

    def __str__(self):
        return f"Correction {self.user} / {self.policy_version}"
