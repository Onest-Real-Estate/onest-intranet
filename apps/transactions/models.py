"""Real-estate transaction records and explicit party assignments.

Storage only for non-status fields. Every status change goes through
:mod:`apps.transactions.lifecycle` — the model refuses unguarded status
writes the same way agent contracts do.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

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
    SIGNATURE_ARTIFACT_KIND_CHOICES,
    SIGNATURE_DELIVERY_METHOD_CHOICES,
    SIGNATURE_FIELD_TYPE_CHOICES,
    SIGNATURE_INTENT_STATUS_CHOICES,
    SIGNATURE_PACKAGE_STATUS_CHOICES,
    SIGNATURE_ROUTING_MODE_CHOICES,
    SIGNATURE_SIGNER_STATUS_CHOICES,
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
    SignatureArtifactKind,
    SignatureDeliveryMethod,
    SignatureFieldType,
    SignatureIntentStatus,
    SignaturePackageStatus,
    SignatureRoutingMode,
    SignatureSignerStatus,
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


def _signature_artifact_upload_to(instance: SignatureArtifact, filename: str) -> str:
    from apps.transactions.media import storage_key

    return storage_key(filename or instance.display_name or "artifact.pdf")


def _signature_appearance_upload_to(instance: SignatureRecord, filename: str) -> str:
    from apps.transactions.media import storage_key

    return storage_key(filename or "appearance.png")


def _signature_initials_upload_to(instance: SignatureRecord, filename: str) -> str:
    from apps.transactions.media import storage_key

    return storage_key(filename or "initials.png")


class SignaturePackage(models.Model):
    """Multi-party e-signature package bound to locked deal document versions."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="signature_packages",
        verbose_name=_("transaction"),
    )
    title = models.CharField(_("title"), max_length=180)
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=SIGNATURE_PACKAGE_STATUS_CHOICES,
        default=SignaturePackageStatus.DRAFT,
        db_index=True,
    )
    routing_mode = models.CharField(
        _("routing mode"),
        max_length=16,
        choices=SIGNATURE_ROUTING_MODE_CHOICES,
        default=SignatureRoutingMode.ORDERED,
    )
    disclosure_version = models.CharField(
        _("disclosure version"), max_length=64, blank=True, default=""
    )
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signature_packages_created",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    if TYPE_CHECKING:
        transaction_id: int
        created_by_id: int | None
        documents: models.Manager[SignaturePackageDocument]
        signers: models.Manager[SignaturePackageSigner]
        fields: models.Manager[SignaturePackageField]
        artifacts: models.Manager[SignatureArtifact]
        #: Set by the lifecycle service for the one legal status write.
        _allow_status_write: bool

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("signature package")
        verbose_name_plural = _("signature packages")
        indexes = [
            models.Index(
                fields=["transaction", "status", "-created_at"],
                name="txn_sig_pkg_txn_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title}:{self.status}"

    def save(self, *args, **kwargs):
        if self.pk:
            previous = (
                SignaturePackage.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if previous is not None and previous != self.status:
                update_fields = kwargs.get("update_fields")
                if update_fields is not None and "status" not in update_fields:
                    raise ValidationError(
                        {
                            "status": _(
                                "Signature package status may only change through "
                                "the signing lifecycle service."
                            )
                        }
                    )
                # Allow service-layer updates that include status in update_fields
                # or full saves from the service; refuse accidental drift when
                # callers omit update_fields after mutating status in memory.
                if update_fields is None and not getattr(
                    self, "_allow_status_write", False
                ):
                    raise ValidationError(
                        {
                            "status": _(
                                "Signature package status may only change through "
                                "the signing lifecycle service."
                            )
                        }
                    )
        return super().save(*args, **kwargs)


class SignaturePackageDocument(models.Model):
    """Source document version frozen into a signature package."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    package = models.ForeignKey(
        SignaturePackage,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name=_("package"),
    )
    version = models.ForeignKey(
        TransactionDocumentVersion,
        on_delete=models.PROTECT,
        related_name="signature_package_documents",
        verbose_name=_("document version"),
    )
    source_checksum = models.CharField(_("source checksum"), max_length=64)
    page_count = models.PositiveIntegerField(_("page count"), default=1)
    sort_order = models.PositiveIntegerField(_("sort order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    if TYPE_CHECKING:
        package_id: int
        version_id: int

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = _("signature package document")
        verbose_name_plural = _("signature package documents")
        constraints = [
            models.UniqueConstraint(
                fields=["package", "version"],
                name="txn_sig_pkg_unique_version",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.package_id}:{self.version_id}"


class SignaturePackageSigner(models.Model):
    """One party asked to sign a package."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    package = models.ForeignKey(
        SignaturePackage,
        on_delete=models.CASCADE,
        related_name="signers",
        verbose_name=_("package"),
    )
    role_label = models.CharField(_("role label"), max_length=64)
    display_name = models.CharField(_("display name"), max_length=255)
    email = models.EmailField(_("email"))
    delivery_method = models.CharField(
        _("delivery method"),
        max_length=16,
        choices=SIGNATURE_DELIVERY_METHOD_CHOICES,
        default=SignatureDeliveryMethod.EMAIL,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_signature_signers",
        verbose_name=_("hub user"),
    )
    party = models.ForeignKey(
        TransactionParty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signature_signers",
        verbose_name=_("transaction party"),
    )
    routing_order = models.PositiveIntegerField(_("routing order"), default=1)
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=SIGNATURE_SIGNER_STATUS_CHOICES,
        default=SignatureSignerStatus.PENDING,
        db_index=True,
    )
    invited_at = models.DateTimeField(_("invited at"), null=True, blank=True)
    viewed_at = models.DateTimeField(_("viewed at"), null=True, blank=True)
    signed_at = models.DateTimeField(_("signed at"), null=True, blank=True)
    declined_at = models.DateTimeField(_("declined at"), null=True, blank=True)
    decline_reason = models.CharField(
        _("decline reason"), max_length=255, blank=True, default=""
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    if TYPE_CHECKING:
        package_id: int
        user_id: int | None
        party_id: int | None
        fields: models.Manager[SignaturePackageField]
        access_tokens: models.Manager[SignatureAccessToken]

    class Meta:
        ordering = ["routing_order", "pk"]
        verbose_name = _("signature package signer")
        verbose_name_plural = _("signature package signers")
        constraints = [
            models.UniqueConstraint(
                fields=["package", "email"],
                name="txn_sig_pkg_unique_signer_email",
            ),
        ]
        indexes = [
            models.Index(
                fields=["package", "routing_order", "status"],
                name="txn_sig_signer_route_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role_label}:{self.email}"

    @property
    def signer_key(self) -> str:
        """Stable role key used in field layout / PDF stamp."""
        return str(self.public_id)


class SignaturePackageField(models.Model):
    """Page-coordinate field assigned to one signer on one package document."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    package = models.ForeignKey(
        SignaturePackage,
        on_delete=models.CASCADE,
        related_name="fields",
        verbose_name=_("package"),
    )
    document = models.ForeignKey(
        SignaturePackageDocument,
        on_delete=models.CASCADE,
        related_name="fields",
        verbose_name=_("package document"),
    )
    signer = models.ForeignKey(
        SignaturePackageSigner,
        on_delete=models.CASCADE,
        related_name="fields",
        verbose_name=_("signer"),
    )
    name = models.CharField(_("name"), max_length=80)
    field_type = models.CharField(
        _("field type"),
        max_length=16,
        choices=SIGNATURE_FIELD_TYPE_CHOICES,
        default=SignatureFieldType.SIGNATURE,
    )
    page = models.PositiveIntegerField(_("page"), default=1)
    x = models.FloatField(_("x"))
    y = models.FloatField(_("y"))
    w = models.FloatField(_("width"))
    h = models.FloatField(_("height"))
    required = models.BooleanField(_("required"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    if TYPE_CHECKING:
        package_id: int
        document_id: int
        signer_id: int

    class Meta:
        ordering = ["document_id", "page", "pk"]
        verbose_name = _("signature package field")
        verbose_name_plural = _("signature package fields")
        constraints = [
            models.UniqueConstraint(
                fields=["package", "name"],
                name="txn_sig_pkg_unique_field_name",
            ),
            models.CheckConstraint(
                condition=Q(page__gte=1)
                & Q(w__gt=0)
                & Q(h__gt=0)
                & Q(x__gte=0)
                & Q(y__gte=0),
                name="txn_sig_field_bounds_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}:{self.field_type}"


class SignatureAccessToken(models.Model):
    """Hashed magic-link token for an external email signer."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    signer = models.ForeignKey(
        SignaturePackageSigner,
        on_delete=models.CASCADE,
        related_name="access_tokens",
        verbose_name=_("signer"),
    )
    token_hash = models.CharField(_("token hash"), max_length=64, unique=True)
    expires_at = models.DateTimeField(_("expires at"), db_index=True)
    consumed_at = models.DateTimeField(_("consumed at"), null=True, blank=True)
    last_sent_at = models.DateTimeField(_("last sent at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    if TYPE_CHECKING:
        signer_id: int

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("signature access token")
        verbose_name_plural = _("signature access tokens")
        indexes = [
            models.Index(
                fields=["signer", "-created_at"],
                name="txn_sig_token_signer_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"token:{self.public_id}"

    @property
    def is_active(self) -> bool:
        from django.utils import timezone

        if self.consumed_at is not None:
            return False
        return self.expires_at > timezone.now()


class SignatureSigningIntent(models.Model):
    """Short-lived ceremony binding for one signer on one package."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    package = models.ForeignKey(
        SignaturePackage,
        on_delete=models.PROTECT,
        related_name="signing_intents",
        verbose_name=_("package"),
    )
    signer = models.ForeignKey(
        SignaturePackageSigner,
        on_delete=models.PROTECT,
        related_name="signing_intents",
        verbose_name=_("signer"),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_signing_intents",
        verbose_name=_("actor"),
    )
    package_version = models.CharField(_("package version token"), max_length=64)
    source_checksums = models.JSONField(_("source checksums"), default=dict)
    session_key_hash = models.CharField(_("session key hash"), max_length=64)
    access_token_hash = models.CharField(
        _("access token hash"), max_length=64, blank=True, default=""
    )
    request_ip_hash = models.CharField(
        _("request IP hash"), max_length=64, blank=True, default=""
    )
    request_ua_hash = models.CharField(
        _("request user-agent hash"), max_length=64, blank=True, default=""
    )
    disclosure_version = models.CharField(_("disclosure version"), max_length=64)
    consent_accepted_at = models.DateTimeField(_("consent accepted at"))
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=SIGNATURE_INTENT_STATUS_CHOICES,
        default=SignatureIntentStatus.PENDING,
        db_index=True,
    )
    expires_at = models.DateTimeField(_("expires at"), db_index=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    consumed_at = models.DateTimeField(_("consumed at"), null=True, blank=True)

    if TYPE_CHECKING:
        package_id: int
        signer_id: int
        actor_id: int | None

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("signature signing intent")
        verbose_name_plural = _("signature signing intents")
        indexes = [
            models.Index(
                fields=["package", "signer", "status"],
                name="txn_sig_intent_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.public_id}:{self.status}"


class SignatureRecord(models.Model):
    """Immutable electronic signature evidence for one package signer."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    package = models.ForeignKey(
        SignaturePackage,
        on_delete=models.PROTECT,
        related_name="signature_records",
        verbose_name=_("package"),
    )
    signer = models.ForeignKey(
        SignaturePackageSigner,
        on_delete=models.PROTECT,
        related_name="signature_records",
        verbose_name=_("signer"),
    )
    intent = models.OneToOneField(
        SignatureSigningIntent,
        on_delete=models.PROTECT,
        related_name="signature_record",
        verbose_name=_("signing intent"),
    )
    method = models.CharField(
        _("method"),
        max_length=32,
        default="hub_embedded",
    )
    disclosure_version = models.CharField(_("disclosure version"), max_length=64)
    source_checksums = models.JSONField(_("source checksums"), default=dict)
    field_values = models.JSONField(_("field values"), default=dict, blank=True)
    signed_date_value = models.CharField(
        _("signed date value"), max_length=64, blank=True, default=""
    )
    appearance_file = models.FileField(
        _("signature appearance"),
        max_length=255,
        storage=private_storage,
        upload_to=_signature_appearance_upload_to,
        blank=True,
        default="",
    )
    initials_file = models.FileField(
        _("initials appearance"),
        max_length=255,
        storage=private_storage,
        upload_to=_signature_initials_upload_to,
        blank=True,
        default="",
    )
    appearance_checksum = models.CharField(
        _("appearance checksum"), max_length=64, blank=True, default=""
    )
    request_ip_hash = models.CharField(
        _("request IP hash"), max_length=64, blank=True, default=""
    )
    request_ua_hash = models.CharField(
        _("request user-agent hash"), max_length=64, blank=True, default=""
    )
    signed_at = models.DateTimeField(_("signed at"), auto_now_add=True)

    if TYPE_CHECKING:
        package_id: int
        signer_id: int
        intent_id: int | None

    class Meta:
        ordering = ["-signed_at", "-pk"]
        verbose_name = _("signature record")
        verbose_name_plural = _("signature records")
        constraints = [
            models.UniqueConstraint(
                fields=["package", "signer"],
                name="txn_sig_unique_package_signer",
            ),
        ]

    def __str__(self) -> str:
        return f"sig:{self.public_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                {"form": [_("Signature records are immutable after create.")]}
            )
        return super().save(*args, **kwargs)


class SignatureArtifact(models.Model):
    """Write-once signed PDF or certificate of completion for a package document."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    package = models.ForeignKey(
        SignaturePackage,
        on_delete=models.PROTECT,
        related_name="artifacts",
        verbose_name=_("package"),
    )
    package_document = models.ForeignKey(
        SignaturePackageDocument,
        on_delete=models.PROTECT,
        related_name="artifacts",
        verbose_name=_("package document"),
        null=True,
        blank=True,
    )
    kind = models.CharField(
        _("kind"),
        max_length=32,
        choices=SIGNATURE_ARTIFACT_KIND_CHOICES,
        default=SignatureArtifactKind.SIGNED_PDF,
    )
    display_name = models.CharField(_("display name"), max_length=180)
    file = models.FileField(
        _("file"),
        max_length=255,
        storage=private_storage,
        upload_to=_signature_artifact_upload_to,
    )
    media_type = models.CharField(
        _("media type"), max_length=120, default="application/pdf"
    )
    byte_size = models.PositiveBigIntegerField(_("size in bytes"))
    checksum = models.CharField(_("checksum"), max_length=64)
    source_checksum = models.CharField(
        _("source checksum"), max_length=64, blank=True, default=""
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    if TYPE_CHECKING:
        package_id: int
        package_document_id: int | None

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("signature artifact")
        verbose_name_plural = _("signature artifacts")
        constraints = [
            models.UniqueConstraint(
                fields=["package", "package_document", "kind"],
                condition=Q(package_document__isnull=False),
                name="txn_sig_unique_doc_artifact_kind",
            ),
            models.UniqueConstraint(
                fields=["package", "kind"],
                condition=Q(package_document__isnull=True),
                name="txn_sig_unique_pkg_artifact_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.public_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                {"form": [_("Signature artifacts are immutable after create.")]}
            )
        return super().save(*args, **kwargs)


# Re-export for callers that expect AssignmentRole on the model module.
__all__ = [
    "AssignmentRole",
    "SignatureAccessToken",
    "SignatureArtifact",
    "SignaturePackage",
    "SignaturePackageDocument",
    "SignaturePackageField",
    "SignaturePackageSigner",
    "SignatureRecord",
    "SignatureSigningIntent",
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
