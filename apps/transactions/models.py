"""Real-estate transaction records and explicit party assignments.

Storage only for non-status fields. Every status change goes through
:mod:`apps.transactions.lifecycle` — the model refuses unguarded status
writes the same way agent contracts do.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.transactions.money import money_field
from apps.transactions.taxonomy import (
    ASSIGNMENT_ROLE_CHOICES,
    DOCUMENT_CATEGORY_CHOICES,
    DOCUMENT_COMPLIANCE_STATUS_CHOICES,
    DOCUMENT_REQUIREMENT_CHOICES,
    DOCUMENT_RETENTION_POLICY_CHOICES,
    DOCUMENT_REVIEW_RESOLUTION_CHOICES,
    DOCUMENT_SIGNATURE_STATUS_CHOICES,
    KEY_DATE_TYPE_CHOICES,
    NOTE_VISIBILITY_CHOICES,
    PARTY_KIND_CHOICES,
    PARTY_ROLE_CHOICES,
    PRIMARY_PARTY_ROLES,
    REPRESENTATION_CHOICES,
    SINGLETON_ASSIGNMENT_ROLES,
    STATUS_CHOICES,
    STATUS_CODES,
    TYPE_CHOICES,
    AssignmentRole,
    DocumentCategory,
    DocumentComplianceStatus,
    DocumentRequirement,
    DocumentRetentionPolicy,
    DocumentReviewResolution,
    DocumentSignatureStatus,
    NoteVisibility,
    PartyKind,
    TransactionStatus,
)
from apps.user.models import Office
from apps.user.storage import private_storage

_PRIMARY_PARTY_ROLES: list[str] = sorted(PRIMARY_PARTY_ROLES)
_STATUS_LIST: list[str] = sorted(STATUS_CODES)
_SINGLETON_ROLES: list[str] = sorted(SINGLETON_ASSIGNMENT_ROLES)


class TransactionQuerySet(models.QuerySet["Transaction"]):
    def for_reader(self, user, *, access) -> TransactionQuerySet:
        """Rows this reader may see — applied before anything else.

        Company / superuser short-circuit, then office/region tree, then
        personal grants via active assignments or the convenience FKs.
        """
        if getattr(user, "is_anonymous", False):
            return self.none()

        if getattr(user, "is_superuser", False) or access.company_wide:
            return self.all()

        personal = (
            Q(primary_agent=user)
            | Q(coordinator=user)
            | Q(
                assignments__user=user,
                assignments__ended_at__isnull=True,
            )
        )
        reach = Q(pk__in=[])
        if access.office_keys:
            reach |= Q(office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            reach |= Q(office__region__stable_key__in=sorted(access.region_keys))
        return self.filter(reach | personal).distinct()

    def update(self, **kwargs):
        if "status" in kwargs:
            raise ValidationError(
                {
                    "status": _(
                        "Transaction status may only change through the "
                        "lifecycle transition service."
                    )
                }
            )
        return super().update(**kwargs)


class Transaction(models.Model):
    """One brokerage real-estate deal (buy, sell, or rent)."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    reference = models.CharField(_("reference"), max_length=16, unique=True, blank=True)

    transaction_type = models.CharField(
        _("transaction type"), max_length=20, choices=TYPE_CHOICES
    )
    representation_type = models.CharField(
        _("representation type"), max_length=20, choices=REPRESENTATION_CHOICES
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("owning office"),
        help_text=_("The node that owns this deal. Scope is read from it."),
    )
    primary_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_transactions",
        verbose_name=_("primary agent"),
    )
    coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coordinated_transactions",
        verbose_name=_("assigned coordinator"),
    )

    property_snapshot = models.JSONField(
        _("property snapshot"),
        default=dict,
        blank=True,
        help_text=_("Address and identity fields captured at write time."),
    )
    property_external_ref = models.CharField(
        _("property external reference"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("Opaque CRM/MLS property id for a later join."),
    )
    mls_number = models.CharField(
        _("MLS number"), max_length=64, blank=True, db_index=True
    )

    client_snapshots = models.JSONField(
        _("client snapshots"),
        default=list,
        blank=True,
        help_text=_("Client presentation data; gated by field permission."),
    )
    client_external_refs = models.JSONField(
        _("client external references"),
        default=list,
        blank=True,
        help_text=_("Opaque CRM contact ids for a later join."),
    )

    list_price = money_field(verbose_name=_("list price"))
    contract_price = money_field(verbose_name=_("contract price"))

    acceptance_date = models.DateField(_("acceptance date"), null=True, blank=True)
    closing_date = models.DateField(_("closing date"), null=True, blank=True)

    lender_ref = models.CharField(_("lender reference"), max_length=128, blank=True)
    title_ref = models.CharField(_("title reference"), max_length=128, blank=True)
    referral_ref = models.CharField(_("referral reference"), max_length=128, blank=True)

    submission_key = models.CharField(
        _("submission key"),
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        help_text=_(
            "Client-supplied idempotency key for create/prepare. Null until "
            "the first prepare attempt stamps one."
        ),
    )

    status = models.CharField(
        _("status"),
        max_length=32,
        choices=STATUS_CHOICES,
        default=TransactionStatus.DRAFT,
        db_index=True,
    )
    held_from_status = models.CharField(
        _("held from status"),
        max_length=32,
        blank=True,
        help_text=_("Pipeline status restored when leaving On Hold."),
    )

    preparing_at = models.DateTimeField(_("preparing at"), null=True, blank=True)
    under_contract_at = models.DateTimeField(
        _("under contract at"), null=True, blank=True
    )
    pending_at = models.DateTimeField(_("pending at"), null=True, blank=True)
    compliance_review_at = models.DateTimeField(
        _("compliance review at"), null=True, blank=True
    )
    compliance_approved_at = models.DateTimeField(
        _("compliance approved at"),
        null=True,
        blank=True,
        help_text=_(
            "Set when leaving Compliance Review for Ready to Close. "
            "Closing refuses without it."
        ),
    )
    ready_to_close_at = models.DateTimeField(
        _("ready to close at"), null=True, blank=True
    )
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    archived_at = models.DateTimeField(_("archived at"), null=True, blank=True)
    on_hold_at = models.DateTimeField(_("on hold at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    withdrawn_at = models.DateTimeField(_("withdrawn at"), null=True, blank=True)
    terminated_at = models.DateTimeField(_("terminated at"), null=True, blank=True)

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions_archived",
        verbose_name=_("archived by"),
    )
    archive_reason = models.CharField(_("archive reason"), max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions_created",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")
        permissions = (
            (
                "view_transaction_financials",
                _("Can view transaction list and contract prices"),
            ),
            (
                "view_transaction_clients",
                _("Can view transaction client snapshots"),
            ),
        )
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=_STATUS_LIST),
                name="transaction_status_is_known",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(status=TransactionStatus.CLOSED) & Q(closed_at__isnull=False))
                    | (
                        ~Q(status=TransactionStatus.CLOSED)
                        & ~Q(status=TransactionStatus.ARCHIVED)
                        & Q(closed_at__isnull=True)
                    )
                    | (
                        Q(status=TransactionStatus.ARCHIVED)
                        & Q(closed_at__isnull=False)
                        & Q(archived_at__isnull=False)
                    )
                ),
                name="transaction_closed_at_matches_status",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=TransactionStatus.ARCHIVED, archived_at__isnull=False)
                    | (
                        ~Q(status=TransactionStatus.ARCHIVED)
                        & Q(archived_at__isnull=True)
                    )
                ),
                name="transaction_archived_at_matches_status",
            ),
        ]
        indexes = [
            models.Index(fields=["office", "status"], name="txn_office_status_idx"),
            models.Index(
                fields=["status", "closing_date"], name="txn_status_closing_idx"
            ),
            models.Index(
                fields=["primary_agent", "status"], name="txn_primary_status_idx"
            ),
            models.Index(fields=["mls_number"], name="txn_mls_number_idx"),
            models.Index(fields=["coordinator", "status"], name="txn_coord_status_idx"),
        ]

    def __str__(self) -> str:
        return self.reference or f"TXN-{self.pk or '?'}"

    @property
    def office_pk(self) -> int | None:
        return getattr(self, "office_id", None)

    @property
    def primary_agent_pk(self) -> int | None:
        return getattr(self, "primary_agent_id", None)

    @property
    def coordinator_pk(self) -> int | None:
        return getattr(self, "coordinator_id", None)

    @property
    def status_label(self) -> str:
        from apps.transactions.taxonomy import STATUS_LABELS

        return str(STATUS_LABELS.get(self.status, self.status))

    def save(self, *args, **kwargs):
        """Refuse unguarded status mutations outside the lifecycle service."""
        if self.pk:
            from apps.transactions.lifecycle import status_write_allowed

            previous = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if (
                previous is not None
                and previous != self.status
                and not status_write_allowed()
            ):
                raise ValidationError(
                    {
                        "status": _(
                            "Transaction status may only change through the "
                            "lifecycle transition service."
                        )
                    }
                )
        super().save(*args, **kwargs)


