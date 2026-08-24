"""Agent Contract query and draft-creation services.

Scope is applied on the queryset from the actor's effective access — never from
a client-supplied office or recipient id. Field-level commission and internal
note visibility is a separate grant from general contract metadata.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.calculations.rules import CURRENT_RULE_VERSION
from apps.contract.models import (
    AgentContract,
    ContractArtifact,
    ContractTemplateVersion,
)
from apps.contract.permissions import (
    MANAGE_AGENT_CONTRACTS,
    VIEW_AGENT_CONTRACTS,
    VIEW_COMMISSION_TERMS,
    VIEW_INTERNAL_NOTES,
    VIEW_OWN_COMMISSION,
)
from apps.contract.snapshots import (
    office_snapshot,
    party_snapshot,
    terms_snapshot_from_contract,
)
from apps.contract.statuses import (
    ContractStatus,
    contract_status_options,
    status_label,
    status_tone,
)
from apps.contract.terms import quantize_money, quantize_percent
from apps.user.administration_fields import ACTIVE as ACTIVE_AGENT_STATUS
from apps.user.models import Office, User
from apps.user.services.agent_administration import (
    AdministrationScope,
    administration_scope,
    is_user_in_scope,
)
from apps.user.services.role_assignments import has_effective_permission


def _office_in_scope(office: Office | None, scope: AdministrationScope) -> bool:
    if scope.company_wide:
        return True
    if office is None:
        return False
    if office.stable_key in scope.office_keys:
        return True
    if office.stable_key in scope.region_keys:
        return True
    region = office.region
    return region is not None and region.stable_key in scope.region_keys


# Re-export for apps.user.services.user_directory / agent_administration.
__all__ = [
    "agent_contract_status",
    "attach_artifact",
    "bulk_agent_onboarding_states",
    "contract_status_options",
    "create_draft_contract",
    "recipient_contract_queryset",
    "scoped_contract_queryset",
    "serialize_contract",
]


def scoped_contract_queryset(actor: User) -> QuerySet[AgentContract]:
    """Contracts an administrator may see, filtered on the database.

    Requires ``web.view_agent_contracts`` or ``contract.manage_agent_contracts``.
    Superusers see everything. Empty scope yields an empty queryset.
    """
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, VIEW_AGENT_CONTRACTS)
        or has_effective_permission(actor, MANAGE_AGENT_CONTRACTS)
    ):
        return AgentContract.objects.none()

    queryset = AgentContract.objects.with_related().all()
    if getattr(actor, "is_superuser", False):
        return queryset

    scope = administration_scope(actor)
    if scope.company_wide:
        return queryset
    if scope.is_empty:
        return queryset.none()

    filters = Q()
    if scope.office_keys:
        filters |= Q(office__stable_key__in=sorted(scope.office_keys))
    if scope.region_keys:
        keys = sorted(scope.region_keys)
        filters |= Q(office__region__stable_key__in=keys) | Q(
            office__stable_key__in=keys
        )
    return queryset.filter(filters)


def recipient_contract_queryset(user: User) -> QuerySet[AgentContract]:
    """Self-only contracts for the signed-in agent."""
    return AgentContract.objects.with_related().for_recipient(user)


def accessible_contract_queryset(actor: User) -> QuerySet[AgentContract]:
    """Union of self contracts and scoped admin contracts."""
    own = recipient_contract_queryset(actor)
    admin = scoped_contract_queryset(actor)
    return AgentContract.objects.filter(
        Q(pk__in=own.values("pk")) | Q(pk__in=admin.values("pk"))
    ).with_related()


def agent_contract_status(user: User) -> dict[str, Any]:
    """Standing summary consumed by agent administration and the directory."""
    contract = (
        AgentContract.objects.filter(recipient=user)
        .exclude(status=ContractStatus.DRAFT)
        .order_by(
            # Prefer governing, then newest non-draft.
            models_order_priority(),
            "-effective_on",
            "-version_number",
            "-pk",
        )
        .first()
    )
    if contract is None:
        draft = (
            AgentContract.objects.filter(recipient=user, status=ContractStatus.DRAFT)
            .order_by("-updated_at", "-pk")
            .first()
        )
        if draft is None:
            return {
                "status": None,
                "label": "No contract",
                "tone": "neutral",
                "source": "contract",
                "available": True,
                "reason": "",
                "publicId": None,
            }
        contract = draft

    return {
        "status": contract.status,
        "label": status_label(contract.status),
        "tone": status_tone(contract.status),
        "source": "contract",
        "available": True,
        "reason": "",
        "publicId": str(contract.public_id),
    }


def bulk_agent_onboarding_states(users: list[User]):
    """Onboarding milestones for many agents in a fixed query budget.

    Returns ``ContractOnboardingState`` values keyed by user pk. One query loads
    every candidate contract for the batch; milestone status is derived in
    memory so list pages never N+1 the contract table.
    """
    from apps.user.services.onboarding_state import (
        ContractOnboardingState,
    )

    user_ids = [user.pk for user in users]
    if not user_ids:
        return {}

    contracts = list(
        AgentContract.objects.filter(recipient_id__in=user_ids).order_by(
            "recipient_id",
            models_order_priority(),
            "-effective_on",
            "-version_number",
            "-pk",
        )
    )
    by_recipient: dict[int, AgentContract] = {}
    for contract in contracts:
        by_recipient.setdefault(contract.recipient_id, contract)

    result: dict[int, ContractOnboardingState] = {}
    for user in users:
        result[user.pk] = _onboarding_state_for_contract(by_recipient.get(user.pk))
    return result


def _onboarding_state_for_contract(contract: AgentContract | None):
    from apps.user.services.onboarding_state import (
        ContractOnboardingState,
        MilestoneStatus,
        SourceMilestone,
    )

    generated_done = False
    signed_done = False
    active_done = False
    blocked = False
    detail = "No agent contract has been created yet."
    updated_at = None

    if contract is not None:
        updated_at = contract.updated_at
        detail = f"Contract status: {status_label(contract.status)}."
        if contract.status == ContractStatus.GENERATION_ERROR:
            blocked = True
            detail = "Contract PDF generation failed and needs attention."
        generated_done = contract.generated_pdf_id is not None or contract.status in {
            ContractStatus.SENT,
            ContractStatus.VIEWED,
            ContractStatus.SIGNED,
            ContractStatus.ACTIVE,
            ContractStatus.SUPERSEDED,
            ContractStatus.EXPIRED,
            ContractStatus.TERMINATED,
        }
        signed_done = contract.signed_at is not None or contract.status in {
            ContractStatus.SIGNED,
            ContractStatus.ACTIVE,
            ContractStatus.SUPERSEDED,
        }
        active_done = contract.status == ContractStatus.ACTIVE

    def milestone(key: str, label: str, done: bool) -> SourceMilestone:
        if blocked and not done:
            status = MilestoneStatus.BLOCKED
        elif done:
            status = MilestoneStatus.COMPLETE
        else:
            status = MilestoneStatus.PENDING
        return SourceMilestone(
            key=key,
            label=label,
            status=status,
            source="contract",
            detail=detail,
            updated_at=updated_at,
        )

    generated = milestone("contract_generated", "Contract generated", generated_done)
    signed = milestone("contract_signed", "Contract signed", signed_done)
    active = milestone("contract_active", "Contract active", active_done)
    if blocked:
        overall = MilestoneStatus.BLOCKED
    elif active_done:
        overall = MilestoneStatus.COMPLETE
    else:
        overall = MilestoneStatus.PENDING
    return ContractOnboardingState(
        status=overall,
        generated=generated,
        signed=signed,
        active=active,
    )


def models_order_priority():
    from django.db.models import Case, IntegerField, Value, When

    return Case(
        When(status=ContractStatus.ACTIVE, then=Value(0)),
        When(status=ContractStatus.SIGNED, then=Value(1)),
        When(status=ContractStatus.VIEWED, then=Value(2)),
        When(status=ContractStatus.SENT, then=Value(3)),
        When(status=ContractStatus.READY_FOR_REVIEW, then=Value(4)),
        When(status=ContractStatus.GENERATION_ERROR, then=Value(5)),
        When(status=ContractStatus.DRAFT, then=Value(6)),
        default=Value(7),
        output_field=IntegerField(),
    )


def _can_view_commission(viewer: User, contract: AgentContract) -> bool:
    if getattr(viewer, "is_superuser", False):
        return True
    if has_effective_permission(viewer, VIEW_COMMISSION_TERMS):
        return True
    return contract.recipient_id == viewer.pk and has_effective_permission(
        viewer, VIEW_OWN_COMMISSION
    )


def _can_view_internal_notes(viewer: User) -> bool:
    if getattr(viewer, "is_superuser", False):
        return True
    return has_effective_permission(viewer, VIEW_INTERNAL_NOTES)


def serialize_contract(viewer: User, contract: AgentContract) -> dict[str, Any]:
    """CamelCase payload with permission-gated commission and notes keys.

    Keys the viewer may not read are **omitted**, never null — same convention
    as agent administration field groups.
    """
    payload: dict[str, Any] = {
        "publicId": str(contract.public_id),
        "familyId": str(contract.family_id),
        "versionNumber": contract.version_number,
        "status": contract.status,
        "statusLabel": status_label(contract.status),
        "statusTone": status_tone(contract.status),
        "effectiveOn": contract.effective_on.isoformat(),
        "expiresOn": (contract.expires_on.isoformat() if contract.expires_on else None),
        "recipientId": contract.recipient_id,
        "officeId": contract.office_id,
        "templateVersionId": contract.template_version_id,
        "createdById": contract.created_by_id,
        "partySnapshot": contract.party_snapshot,
        "officeSnapshot": contract.office_snapshot,
        "viewedAt": _dt(contract.viewed_at),
        "sentAt": _dt(contract.sent_at),
        "signedAt": _dt(contract.signed_at),
        "activatedAt": _dt(contract.activated_at),
        "supersededAt": _dt(contract.superseded_at),
        "expiredAt": _dt(contract.expired_at),
        "terminatedAt": _dt(contract.terminated_at),
        "createdAt": _dt(contract.created_at),
        "updatedAt": _dt(contract.updated_at),
        "generatedPdf": _artifact_meta(contract.generated_pdf),
        "signedPdf": _artifact_meta(contract.signed_pdf),
        "rootAgreementId": contract.root_agreement_id,
        "supersedesId": contract.supersedes_id,
        "amendsId": contract.amends_id,
    }
    if _can_view_commission(viewer, contract):
        payload["termsSnapshot"] = contract.terms_snapshot
        payload["commission"] = {
            "agentSplitPercent": _dec(contract.agent_split_percent),
            "officeSplitPercent": _dec(contract.office_split_percent),
            "transactionFeeAmount": _dec(contract.transaction_fee_amount),
            "transactionFeePercent": _dec(contract.transaction_fee_percent),
            "annualCapAmount": _dec(contract.annual_cap_amount),
            "specialArrangements": contract.special_arrangements,
            "addendaReferences": list(contract.addenda_references or []),
            "mentor": {
                "percent": _dec(contract.mentor_percent),
                "fixedAmount": _dec(contract.mentor_fixed_amount),
                "capAmount": _dec(contract.mentor_cap_amount),
                "basis": contract.mentor_basis,
                "payeeId": contract.mentor_payee_id,
                "notes": contract.mentor_notes,
            },
            "referral": {
                "percent": _dec(contract.referral_percent),
                "fixedAmount": _dec(contract.referral_fixed_amount),
                "capAmount": _dec(contract.referral_cap_amount),
                "basis": contract.referral_basis,
                "payeeId": contract.referral_payee_id,
                "notes": contract.referral_notes,
            },
        }
    if _can_view_internal_notes(viewer):
        payload["internalNotes"] = contract.internal_notes
    return payload


def _dt(value) -> str | None:
    return value.isoformat() if value is not None else None


def _dec(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _artifact_meta(artifact: ContractArtifact | None) -> dict[str, Any] | None:
    if artifact is None:
        return None
    return {
        "publicId": str(artifact.public_id),
        "kind": artifact.kind,
        "displayName": artifact.display_name,
        "mediaType": artifact.media_type,
        "byteSize": artifact.byte_size,
        "checksum": artifact.checksum,
        # Deliberately no URL — downloads go through an authorized view.
    }


def _ensure_manage(actor: User) -> None:
    if getattr(actor, "is_superuser", False):
        return
    if not has_effective_permission(actor, MANAGE_AGENT_CONTRACTS):
        raise PermissionDenied(_("You cannot manage agent contracts."))


def create_draft_contract(
    actor: User,
    *,
    recipient: User,
    office: Office | None = None,
    effective_on: date,
    expires_on: date | None = None,
    template_version: ContractTemplateVersion | None = None,
    agent_split_percent: Decimal | str | None = None,
    office_split_percent: Decimal | str | None = None,
    transaction_fee_amount: Decimal | str | None = None,
    transaction_fee_percent: Decimal | str | None = None,
    annual_cap_amount: Decimal | str | None = None,
    mentor_percent: Decimal | str | None = None,
    mentor_fixed_amount: Decimal | str | None = None,
    mentor_cap_amount: Decimal | str | None = None,
    mentor_basis: str = "",
    mentor_payee: User | None = None,
    mentor_notes: str = "",
    referral_percent: Decimal | str | None = None,
    referral_fixed_amount: Decimal | str | None = None,
    referral_cap_amount: Decimal | str | None = None,
    referral_basis: str = "",
    referral_payee: User | None = None,
    referral_notes: str = "",
    special_arrangements: str = "",
    addenda_references: list[str] | None = None,
    internal_notes: str = "",
    supersedes: AgentContract | None = None,
    amends: AgentContract | None = None,
    root_agreement: AgentContract | None = None,
) -> AgentContract:
    """Create a validated draft for an active in-scope agent and office."""
    _ensure_manage(actor)

    if not recipient.is_active:
        raise ValidationError({"recipient": _("Recipient account is inactive.")})
    if recipient.agent_status != ACTIVE_AGENT_STATUS:
        raise ValidationError(
            {"recipient": _("Draft contracts require an active agent status.")}
        )

    owning_office = office or recipient.office
    if owning_office is None:
        raise ValidationError(
            {"office": _("Recipient has no office; choose an owning office.")}
        )
    if not owning_office.is_active:
        raise ValidationError({"office": _("Owning office is inactive.")})
    if not owning_office.is_assignable:
        raise ValidationError(
            {"office": _("Owning office cannot be assigned contracts.")}
        )

    if not is_user_in_scope(actor, recipient):
        raise ValidationError(
            {"recipient": _("Recipient is outside your administrative scope.")}
        )
    scope = administration_scope(actor)
    if not _office_in_scope(owning_office, scope):
        raise ValidationError(
            {"office": _("Owning office is outside your administrative scope.")}
        )

    if (
        template_version is not None
        and template_version.status != ContractTemplateVersion.Status.PUBLISHED
    ):
        raise ValidationError(
            {
                "template_version": _(
                    "Only published template versions can originate a contract."
                )
            }
        )
    if template_version is not None:
        from apps.contract.administration import assert_template_applicable

        assert_template_applicable(
            template_version, office=owning_office, effective_on=effective_on
        )

    contract = AgentContract(
        recipient=recipient,
        office=owning_office,
        template_version=template_version,
        created_by=actor,
        status=ContractStatus.DRAFT,
        effective_on=effective_on,
        expires_on=expires_on,
        agent_split_percent=quantize_percent(agent_split_percent),
        office_split_percent=quantize_percent(office_split_percent),
        transaction_fee_amount=quantize_money(transaction_fee_amount),
        transaction_fee_percent=quantize_percent(transaction_fee_percent),
        annual_cap_amount=quantize_money(annual_cap_amount),
        mentor_percent=quantize_percent(mentor_percent),
        mentor_fixed_amount=quantize_money(mentor_fixed_amount),
        mentor_cap_amount=quantize_money(mentor_cap_amount),
        mentor_basis=mentor_basis or "",
        mentor_payee=mentor_payee,
        mentor_notes=mentor_notes or "",
        referral_percent=quantize_percent(referral_percent),
        referral_fixed_amount=quantize_money(referral_fixed_amount),
        referral_cap_amount=quantize_money(referral_cap_amount),
        referral_basis=referral_basis or "",
        referral_payee=referral_payee,
        referral_notes=referral_notes or "",
        special_arrangements=special_arrangements or "",
        addenda_references=list(addenda_references or []),
        internal_notes=internal_notes or "",
        supersedes=supersedes,
        amends=amends,
        root_agreement=root_agreement,
        calculation_rule_version=CURRENT_RULE_VERSION,
    )
    if root_agreement is not None:
        contract.family_id = root_agreement.family_id
        contract.version_number = (
            AgentContract.objects.filter(family_id=root_agreement.family_id)
            .order_by("-version_number")
            .values_list("version_number", flat=True)
            .first()
            or 0
        ) + 1

    contract.party_snapshot = party_snapshot(recipient)
    contract.office_snapshot = office_snapshot(owning_office)
    # terms_snapshot filled after clean so quantized values are frozen.
    contract.full_clean()
    contract.terms_snapshot = terms_snapshot_from_contract(contract)

    with transaction.atomic():
        contract.save()
        log_event(
            "contract.draft.created",
            actor=actor_from_user(actor),
            target=AuditTarget(
                target_type=AgentContract._meta.label_lower,
                target_id=str(contract.public_id),
                target_label=recipient.email,
                target_snapshot={
                    "status": contract.status,
                    "recipient_id": recipient.pk,
                    "office_id": owning_office.pk,
                },
            ),
            outcome=AuditEvent.Outcome.SUCCESS,
            source="service",
            channel="contract",
            office_id=owning_office.stable_key,
        )
    return contract


def attach_artifact(
    actor: User,
    contract: AgentContract,
    *,
    kind: str,
    file,
    display_name: str,
    media_type: str,
    byte_size: int,
    checksum: str,
) -> ContractArtifact:
    """Attach a protected artifact with checksum metadata (no public URL)."""
    _ensure_manage(actor)
    if (
        not getattr(actor, "is_superuser", False)
        and not scoped_contract_queryset(actor).filter(pk=contract.pk).exists()
    ):
        raise PermissionDenied(_("Contract is outside your scope."))

    artifact = ContractArtifact(
        contract=contract,
        kind=kind,
        display_name=display_name,
        file=file,
        media_type=media_type,
        byte_size=byte_size,
        checksum=checksum.lower(),
        created_by=actor,
    )
    artifact.full_clean()
    artifact.save()

    update_fields: list[str] = []
    if kind == ContractArtifact.Kind.GENERATED_PDF:
        contract.generated_pdf = artifact
        update_fields.append("generated_pdf")
    elif kind == ContractArtifact.Kind.SIGNED_PDF:
        contract.signed_pdf = artifact
        update_fields.append("signed_pdf")
    if update_fields:
        update_fields.append("updated_at")
        contract.save(update_fields=update_fields)
    return artifact
