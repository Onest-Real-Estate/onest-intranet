"""Agent Contract domain models.

Historical identity is immutable: legal party/office/terms snapshots freeze at
issuance, artifacts keep checksums in protected storage, and prior versions stay
reachable through family/supersedes/amends links instead of being overwritten.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.contract.calculations.rules import CURRENT_RULE_VERSION
from apps.contract.statuses import ContractStatus
from apps.contract.terms import (
    HUNDRED,
    ZERO,
    CommissionBasis,
    money_field,
    percent_field,
    quantize_money,
    quantize_percent,
)
from apps.user.storage import private_storage

if TYPE_CHECKING:
    from apps.user.models import User  # noqa: F401


def _artifact_upload_to(instance: ContractArtifact, filename: str) -> str:
    # Random key under the contract public id — never the browser filename alone.
    safe = Path(filename).name
    suffix = f"{uuid.uuid4().hex}_{safe}"
    return f"contracts/{instance.contract.public_id}/{instance.kind}/{suffix}"


def _template_source_upload_to(instance: ContractTemplateVersion, filename: str) -> str:
    safe = Path(filename).name
    suffix = f"{uuid.uuid4().hex}_{safe}"
    return (
        "contract-templates/"
        f"{instance.template.public_id}/{instance.public_id}/source/{suffix}"
    )


def _template_preview_upload_to(
    instance: ContractTemplateVersion, filename: str
) -> str:
    safe = Path(filename).name
    suffix = f"{uuid.uuid4().hex}_{safe}"
    return (
        "contract-templates/"
        f"{instance.template.public_id}/{instance.public_id}/preview/{suffix}"
    )


class ContractTemplate(models.Model):
    """Template family. Full management workflow lands in a later issue.

    Enough structure for contracts to PROTECT-reference an originating template
    without depending on Django admin as the product surface.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        RETIRED = "retired", _("Retired")

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, unique=True, editable=False
    )
    stable_key = models.SlugField(
        _("stable key"),
        max_length=80,
        unique=True,
        help_text=_("Immutable machine key for the template family."),
    )
    name = models.CharField(_("name"), max_length=180)
    description = models.TextField(_("description"), blank=True)
    jurisdiction_state_codes = models.JSONField(
        _("jurisdiction state codes"),
        default=list,
        blank=True,
        help_text=_("Applicable US state codes, e.g. ['VA', 'MD']."),
    )
    company_wide = models.BooleanField(
        _("company wide"),
        default=False,
        help_text=_("Applies brokerage-wide instead of a narrower office scope."),
    )
    applicable_offices = models.ManyToManyField(
        "user.Office",
        verbose_name=_("applicable offices"),
        related_name="contract_templates",
        blank=True,
        help_text=_("Explicit offices this template family applies to."),
    )
    applicable_regions = models.ManyToManyField(
        "user.Office",
        verbose_name=_("applicable regions"),
        related_name="regional_contract_templates",
        blank=True,
        help_text=_("Region office rows this template family applies to."),
    )
    effective_from = models.DateField(_("effective from"), null=True, blank=True)
    effective_until = models.DateField(_("effective until"), null=True, blank=True)
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    active_version = models.ForeignKey(
        "ContractTemplateVersion",
        verbose_name=_("active version"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Published version currently active for new contracts."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="contract_templates_created",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("approved by"),
        related_name="contract_templates_approved",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    retired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("retired by"),
        related_name="contract_templates_retired",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    retired_at = models.DateTimeField(_("retired at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    if TYPE_CHECKING:
        active_version_id: int | None
        created_by_id: int | None
        approved_by_id: int | None
        retired_by_id: int | None

    class Meta:
        ordering = ["name"]
        verbose_name = _("contract template")
        verbose_name_plural = _("contract templates")
        permissions = (
            (
                "manage_contract_templates",
                _("Can manage scoped contract template drafts"),
            ),
            (
                "approve_contract_templates",
                _("Can approve and activate scoped contract templates"),
            ),
        )

    def __str__(self) -> str:
        return self.name

    def clean(self):
        super().clean()
        errors: dict[str, list[str]] = {}

        if self.pk:
            original = (
                type(self).objects.filter(pk=self.pk).values("stable_key").first()
            )
            if original and original["stable_key"] != self.stable_key:
                errors.setdefault("stable_key", []).append(
                    str(_("Stable identity cannot be changed once created."))
                )

        states = [str(code).upper() for code in (self.jurisdiction_state_codes or [])]
        if not all(len(code) == 2 and code.isalpha() for code in states):
            errors.setdefault("jurisdiction_state_codes", []).append(
                str(_("Jurisdiction codes must be two-letter US state codes."))
            )
        self.jurisdiction_state_codes = sorted(set(states))

        if (
            self.effective_from
            and self.effective_until
            and self.effective_until < self.effective_from
        ):
            errors.setdefault("effective_until", []).append(
                str(_("Effective until cannot be earlier than effective from."))
            )

        if self.active_version_id is not None:
            if self.active_version is None:
                errors.setdefault("active_version", []).append(
                    str(_("Choose an active version from this template family."))
                )
            elif self.active_version.template_id != self.pk or (
                self.active_version.status != ContractTemplateVersion.Status.PUBLISHED
            ):
                errors.setdefault("active_version", []).append(
                    str(_("Active version must be a published version of this family."))
                )

        if self.status == self.Status.ACTIVE and self.active_version_id is None:
            errors.setdefault("active_version", []).append(
                str(_("Active templates must point to an active published version."))
            )
        if self.status == self.Status.RETIRED and self.retired_at is None:
            errors.setdefault("retired_at", []).append(
                str(_("Retired templates must record when they were retired."))
            )

        if errors:
            raise ValidationError(errors)


class ContractTemplateVersion(models.Model):
    """One immutable published (or draft) version of a template family."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        SUPERSEDED = "superseded", _("Superseded")
        RETIRED = "retired", _("Retired")

    template = models.ForeignKey(
        ContractTemplate,
        verbose_name=_("template"),
        related_name="versions",
        on_delete=models.PROTECT,
    )
    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, unique=True, editable=False
    )
    version_label = models.CharField(
        _("version label"),
        max_length=32,
        help_text=_("Semantic version label, e.g. 1.0.0."),
    )
    display_name = models.CharField(_("display name"), max_length=180, blank=True)
    description = models.TextField(_("description"), blank=True)
    source_format = models.CharField(
        _("source format"),
        max_length=16,
        blank=True,
        help_text=_("Allowed values are docx and pdf."),
    )
    source_media_type = models.CharField(
        _("source media type"),
        max_length=120,
        blank=True,
    )
    source_document = models.FileField(
        _("source document"),
        max_length=255,
        storage=private_storage,
        upload_to=_template_source_upload_to,
        blank=True,
        help_text=_("Protected template source file. Never a public URL."),
    )
    source_checksum = models.CharField(
        _("source checksum"),
        max_length=64,
        blank=True,
        help_text=_("SHA-256 hex digest of the uploaded source bytes."),
    )
    merge_schema = models.JSONField(
        _("merge schema"),
        default=list,
        blank=True,
        help_text=_("Allowlisted merge variables and their documented sources."),
    )
    extracted_placeholder_keys = models.JSONField(
        _("extracted placeholder keys"),
        default=list,
        blank=True,
        help_text=_("Placeholder names parsed from the protected source file."),
    )
    preview_pdf = models.FileField(
        _("preview PDF"),
        max_length=255,
        storage=private_storage,
        upload_to=_template_preview_upload_to,
        blank=True,
        help_text=_("Production-path preview output rendered with synthetic data."),
    )
    preview_checksum = models.CharField(
        _("preview checksum"),
        max_length=64,
        blank=True,
        help_text=_("SHA-256 hex digest of the preview PDF bytes."),
    )
    preview_context = models.JSONField(
        _("preview context"),
        default=dict,
        blank=True,
        help_text=_("Synthetic merge values used for the stored preview."),
    )
    preview_generated_at = models.DateTimeField(
        _("preview generated at"), null=True, blank=True
    )
    validation_errors = models.JSONField(
        _("validation errors"),
        default=list,
        blank=True,
        help_text=_("Structured validation failures from the rendering safety pass."),
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    supersedes = models.ForeignKey(
        "self",
        verbose_name=_("supersedes"),
        related_name="superseded_by",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="contract_template_versions_created",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("approved by"),
        related_name="contract_template_versions_approved",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    retired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("retired by"),
        related_name="contract_template_versions_retired",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    retired_at = models.DateTimeField(_("retired at"), null=True, blank=True)

    if TYPE_CHECKING:
        supersedes_id: int | None
        created_by_id: int | None
        approved_by_id: int | None
        retired_by_id: int | None

    class Meta:
        ordering = ["template", "-created_at"]
        verbose_name = _("contract template version")
        verbose_name_plural = _("contract template versions")
        constraints = [
            models.UniqueConstraint(
                fields=["template", "version_label"],
                name="contract_template_version_unique_label",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template.stable_key}@{self.version_label}"

    def _immutable_field_names(self) -> tuple[str, ...]:
        return (
            "template_id",
            "version_label",
            "display_name",
            "description",
            "source_format",
            "source_media_type",
            "source_document",
            "source_checksum",
            "merge_schema",
            "extracted_placeholder_keys",
            "preview_pdf",
            "preview_checksum",
            "preview_context",
            "supersedes_id",
        )

    def clean(self):
        super().clean()
        errors: dict[str, list[str]] = {}

        if self.supersedes_id and self.supersedes_id == self.pk:
            errors.setdefault("supersedes", []).append(
                str(_("A template version cannot supersede itself."))
            )

        if self.source_format and self.source_format not in {"docx", "pdf"}:
            errors.setdefault("source_format", []).append(
                str(_("Source format must be either docx or pdf."))
            )

        if self.source_checksum and (
            len(self.source_checksum) != 64
            or any(ch not in "0123456789abcdef" for ch in self.source_checksum)
        ):
            errors.setdefault("source_checksum", []).append(
                str(_("Source checksum must be a 64-character SHA-256 hex digest."))
            )
        if self.preview_checksum and (
            len(self.preview_checksum) != 64
            or any(ch not in "0123456789abcdef" for ch in self.preview_checksum)
        ):
            errors.setdefault("preview_checksum", []).append(
                str(_("Preview checksum must be a 64-character SHA-256 hex digest."))
            )

        if not isinstance(self.merge_schema, list):
            errors.setdefault("merge_schema", []).append(
                str(_("Merge schema must be a list of variable definitions."))
            )
        else:
            keys: set[str] = set()
            for index, item in enumerate(self.merge_schema):
                if not isinstance(item, dict):
                    errors.setdefault("merge_schema", []).append(
                        str(_("Every merge schema entry must be an object."))
                    )
                    continue
                key = str(item.get("key", "")).strip()
                source = str(item.get("source", "")).strip()
                var_type = str(item.get("type", "")).strip()
                label = str(item.get("label", "")).strip()
                if not key:
                    errors.setdefault("merge_schema", []).append(
                        str(_("Merge schema entry %(index)s is missing a key."))
                        % {"index": index + 1}
                    )
                elif key in keys:
                    errors.setdefault("merge_schema", []).append(
                        str(_("Merge variable %(key)s is declared more than once."))
                        % {"key": key}
                    )
                else:
                    keys.add(key)
                if not source:
                    errors.setdefault("merge_schema", []).append(
                        str(_("Merge variable %(key)s must declare a source."))
                        % {"key": key or f"#{index + 1}"}
                    )
                if not var_type:
                    errors.setdefault("merge_schema", []).append(
                        str(_("Merge variable %(key)s must declare a type."))
                        % {"key": key or f"#{index + 1}"}
                    )
                if not label:
                    errors.setdefault("merge_schema", []).append(
                        str(_("Merge variable %(key)s must declare a label."))
                        % {"key": key or f"#{index + 1}"}
                    )

        if not isinstance(self.extracted_placeholder_keys, list) or any(
            not isinstance(item, str) for item in self.extracted_placeholder_keys
        ):
            errors.setdefault("extracted_placeholder_keys", []).append(
                str(_("Extracted placeholder keys must be a list of strings."))
            )

        if self.status == self.Status.PUBLISHED and self.published_at is None:
            errors.setdefault("published_at", []).append(
                str(_("Published versions must record when they were published."))
            )
        if self.status == self.Status.RETIRED and self.retired_at is None:
            errors.setdefault("retired_at", []).append(
                str(_("Retired versions must record when they were retired."))
            )

        if self.pk:
            original = type(self).objects.filter(pk=self.pk).first()
            if original and original.status == self.Status.PUBLISHED:
                changed = [
                    field
                    for field in self._immutable_field_names()
                    if getattr(original, field) != getattr(self, field)
                ]
                if changed:
                    errors.setdefault("__all__", []).append(
                        str(
                            _(
                                "Published template versions are immutable; create "
                                "a new draft version instead."
                            )
                        )
                    )

        if errors:
            raise ValidationError(errors)


class AgentContractQuerySet(models.QuerySet["AgentContract"]):
    def for_recipient(self, user: User) -> AgentContractQuerySet:
        return self.filter(recipient=user)

    def governing(self) -> AgentContractQuerySet:
        return self.filter(status=ContractStatus.ACTIVE)

    def with_related(self) -> AgentContractQuerySet:
        return self.select_related(
            "recipient",
            "office",
            "office__region",
            "template_version",
            "template_version__template",
            "created_by",
            "generated_pdf",
            "signed_pdf",
        )


class AgentContract(models.Model):
    """One brokerage agreement version for a recipient agent.

    The integer primary key is internal. Clients and audit trails use
    ``public_id``. Commercial history is preserved by creating related rows
    (supersedes / amends / family) rather than mutating signed terms in place.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, unique=True, editable=False
    )
    family_id = models.UUIDField(
        _("family id"),
        default=uuid.uuid4,
        db_index=True,
        help_text=_(
            "Stable identity for the contract family. Amendments and "
            "replacements share this id and increment version_number."
        ),
    )
    version_number = models.PositiveIntegerField(
        _("version number"),
        default=1,
        help_text=_("Monotonic revision within the family. Starts at 1."),
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("recipient agent"),
        related_name="agent_contracts",
        on_delete=models.PROTECT,
    )
    office = models.ForeignKey(
        "user.Office",
        verbose_name=_("owning office"),
        related_name="agent_contracts",
        on_delete=models.PROTECT,
        help_text=_("Office that owns this agreement for scope and mailing."),
    )
    template_version = models.ForeignKey(
        ContractTemplateVersion,
        verbose_name=_("template version"),
        related_name="contracts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("Originating published template version, when chosen."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="agent_contracts_created",
        on_delete=models.PROTECT,
    )
    status = models.CharField(
        _("status"),
        max_length=32,
        choices=ContractStatus.choices,
        default=ContractStatus.DRAFT,
        db_index=True,
    )
    effective_on = models.DateField(_("effective on"))
    expires_on = models.DateField(_("expires on"), null=True, blank=True)

    # --- Commercial terms (explicit Decimal; never float) -----------------
    agent_split_percent = percent_field(verbose_name=_("agent split percent"))
    office_split_percent = percent_field(verbose_name=_("office split percent"))
    transaction_fee_amount = money_field(verbose_name=_("transaction fee amount"))
    transaction_fee_percent = percent_field(verbose_name=_("transaction fee percent"))
    annual_cap_amount = money_field(verbose_name=_("annual cap amount"))

    mentor_percent = percent_field(verbose_name=_("mentor percent"))
    mentor_fixed_amount = money_field(verbose_name=_("mentor fixed amount"))
    mentor_cap_amount = money_field(verbose_name=_("mentor cap amount"))
    mentor_basis = models.CharField(
        _("mentor basis"),
        max_length=32,
        choices=CommissionBasis.choices,
        blank=True,
    )
    mentor_payee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("mentor payee"),
        related_name="mentor_contracts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    mentor_notes = models.CharField(_("mentor notes"), max_length=500, blank=True)

    referral_percent = percent_field(verbose_name=_("referral percent"))
    referral_fixed_amount = money_field(verbose_name=_("referral fixed amount"))
    referral_cap_amount = money_field(verbose_name=_("referral cap amount"))
    referral_basis = models.CharField(
        _("referral basis"),
        max_length=32,
        choices=CommissionBasis.choices,
        blank=True,
    )
    referral_payee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("referral payee"),
        related_name="referral_contracts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    referral_notes = models.CharField(_("referral notes"), max_length=500, blank=True)

    special_arrangements = models.TextField(_("special arrangements"), blank=True)
    addenda_references = models.JSONField(
        _("addenda references"),
        default=list,
        blank=True,
        help_text=_("Ordered list of addendum identifiers or titles."),
    )
    internal_notes = models.TextField(
        _("internal notes"),
        blank=True,
        help_text=_("Broker-only notes. Gated by a separate permission."),
    )

    # --- Immutable issuance snapshots ------------------------------------
    party_snapshot = models.JSONField(_("party snapshot"), default=dict, blank=True)
    office_snapshot = models.JSONField(_("office snapshot"), default=dict, blank=True)
    terms_snapshot = models.JSONField(_("terms snapshot"), default=dict, blank=True)
    calculation_rule_version = models.CharField(
        _("calculation rule version"),
        max_length=16,
        default=CURRENT_RULE_VERSION,
        help_text=_(
            "Commission policy version frozen on this contract. Issued "
            "calculations use this value so later policy bumps do not "
            "silently reinterpret historical terms."
        ),
    )

    # --- Family relationships --------------------------------------------
    root_agreement = models.ForeignKey(
        "self",
        verbose_name=_("root agreement"),
        related_name="family_versions",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("First agreement in the family. Null on the root itself."),
    )
    supersedes = models.ForeignKey(
        "self",
        verbose_name=_("supersedes"),
        related_name="superseded_by_set",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    amends = models.ForeignKey(
        "self",
        verbose_name=_("amends"),
        related_name="amendments",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    # --- Current artifact pointers (private FileField lives on artifact) -
    generated_pdf = models.ForeignKey(
        "ContractArtifact",
        verbose_name=_("generated PDF"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    signed_pdf = models.ForeignKey(
        "ContractArtifact",
        verbose_name=_("signed PDF"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # --- Lifecycle timestamps --------------------------------------------
    viewed_at = models.DateTimeField(_("viewed at"), null=True, blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    signed_at = models.DateTimeField(_("signed at"), null=True, blank=True)
    activated_at = models.DateTimeField(_("activated at"), null=True, blank=True)
    superseded_at = models.DateTimeField(_("superseded at"), null=True, blank=True)
    expired_at = models.DateTimeField(_("expired at"), null=True, blank=True)
    terminated_at = models.DateTimeField(_("terminated at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = AgentContractQuerySet.as_manager()

    if TYPE_CHECKING:
        recipient_id: int
        office_id: int
        created_by_id: int
        template_version_id: int | None
        mentor_payee_id: int | None
        referral_payee_id: int | None
        generated_pdf_id: int | None
        signed_pdf_id: int | None
        root_agreement_id: int | None
        supersedes_id: int | None
        amends_id: int | None

    class Meta:
        ordering = ["-effective_on", "-version_number", "-pk"]
        verbose_name = _("agent contract")
        verbose_name_plural = _("agent contracts")
        default_permissions = ("add", "change", "view")
        permissions = (
            (
                "manage_agent_contracts",
                _("Can manage scoped agent contracts"),
            ),
            (
                "view_commission_terms",
                _("Can view contract commission terms"),
            ),
            (
                "view_internal_notes",
                _("Can view contract internal notes"),
            ),
        )
        constraints = [
            models.UniqueConstraint(
                fields=["family_id", "version_number"],
                name="contract_family_version_unique",
            ),
            models.UniqueConstraint(
                fields=["recipient"],
                condition=Q(status=ContractStatus.ACTIVE),
                name="contract_one_active_per_recipient",
            ),
            models.CheckConstraint(
                condition=Q(expires_on__isnull=True)
                | Q(expires_on__gte=F("effective_on")),
                name="contract_expires_on_or_after_effective",
            ),
            models.CheckConstraint(
                condition=Q(version_number__gte=1),
                name="contract_version_number_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(agent_split_percent__isnull=True)
                    | (
                        Q(agent_split_percent__gte=ZERO)
                        & Q(agent_split_percent__lte=HUNDRED)
                    )
                ),
                name="contract_agent_split_bounds",
            ),
            models.CheckConstraint(
                condition=(
                    Q(office_split_percent__isnull=True)
                    | (
                        Q(office_split_percent__gte=ZERO)
                        & Q(office_split_percent__lte=HUNDRED)
                    )
                ),
                name="contract_office_split_bounds",
            ),
            models.CheckConstraint(
                condition=(
                    Q(transaction_fee_percent__isnull=True)
                    | (
                        Q(transaction_fee_percent__gte=ZERO)
                        & Q(transaction_fee_percent__lte=HUNDRED)
                    )
                ),
                name="contract_txn_fee_percent_bounds",
            ),
            models.CheckConstraint(
                condition=(
                    Q(mentor_percent__isnull=True)
                    | (Q(mentor_percent__gte=ZERO) & Q(mentor_percent__lte=HUNDRED))
                ),
                name="contract_mentor_percent_bounds",
            ),
            models.CheckConstraint(
                condition=(
                    Q(referral_percent__isnull=True)
                    | (Q(referral_percent__gte=ZERO) & Q(referral_percent__lte=HUNDRED))
                ),
                name="contract_referral_percent_bounds",
            ),
            models.CheckConstraint(
                condition=(
                    Q(transaction_fee_amount__isnull=True)
                    | Q(transaction_fee_amount__gte=ZERO)
                ),
                name="contract_txn_fee_amount_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(annual_cap_amount__isnull=True)
                | Q(annual_cap_amount__gte=ZERO),
                name="contract_annual_cap_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(mentor_fixed_amount__isnull=True)
                    | Q(mentor_fixed_amount__gte=ZERO)
                ),
                name="contract_mentor_fixed_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(mentor_cap_amount__isnull=True)
                | Q(mentor_cap_amount__gte=ZERO),
                name="contract_mentor_cap_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(referral_fixed_amount__isnull=True)
                    | Q(referral_fixed_amount__gte=ZERO)
                ),
                name="contract_referral_fixed_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(referral_cap_amount__isnull=True)
                | Q(referral_cap_amount__gte=ZERO),
                name="contract_referral_cap_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        agent_split_percent__isnull=True,
                        office_split_percent__isnull=True,
                    )
                    | Q(
                        agent_split_percent__isnull=False,
                        office_split_percent__isnull=False,
                    )
                ),
                name="contract_splits_both_or_neither",
            ),
        ]
        indexes = [
            models.Index(
                fields=["recipient", "status"],
                name="contract_recipient_status",
            ),
            models.Index(
                fields=["office", "status"],
                name="contract_office_status",
            ),
            models.Index(
                fields=["status", "-effective_on"],
                name="contract_status_effective",
            ),
            models.Index(
                fields=["family_id", "version_number"],
                name="contract_family_version_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.public_id} ({self.status})"

    def clean(self):
        super().clean()
        errors: dict[str, list[str]] = {}

        if (
            self.expires_on
            and self.effective_on
            and self.expires_on < self.effective_on
        ):
            errors.setdefault("expires_on", []).append(
                str(_("Expiration cannot be earlier than the effective date."))
            )

        try:
            self.agent_split_percent = quantize_percent(self.agent_split_percent)
            self.office_split_percent = quantize_percent(self.office_split_percent)
            self.transaction_fee_percent = quantize_percent(
                self.transaction_fee_percent
            )
            self.mentor_percent = quantize_percent(self.mentor_percent)
            self.referral_percent = quantize_percent(self.referral_percent)
        except ValidationError as exc:
            errors.setdefault("agent_split_percent", []).extend(exc.messages)

        for field in (
            "transaction_fee_amount",
            "annual_cap_amount",
            "mentor_fixed_amount",
            "mentor_cap_amount",
            "referral_fixed_amount",
            "referral_cap_amount",
        ):
            try:
                setattr(self, field, quantize_money(getattr(self, field)))
            except ValidationError as exc:
                errors.setdefault(field, []).extend(exc.messages)

        agent = self.agent_split_percent
        office = self.office_split_percent
        if agent is not None and office is not None and agent + office != HUNDRED:
            errors.setdefault("agent_split_percent", []).append(
                str(_("Agent and office splits must sum to 100 percent."))
            )
            errors.setdefault("office_split_percent", []).append(
                str(_("Agent and office splits must sum to 100 percent."))
            )
        elif (agent is None) ^ (office is None):
            errors.setdefault("agent_split_percent", []).append(
                str(_("Agent and office splits must both be set or both omitted."))
            )

        if self.mentor_percent is not None or self.mentor_fixed_amount is not None:
            if not self.mentor_basis:
                errors.setdefault("mentor_basis", []).append(
                    str(_("Mentor terms require a calculation basis."))
                )
            if self.mentor_payee_id is None:
                errors.setdefault("mentor_payee", []).append(
                    str(_("Mentor terms require a payee."))
                )
        if self.referral_percent is not None or self.referral_fixed_amount is not None:
            if not self.referral_basis:
                errors.setdefault("referral_basis", []).append(
                    str(_("Referral terms require a calculation basis."))
                )
            if self.referral_payee_id is None:
                errors.setdefault("referral_payee", []).append(
                    str(_("Referral terms require a payee."))
                )
        if (
            self.mentor_basis == CommissionBasis.FIXED_ONLY
            and self.mentor_percent is not None
        ):
            errors.setdefault("mentor_percent", []).append(
                str(_("fixed_only basis cannot include a percentage."))
            )
        if (
            self.referral_basis == CommissionBasis.FIXED_ONLY
            and self.referral_percent is not None
        ):
            errors.setdefault("referral_percent", []).append(
                str(_("fixed_only basis cannot include a percentage."))
            )

        if not isinstance(self.addenda_references, list):
            errors.setdefault("addenda_references", []).append(
                str(_("Addenda references must be a list."))
            )
        elif any(not isinstance(item, str) for item in self.addenda_references):
            errors.setdefault("addenda_references", []).append(
                str(_("Each addendum reference must be a string."))
            )

        if self.root_agreement_id and self.root_agreement_id == self.pk:
            errors.setdefault("root_agreement", []).append(
                str(_("A contract cannot be its own root agreement."))
            )
        if self.supersedes_id and self.supersedes_id == self.pk:
            errors.setdefault("supersedes", []).append(
                str(_("A contract cannot supersede itself."))
            )
        if self.amends_id and self.amends_id == self.pk:
            errors.setdefault("amends", []).append(
                str(_("A contract cannot amend itself."))
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Refuse unguarded status mutations outside the lifecycle service."""
        if self.pk:
            from apps.contract.lifecycle import status_write_allowed

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
                            "Contract status may only change through the "
                            "lifecycle transition service."
                        )
                    }
                )
        super().save(*args, **kwargs)


class ContractArtifact(models.Model):
    """Protected file belonging to a contract — generated PDF, signed PDF, etc.

    Bytes live in private storage. The only supported read path is an
    authorized view that re-checks recipient/admin scope. Checksums make
    silent storage drift detectable.
    """

    class Kind(models.TextChoices):
        GENERATED_PDF = "generated_pdf", _("Generated PDF")
        SIGNED_PDF = "signed_pdf", _("Signed PDF")
        ADDENDUM = "addendum", _("Addendum")
        OTHER = "other", _("Other")

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, unique=True, editable=False
    )
    contract = models.ForeignKey(
        AgentContract,
        verbose_name=_("contract"),
        related_name="artifacts",
        on_delete=models.PROTECT,
    )
    kind = models.CharField(_("kind"), max_length=32, choices=Kind.choices)
    display_name = models.CharField(
        _("display name"),
        max_length=180,
        help_text=_("Human-facing filename. Never a storage path or public URL."),
    )
    file = models.FileField(
        _("file"),
        max_length=255,
        storage=private_storage,
        upload_to=_artifact_upload_to,
        help_text=_("Protected storage reference. Not a public URL."),
    )
    media_type = models.CharField(_("media type"), max_length=120)
    byte_size = models.PositiveBigIntegerField(_("size in bytes"))
    checksum = models.CharField(
        _("checksum"),
        max_length=64,
        help_text=_("SHA-256 hex digest of the stored bytes."),
    )
    renderer_version = models.CharField(
        _("renderer version"),
        max_length=32,
        blank=True,
        help_text=_("PDF renderer/pipeline version that produced this artifact."),
    )
    rule_version = models.CharField(
        _("calculation rule version"),
        max_length=32,
        blank=True,
        help_text=_("Frozen calculation rule version at generation time."),
    )
    input_fingerprint = models.CharField(
        _("input fingerprint"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_(
            "SHA-256 of frozen snapshots + template source + renderer version. "
            "Used for idempotent retries."
        ),
    )
    generation_metadata = models.JSONField(
        _("generation metadata"),
        default=dict,
        blank=True,
        help_text=_("Page count, validated markers, and other non-PII render facts."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="contract_artifacts_created",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    if TYPE_CHECKING:
        contract_id: int
        created_by_id: int | None

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("contract artifact")
        verbose_name_plural = _("contract artifacts")
        constraints = [
            models.CheckConstraint(
                condition=Q(byte_size__gt=0),
                name="contract_artifact_has_bytes",
            ),
        ]
        indexes = [
            models.Index(
                fields=["contract", "kind"],
                name="contract_artifact_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.display_name}"

    def clean(self):
        super().clean()
        if self.byte_size is not None and self.byte_size <= 0:
            raise ValidationError(
                {"byte_size": _("Artifact byte size must be positive.")}
            )
        if self.checksum and (
            len(self.checksum) != 64
            or any(ch not in "0123456789abcdef" for ch in self.checksum)
        ):
            raise ValidationError(
                {"checksum": _("Checksum must be a 64-character SHA-256 hex digest.")}
            )
        if self.input_fingerprint and (
            len(self.input_fingerprint) != 64
            or any(ch not in "0123456789abcdef" for ch in self.input_fingerprint)
        ):
            raise ValidationError(
                {
                    "input_fingerprint": _(
                        "Input fingerprint must be a 64-character SHA-256 hex digest."
                    )
                }
            )
        if self.generation_metadata is None or not isinstance(
            self.generation_metadata, dict
        ):
            raise ValidationError(
                {"generation_metadata": _("Generation metadata must be an object.")}
            )


def _required_money(**kwargs):
    """Non-null USD money field for persisted calculation results."""
    return models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=_("US dollars with cents. Currency: USD. Nonnegative."),
        **kwargs,
    )


class CommissionCalculation(models.Model):
    """Persisted, explainable outcome of one mentor/referral commission run.

    Core math lives in :mod:`apps.contract.calculations`. This row freezes the
    rule version, input, terms, intermediates, results, and explanation so a
    later policy change cannot reinterpret issued figures.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, unique=True, editable=False
    )
    contract = models.ForeignKey(
        AgentContract,
        verbose_name=_("contract"),
        related_name="commission_calculations",
        on_delete=models.PROTECT,
    )
    rule_version = models.CharField(_("rule version"), max_length=16)
    currency = models.CharField(_("currency"), max_length=3, default="USD")
    fingerprint = models.CharField(
        _("fingerprint"),
        max_length=64,
        db_index=True,
        help_text=_(
            "SHA-256 of rule version + input + terms snapshots. Identical "
            "requests reuse the same row (idempotent)."
        ),
    )
    input_snapshot = models.JSONField(_("input snapshot"), default=dict)
    terms_snapshot = models.JSONField(_("terms snapshot"), default=dict)
    intermediate_snapshot = models.JSONField(_("intermediate snapshot"), default=dict)
    result_snapshot = models.JSONField(_("result snapshot"), default=dict)
    explanation = models.JSONField(
        _("explanation"),
        default=list,
        help_text=_(
            "Ordered human-readable lines; mentor and referral labeled separately."
        ),
    )
    mentor_amount = _required_money(verbose_name=_("mentor amount"))
    referral_amount = _required_money(verbose_name=_("referral amount"))
    agent_net_amount = _required_money(verbose_name=_("agent net amount"))
    office_net_amount = _required_money(verbose_name=_("office net amount"))
    transaction_fee_amount = _required_money(verbose_name=_("transaction fee amount"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="commission_calculations_created",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    if TYPE_CHECKING:
        contract_id: int
        created_by_id: int | None

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("commission calculation")
        verbose_name_plural = _("commission calculations")
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "fingerprint"],
                name="contract_calculation_idempotent",
            ),
        ]
        indexes = [
            models.Index(
                fields=["contract", "-created_at"],
                name="contract_calc_contract_time",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.public_id}@{self.rule_version}"