class TransactionAssignment(models.Model):
    """Explicit, auditable membership of a user on a transaction."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("transaction"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transaction_assignments",
        verbose_name=_("user"),
    )
    role = models.CharField(_("role"), max_length=32, choices=ASSIGNMENT_ROLE_CHOICES)
    assigned_at = models.DateTimeField(_("assigned at"), auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_assignments_made",
        verbose_name=_("assigned by"),
    )
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at", "-pk"]
        verbose_name = _("transaction assignment")
        verbose_name_plural = _("transaction assignments")
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "user", "role"],
                condition=Q(ended_at__isnull=True),
                name="txn_assignment_unique_active",
            ),
            models.UniqueConstraint(
                fields=["transaction", "role"],
                condition=Q(ended_at__isnull=True, role__in=_SINGLETON_ROLES),
                name="txn_assignment_singleton_active",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "ended_at"], name="txn_assign_user_active_idx"
            ),
            models.Index(
                fields=["transaction", "role", "ended_at"],
                name="txn_assign_role_active_idx",
            ),
        ]

    def __str__(self) -> str:
        user_id = getattr(self, "user_id", None)
        transaction_id = getattr(self, "transaction_id", None)
        return f"{self.role}:{user_id}@{transaction_id}"

    @property
    def user_pk(self) -> int | None:
        return getattr(self, "user_id", None)

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def role_label(self) -> str:
        from apps.transactions.taxonomy import ASSIGNMENT_ROLE_LABELS

        return str(ASSIGNMENT_ROLE_LABELS.get(self.role, self.role))


class TransactionParty(models.Model):
    """Structured party on a deal (buyer, seller, vendor, co-party, …)."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="parties",
        verbose_name=_("transaction"),
    )
    role = models.CharField(_("role"), max_length=32, choices=PARTY_ROLE_CHOICES)
    kind = models.CharField(
        _("kind"),
        max_length=20,
        choices=PARTY_KIND_CHOICES,
        default=PartyKind.PERSON,
    )
    display_name = models.CharField(_("display name"), max_length=255)
    organization_name = models.CharField(
        _("organization name"), max_length=255, blank=True
    )
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    representation = models.CharField(
        _("representation"),
        max_length=20,
        choices=REPRESENTATION_CHOICES,
        blank=True,
    )
    is_primary = models.BooleanField(_("is primary"), default=False)
    valid_from = models.DateTimeField(_("valid from"), null=True, blank=True)
    valid_until = models.DateTimeField(_("valid until"), null=True, blank=True)
    snapshot = models.JSONField(
        _("snapshot"),
        default=dict,
        blank=True,
        help_text=_("Frozen presentation fields captured on each write."),
    )
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_parties_created",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["role", "-is_primary", "display_name", "pk"]
        verbose_name = _("transaction party")
        verbose_name_plural = _("transaction parties")
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "role"],
                condition=Q(
                    ended_at__isnull=True,
                    is_primary=True,
                    role__in=_PRIMARY_PARTY_ROLES,
                ),
                name="txn_party_unique_primary_role",
            ),
        ]
        indexes = [
            models.Index(
                fields=["transaction", "role", "ended_at"],
                name="txn_party_role_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role}:{self.display_name}"

    @property
    def role_label(self) -> str:
        from apps.transactions.taxonomy import PARTY_ROLE_LABELS

        return str(PARTY_ROLE_LABELS.get(self.role, self.role))

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


class TransactionPropertySnapshot(models.Model):
    """Immutable history row for material property-field changes."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="property_snapshots",
        verbose_name=_("transaction"),
    )
    snapshot = models.JSONField(_("snapshot"), default=dict)
    mls_number = models.CharField(_("MLS number"), max_length=64, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_property_snapshots",
        verbose_name=_("recorded by"),
    )
    recorded_at = models.DateTimeField(_("recorded at"), auto_now_add=True)
    change_summary = models.JSONField(
        _("change summary"),
        default=list,
        blank=True,
        help_text=_("Allowlisted field keys that changed in this revision."),
    )

    class Meta:
        ordering = ["-recorded_at", "-pk"]
        verbose_name = _("transaction property snapshot")
        verbose_name_plural = _("transaction property snapshots")
        indexes = [
            models.Index(
                fields=["transaction", "-recorded_at"],
                name="txn_prop_snap_txn_idx",
            ),
        ]

    def __str__(self) -> str:
        transaction_id = getattr(self, "transaction_id", None)
        return f"property@{transaction_id}:{self.pk}"


class TransactionKeyDate(models.Model):
    """Named key date on a deal (acceptance, closing, contingencies, …)."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="key_dates",
        verbose_name=_("transaction"),
    )
    date_type = models.CharField(
        _("date type"), max_length=32, choices=KEY_DATE_TYPE_CHOICES
    )
    label = models.CharField(_("label"), max_length=120, blank=True)
    occurs_at = models.DateTimeField(_("occurs at"), null=True, blank=True)
    timezone = models.CharField(_("timezone"), max_length=64, blank=True)
    source = models.CharField(_("source"), max_length=64, blank=True)
    is_required = models.BooleanField(_("is required"), default=False)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supersedes",
        verbose_name=_("superseded by"),
    )
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_key_dates_created",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["occurs_at", "date_type", "pk"]
        verbose_name = _("transaction key date")
        verbose_name_plural = _("transaction key dates")
        indexes = [
            models.Index(
                fields=["transaction", "date_type", "ended_at"],
                name="txn_keydate_type_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date_type}:{self.occurs_at}"

    @property
    def date_type_label(self) -> str:
        from apps.transactions.taxonomy import KEY_DATE_TYPE_LABELS

        return str(KEY_DATE_TYPE_LABELS.get(self.date_type, self.date_type))

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


class TransactionNote(models.Model):
    """Workspace note with explicit visibility — never one unrestricted stream."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name=_("transaction"),
    )
    body = models.TextField(_("body"))
    visibility = models.CharField(
        _("visibility"),
        max_length=32,
        choices=NOTE_VISIBILITY_CHOICES,
        default=NoteVisibility.TEAM,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transaction_notes",
        verbose_name=_("author"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("transaction note")
        verbose_name_plural = _("transaction notes")
        indexes = [
            models.Index(
                fields=["transaction", "visibility", "ended_at"],
                name="txn_note_vis_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"note:{self.public_id}"

    @property
    def visibility_label(self) -> str:
        from apps.transactions.taxonomy import NOTE_VISIBILITY_LABELS

        return str(NOTE_VISIBILITY_LABELS.get(self.visibility, self.visibility))

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


def _transaction_document_upload_to(
    instance: TransactionDocumentVersion, filename: str
) -> str:
    from apps.transactions.media import storage_key

    return storage_key(filename or instance.original_name or "file.bin")


class TransactionDocument(models.Model):
    """Deal document package (family/slot) holding versioned files."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name=_("transaction"),
    )
    category = models.CharField(
        _("category"),
        max_length=32,
        choices=DOCUMENT_CATEGORY_CHOICES,
        default=DocumentCategory.OTHER,
    )
    requirement = models.CharField(
        _("requirement"),
        max_length=16,
        choices=DOCUMENT_REQUIREMENT_CHOICES,
        default=DocumentRequirement.OPTIONAL,
    )
    title = models.CharField(_("title"), max_length=180)
    current_version = models.ForeignKey(
        "TransactionDocumentVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("current version"),
    )
    retention_policy = models.CharField(
        _("retention policy"),
        max_length=32,
        choices=DOCUMENT_RETENTION_POLICY_CHOICES,
        default=DocumentRetentionPolicy.DEAL_CLOSE_PLUS_7Y,
    )
    retain_until = models.DateField(_("retain until"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_documents_created",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)

    class Meta:
        ordering = ["category", "title", "pk"]
        verbose_name = _("transaction document")
        verbose_name_plural = _("transaction documents")
        indexes = [
            models.Index(
                fields=["transaction", "ended_at", "category"],
                name="txn_doc_txn_active_cat_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category}:{self.title}"

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def current_version_pk(self) -> int | None:
        return getattr(self, "current_version_id", None)

    @property
    def category_label(self) -> str:
        from apps.transactions.taxonomy import DOCUMENT_CATEGORY_LABELS

        return str(DOCUMENT_CATEGORY_LABELS.get(self.category, self.category))

    @property
    def requirement_label(self) -> str:
        from apps.transactions.taxonomy import DOCUMENT_REQUIREMENT_LABELS

        return str(DOCUMENT_REQUIREMENT_LABELS.get(self.requirement, self.requirement))


class TransactionDocumentVersion(models.Model):
    """Immutable file revision on a deal document package."""

    class ProcessingState(models.TextChoices):
        PENDING = "pending", _("Processing")
        READY = "ready", _("Ready")
        QUARANTINED = "quarantined", _("Quarantined")
        FAILED = "failed", _("Processing failed")

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    document = models.ForeignKey(
        TransactionDocument,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("document"),
    )
    version_number = models.PositiveIntegerField(_("version number"), default=1)
    original_name = models.CharField(_("original name"), max_length=255)
    display_name = models.CharField(_("display name"), max_length=180)
    file = models.FileField(
        _("file"),
        max_length=255,
        storage=private_storage,
        upload_to=_transaction_document_upload_to,
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
    signature_status = models.CharField(
        _("signature status"),
        max_length=16,
        choices=DOCUMENT_SIGNATURE_STATUS_CHOICES,
        default=DocumentSignatureStatus.NONE,
    )
    compliance_status = models.CharField(
        _("compliance status"),
        max_length=16,
        choices=DOCUMENT_COMPLIANCE_STATUS_CHOICES,
        default=DocumentComplianceStatus.NONE,
    )
    locked_at = models.DateTimeField(_("locked at"), null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_document_versions_locked",
        verbose_name=_("locked by"),
    )
    lock_reason = models.CharField(_("lock reason"), max_length=64, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_document_versions_uploaded",
        verbose_name=_("uploaded by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["-version_number", "-pk"]
        verbose_name = _("transaction document version")
        verbose_name_plural = _("transaction document versions")
        constraints = [
            models.UniqueConstraint(
                fields=["document", "version_number"],
                name="txn_doc_unique_document_version",
            ),
            models.CheckConstraint(
                condition=Q(byte_size__gt=0),
                name="txn_doc_version_has_bytes",
            ),
        ]
        indexes = [
            models.Index(
                fields=["document", "is_active", "processing_state"],
                name="txn_doc_ver_state_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} (v{self.version_number})"

    @property
    def is_readable(self) -> bool:
        return (
            self.is_active
            and self.processing_state == self.ProcessingState.READY
            and bool(self.file)
        )

    @property
    def is_locked(self) -> bool:
        if self.locked_at is not None:
            return True
        return (
            self.signature_status == DocumentSignatureStatus.SIGNED
            or self.compliance_status == DocumentComplianceStatus.APPROVED
        )

    @property
    def is_image(self) -> bool:
        return (self.media_type or "").startswith("image/")


class TransactionDocumentReviewComment(models.Model):
    """Version-bound review comment with visibility and resolution."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    version = models.ForeignKey(
        TransactionDocumentVersion,
        on_delete=models.CASCADE,
        related_name="review_comments",
        verbose_name=_("version"),
    )
    body = models.TextField(_("body"))
    visibility = models.CharField(
        _("visibility"),
        max_length=32,
        choices=NOTE_VISIBILITY_CHOICES,
        default=NoteVisibility.TEAM,
    )
    resolution_state = models.CharField(
        _("resolution state"),
        max_length=16,
        choices=DOCUMENT_REVIEW_RESOLUTION_CHOICES,
        default=DocumentReviewResolution.OPEN,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transaction_document_review_comments",
        verbose_name=_("author"),
    )
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_document_reviews_resolved",
        verbose_name=_("resolved by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("transaction document review comment")
        verbose_name_plural = _("transaction document review comments")
        indexes = [
            models.Index(
                fields=["version", "visibility", "ended_at"],
                name="txn_doc_review_vis_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"review:{self.public_id}"

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def visibility_label(self) -> str:
        from apps.transactions.taxonomy import NOTE_VISIBILITY_LABELS

        return str(NOTE_VISIBILITY_LABELS.get(self.visibility, self.visibility))

    @property
    def resolution_label(self) -> str:
        from apps.transactions.taxonomy import DOCUMENT_REVIEW_RESOLUTION_LABELS

        return str(
            DOCUMENT_REVIEW_RESOLUTION_LABELS.get(
                self.resolution_state, self.resolution_state
            )
        )


# Re-export for callers that expect AssignmentRole on the model module.
__all__ = [
    "AssignmentRole",
    "Transaction",
    "TransactionAssignment",
    "TransactionDocument",
    "TransactionDocumentReviewComment",
    "TransactionDocumentVersion",
    "TransactionKeyDate",
    "TransactionNote",
    "TransactionParty",
    "TransactionPropertySnapshot",
    "TransactionQuerySet",
]
