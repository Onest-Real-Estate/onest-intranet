"""Read-only Django admin registration for ops debugging.

Product workflows for contract creation, signing, and lifecycle live outside
Django admin. These registrations exist so support can inspect rows without
treating admin as the authoring surface.
"""

from django.contrib import admin

from apps.contract.models import (
    AgentContract,
    CommissionCalculation,
    ContractArtifact,
    ContractSignature,
    ContractSigningIntent,
    ContractTemplate,
    ContractTemplateVersion,
)


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "stable_key", "status", "updated_at")
    search_fields = ("name", "stable_key")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(ContractTemplateVersion)
class ContractTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version_label", "status", "published_at")
    list_filter = ("status",)
    search_fields = ("template__stable_key", "version_label")
    readonly_fields = ("public_id", "created_at")


class ContractArtifactInline(admin.TabularInline):
    model = ContractArtifact
    extra = 0
    readonly_fields = (
        "public_id",
        "kind",
        "display_name",
        "media_type",
        "byte_size",
        "checksum",
        "renderer_version",
        "rule_version",
        "input_fingerprint",
        "generation_metadata",
        "created_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AgentContract)
class AgentContractAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "recipient",
        "office",
        "status",
        "change_kind",
        "effective_on",
        "version_number",
    )
    list_filter = ("status", "change_kind")
    search_fields = (
        "public_id",
        "recipient__email",
        "recipient__display_name",
        "office__name",
    )
    readonly_fields = (
        "public_id",
        "family_id",
        "change_kind",
        "change_summary",
        "status",
        "party_snapshot",
        "office_snapshot",
        "terms_snapshot",
        "calculation_rule_version",
        "created_at",
        "updated_at",
        "viewed_at",
        "sent_at",
        "signed_at",
        "activated_at",
        "superseded_at",
        "expired_at",
        "terminated_at",
    )
    inlines = [ContractArtifactInline]
    autocomplete_fields = ("recipient", "office", "created_by", "template_version")

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        # Status and lifecycle stamps are always read-only; product transitions
        # go through apps.contract.lifecycle, not Django admin field edits.
        return self.readonly_fields


@admin.register(ContractArtifact)
class ContractArtifactAdmin(admin.ModelAdmin):
    list_display = ("display_name", "kind", "contract", "byte_size", "created_at")
    list_filter = ("kind",)
    search_fields = ("public_id", "display_name", "checksum")
    readonly_fields = (
        "public_id",
        "checksum",
        "byte_size",
        "renderer_version",
        "rule_version",
        "input_fingerprint",
        "generation_metadata",
        "created_at",
    )


@admin.register(CommissionCalculation)
class CommissionCalculationAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "contract",
        "rule_version",
        "mentor_amount",
        "referral_amount",
        "agent_net_amount",
        "created_at",
    )
    list_filter = ("rule_version", "currency")
    search_fields = ("public_id", "fingerprint", "contract__public_id")
    readonly_fields = (
        "public_id",
        "contract",
        "rule_version",
        "currency",
        "fingerprint",
        "input_snapshot",
        "terms_snapshot",
        "intermediate_snapshot",
        "result_snapshot",
        "explanation",
        "mentor_amount",
        "referral_amount",
        "agent_net_amount",
        "office_net_amount",
        "transaction_fee_amount",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ContractSigningIntent)
class ContractSigningIntentAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "contract",
        "actor",
        "status",
        "docuseal_submission_id",
        "expires_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("public_id", "docuseal_submission_id", "actor__email")
    readonly_fields = (
        "public_id",
        "contract",
        "actor",
        "contract_version",
        "artifact",
        "artifact_checksum",
        "session_key_hash",
        "request_ip_hash",
        "request_ua_hash",
        "disclosure_version",
        "consent_accepted_at",
        "status",
        "docuseal_submission_id",
        "docuseal_submitter_slug",
        "embed_src",
        "expires_at",
        "created_at",
        "consumed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ContractSignature)
class ContractSignatureAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "contract",
        "signer",
        "signature_method",
        "disclosure_version",
        "signed_at",
    )
    search_fields = ("public_id", "signer__email", "docuseal_submission_id")
    readonly_fields = (
        "public_id",
        "contract",
        "intent",
        "signer",
        "artifact",
        "signed_at",
        "disclosure_version",
        "signature_method",
        "docuseal_submission_id",
        "docuseal_submitter_slug",
        "request_ip_hash",
        "request_ua_hash",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
