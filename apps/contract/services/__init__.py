"""Agent Contract query and draft-creation services.

Scope is applied on the queryset from the actor's effective access — never from
a client-supplied office or recipient id. Field-level commission and internal
note visibility is a separate grant from general contract metadata.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.calculations.rules import CURRENT_RULE_VERSION
from apps.contract.change_kinds import ContractChangeKind, change_kind_label
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
    "initiate_onboarding_contract",
    "recipient_contract_queryset",
    "scoped_contract_queryset",
    "serialize_contract",
]


class OnboardingContractAction(StrEnum):
    INITIATE = "initiate_contract"
    OPEN = "open_contract"


def onboarding_workspace_capability(
    *, actor: User, user: User, public_id: str | None, required_setup_complete: bool
) -> dict[str, Any]:
    """Source-owned action contract for the New Agent workspace."""
    may_manage = bool(
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, MANAGE_AGENT_CONTRACTS)
    )
    if public_id:
        may_view = may_manage or has_effective_permission(actor, VIEW_AGENT_CONTRACTS)
        return {
            "code": str(OnboardingContractAction.OPEN),
            "label": "Open contract workspace",
            "method": "get",
            "href": reverse("agent_contract_workspace", args=[public_id]),
            "enabled": may_view,
            "unavailableReason": (
                "" if may_view else "You do not have permission to view contracts."
            ),
            "permission": VIEW_AGENT_CONTRACTS,
        }
    unavailable_reason = ""
    if not may_manage:
        unavailable_reason = "You do not have permission to manage contracts."
    elif not required_setup_complete:
        unavailable_reason = (
            "Wait until the agent completes their profile and confirms their office."
        )
    return {
        "code": str(OnboardingContractAction.INITIATE),
        "label": "Initiate agent contract",
        "method": "post",
        "href": None,
        "enabled": not unavailable_reason,
        "unavailableReason": unavailable_reason,
        "permission": MANAGE_AGENT_CONTRACTS,
    }


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
        ContractJourneyStatus,
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
        generated_done = contract.generated_pdf_id is not None
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
    if blocked:
        journey_status = ContractJourneyStatus.BLOCKED
    elif active_done:
        journey_status = ContractJourneyStatus.ACTIVE
    elif signed_done:
        journey_status = ContractJourneyStatus.SIGNED
    elif contract is not None and contract.status in {
        ContractStatus.SENT,
        ContractStatus.VIEWED,
    }:
        journey_status = ContractJourneyStatus.SENT
    elif generated_done:
        journey_status = ContractJourneyStatus.GENERATED
    elif contract is None:
        # The source answered and there is simply nothing yet. ``UNAVAILABLE``
        # is reserved for a source that could not answer at all, so the agent's
        # own surface can say "waiting for your office" instead of implying a
        # broken integration.
        journey_status = ContractJourneyStatus.NOT_STARTED
    else:
        journey_status = ContractJourneyStatus.UNAVAILABLE
    return ContractOnboardingState(
        status=overall,
        journey_status=journey_status,
        generated=generated,
        signed=signed,
        active=active,
        public_id=str(contract.public_id) if contract is not None else None,
    )


def models_order_priority():
    from django.db.models import Case, IntegerField, Value, When

    return Case(
        When(status=ContractStatus.ACTIVE, then=Value(0)),
        When(status=ContractStatus.SIGNED, then=Value(1)),
        When(status=ContractStatus.VIEWED, then=Value(2)),
        When(status=ContractStatus.SENT, then=Value(3)),
        When(status=ContractStatus.AWAITING_COMPANY_SIGNATURE, then=Value(4)),
        When(status=ContractStatus.READY_FOR_REVIEW, then=Value(5)),
        When(status=ContractStatus.GENERATION_ERROR, then=Value(6)),
        When(status=ContractStatus.DRAFT, then=Value(7)),
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
        "changeKind": contract.change_kind,
        "changeKindLabel": change_kind_label(contract.change_kind),
        "changeSummary": contract.change_summary or "",
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
        "companySignedAt": _dt(contract.company_signed_at),
        "signedAt": _dt(contract.signed_at),
        "activatedAt": _dt(contract.activated_at),
        "companySignatoryId": contract.company_signatory_id,
        "companySignatoryName": (
            contract.company_signatory.preferred_display_name()
            if contract.company_signatory_id and contract.company_signatory
            else ""
        ),
        "companySignUrl": (
            f"/operations/agent-contracts/{contract.public_id}/company-sign"
            if contract.status == ContractStatus.AWAITING_COMPANY_SIGNATURE
            and contract.company_signatory_id
            else None
        ),
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
        "amendsPublicId": (
            str(contract.amends.public_id) if contract.amends is not None else None
        ),
        "supersedesPublicId": (
            str(contract.supersedes.public_id)
            if contract.supersedes is not None
            else None
        ),
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
                "payee": _payee_summary(contract.mentor_payee),
                "notes": contract.mentor_notes,
            },
            "referral": {
                "percent": _dec(contract.referral_percent),
                "fixedAmount": _dec(contract.referral_fixed_amount),
                "capAmount": _dec(contract.referral_cap_amount),
                "basis": contract.referral_basis,
                "payeeId": contract.referral_payee_id,
                "payee": _payee_summary(contract.referral_payee),
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


def _payee_summary(payee: User | None) -> dict[str, Any] | None:
    if payee is None:
        return None
    office = getattr(payee, "office", None)
    return {
        "id": payee.pk,
        "name": payee.preferred_display_name(),
        "email": payee.email,
        "officeId": getattr(payee, "office_id", None),
        "officeName": office.name if office else "",
    }


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
        "rendererVersion": artifact.renderer_version or None,
        "ruleVersion": artifact.rule_version or None,
        "generatedAt": artifact.created_at.isoformat() if artifact.created_at else None,
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
    change_kind: str | None = None,
    change_summary: str = "",
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

    resolved_kind = change_kind
    if resolved_kind is None:
        if amends is not None:
            resolved_kind = ContractChangeKind.AMENDMENT
        elif supersedes is not None:
            resolved_kind = ContractChangeKind.REPLACEMENT
        else:
            resolved_kind = ContractChangeKind.ORIGINAL

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
        change_kind=resolved_kind,
        change_summary=(change_summary or "").strip(),
        calculation_rule_version=CURRENT_RULE_VERSION,
    )
    contract.party_snapshot = party_snapshot(recipient)
    contract.office_snapshot = office_snapshot(owning_office)
    # terms_snapshot filled after clean so quantized values are frozen.
    contract.full_clean()
    contract.terms_snapshot = terms_snapshot_from_contract(contract)

    with transaction.atomic():
        if root_agreement is not None:
            from apps.contract.versioning import lock_family, next_version_number

            lock_family(root_agreement.family_id)
            contract.family_id = root_agreement.family_id
            contract.version_number = next_version_number(root_agreement.family_id)
        elif supersedes is not None or amends is not None:
            from apps.contract.versioning import lock_family, next_version_number

            parent = supersedes or amends
            assert parent is not None
            lock_family(parent.family_id)
            contract.family_id = parent.family_id
            contract.version_number = next_version_number(parent.family_id)
            if contract.root_agreement_id is None:
                contract.root_agreement = (
                    parent.root_agreement if parent.root_agreement_id else parent
                )

        try:
            contract.save()
        except IntegrityError as exc:
            raise ValidationError(
                {
                    "version_number": _(
                        "Could not allocate a unique family version; retry."
                    )
                }
            ) from exc
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


@transaction.atomic
def initiate_onboarding_contract(
    actor: User, *, recipient: User
) -> tuple[AgentContract, bool]:
    """Create or reuse the recipient's contract draft from confirmed Hub facts.

    This is intentionally an initiation seam, not a second status writer. The
    contract workspace still owns template selection, commercial review, issue,
    PDF generation, and signing through the existing lifecycle service.
    """
    from apps.user.models import UserOnboardingCase
    from apps.user.services.onboarding_office import office_confirmation_is_current

    _ensure_manage(actor)
    if actor.pk == recipient.pk:
        raise PermissionDenied(_("You cannot initiate your own agent contract."))
    locked = (
        User.objects.select_for_update().select_related("office").get(pk=recipient.pk)
    )
    if not is_user_in_scope(actor, locked):
        raise PermissionDenied(_("Recipient is outside your administrative scope."))
    case = UserOnboardingCase.objects.filter(user=locked).first()
    if not locked.profile_completed:
        raise ValidationError(
            {"contract": _("The agent must complete their profile first.")}
        )
    if not office_confirmation_is_current(locked, case) or not (
        case and case.required_setup_completed_at
    ):
        raise ValidationError(
            {"contract": _("The agent must confirm their current office first.")}
        )
    existing = (
        AgentContract.objects.filter(recipient=locked)
        .order_by(
            models_order_priority(),
            "-effective_on",
            "-version_number",
            "-pk",
        )
        .first()
    )
    if existing is not None:
        return existing, False
    contract = create_draft_contract(
        actor,
        recipient=locked,
        office=locked.office,
        effective_on=locked.start_date or timezone.localdate(),
    )
    return contract, True


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
        if contract.signed_pdf_id:
            raise ValidationError(
                {
                    "kind": _(
                        "This contract version already has a signed PDF; "
                        "signed artifacts are immutable."
                    )
                }
            )
        contract.signed_pdf = artifact
        update_fields.append("signed_pdf")
    if update_fields:
        update_fields.append("updated_at")
        contract.save(update_fields=update_fields)
    return artifact
