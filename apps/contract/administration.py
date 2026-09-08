"""Admin authoring services for agent contracts (P1-039).

Creates, updates, validates, and previews drafts. Issuance goes through
``apps.contract.lifecycle.transition``. Office, template applicability, and
snapshots are always derived on the server — never trusted from the client.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from html import escape
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.artifact_delivery import generated_pdf_download_url
from apps.contract.calculations import summarize_terms_for_display
from apps.contract.lifecycle import (
    StaleContractVersion,
    allowed_actions,
    contract_version,
    transition,
)
from apps.contract.models import (
    AgentContract,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.permissions import (
    MANAGE_AGENT_CONTRACTS,
    VIEW_AGENT_CONTRACTS,
    VIEW_COMMISSION_TERMS,
    VIEW_INTERNAL_NOTES,
)
from apps.contract.services import (
    _ensure_manage,
    _office_in_scope,
    create_draft_contract,
    scoped_contract_queryset,
    serialize_contract,
)
from apps.contract.services.calculation_service import (
    preview_commission,
    terms_input_from_contract,
)
from apps.contract.snapshots import (
    office_snapshot,
    party_snapshot,
    terms_snapshot_from_contract,
)
from apps.contract.statuses import ContractStatus, status_label, status_tone
from apps.contract.terms import CommissionBasis, quantize_money, quantize_percent
from apps.user.administration_fields import ACTIVE as ACTIVE_AGENT_STATUS
from apps.user.models import Office, User
from apps.user.services.agent_administration import (
    administration_scope,
    is_user_in_scope,
)
from apps.user.services.role_assignments import has_effective_permission
from apps.user.services.user_directory import directory_queryset

UNSET: Any = object()

MIN_RECIPIENT_QUERY = 2
RECIPIENT_SEARCH_LIMIT = 20
EDITABLE_STATUSES = frozenset({ContractStatus.DRAFT})

_SENSITIVE_TERM_FIELDS = (
    "agent_split_percent",
    "office_split_percent",
    "transaction_fee_amount",
    "transaction_fee_percent",
    "annual_cap_amount",
    "mentor_percent",
    "mentor_fixed_amount",
    "mentor_cap_amount",
    "mentor_basis",
    "mentor_payee_id",
    "referral_percent",
    "referral_fixed_amount",
    "referral_cap_amount",
    "referral_basis",
    "referral_payee_id",
)


def capabilities(actor: User) -> dict[str, bool]:
    manage = bool(
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, MANAGE_AGENT_CONTRACTS)
    )
    return {
        "canView": manage
        or bool(
            getattr(actor, "is_superuser", False)
            or has_effective_permission(actor, VIEW_AGENT_CONTRACTS)
        ),
        "canManage": manage,
        "canViewCommission": bool(
            getattr(actor, "is_superuser", False)
            or has_effective_permission(actor, VIEW_COMMISSION_TERMS)
            or manage
        ),
        "canViewNotes": bool(
            getattr(actor, "is_superuser", False)
            or has_effective_permission(actor, VIEW_INTERNAL_NOTES)
        ),
    }


def applicable_template_versions(
    office: Office,
    effective_on: date,
) -> QuerySet[ContractTemplateVersion]:
    """Published active versions that apply to an office on a given date."""
    region = office.region
    family_q = Q(company_wide=True) | Q(applicable_offices=office)
    if region is not None:
        family_q |= Q(applicable_regions=region)

    family_ids = (
        ContractTemplate.objects.filter(
            status=ContractTemplate.Status.ACTIVE,
            active_version__isnull=False,
            active_version__status=ContractTemplateVersion.Status.PUBLISHED,
        )
        .filter(family_q)
        .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=effective_on))
        .filter(Q(effective_until__isnull=True) | Q(effective_until__gte=effective_on))
        .values_list("active_version_id", flat=True)
    )
    queryset = ContractTemplateVersion.objects.select_related("template").filter(
        pk__in=family_ids,
        status=ContractTemplateVersion.Status.PUBLISHED,
    )

    state = _office_jurisdiction_state(office)
    matching: list[int] = []
    for version in queryset:
        codes = [
            str(code).strip().upper()
            for code in (version.template.jurisdiction_state_codes or [])
            if str(code).strip()
        ]
        # Unrestricted templates apply everywhere. Jurisdiction-limited
        # templates require a resolvable office state that matches.
        if not codes or (state and state in codes):
            matching.append(version.pk)
    return queryset.filter(pk__in=matching).order_by("template__name", "version_label")


def _office_jurisdiction_state(office: Office) -> str:
    """Return the office US state, walking parents when the leaf is blank."""
    current: Office | None = office
    seen: set[int] = set()
    while current is not None and current.pk not in seen:
        seen.add(current.pk)
        state = (current.state or "").strip().upper()
        if state:
            return state
        current = current.parent
    return ""


def assert_template_applicable(
    template_version: ContractTemplateVersion | None,
    *,
    office: Office,
    effective_on: date,
) -> None:
    if template_version is None:
        return
    if template_version.status != ContractTemplateVersion.Status.PUBLISHED:
        raise ValidationError(
            {
                "template_version": _(
                    "Only published template versions can originate a contract."
                )
            }
        )
    allowed = applicable_template_versions(office, effective_on)
    if not allowed.filter(pk=template_version.pk).exists():
        raise ValidationError(
            {
                "template_version": _(
                    "That template version does not apply to this office "
                    "or effective date."
                )
            }
        )


def search_contract_recipients(
    actor: User, query: str, *, limit: int = RECIPIENT_SEARCH_LIMIT
) -> list[dict[str, Any]]:
    _ensure_manage(actor)
    term = (query or "").strip()[:120]
    if len(term) < MIN_RECIPIENT_QUERY:
        return []
    rows = (
        directory_queryset(actor)
        .filter(is_active=True, agent_status=ACTIVE_AGENT_STATUS)
        .filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(email__icontains=term)
            | Q(display_name__icontains=term)
            | Q(agent_identifier__icontains=term)
        )
        .select_related("office")[: max(1, min(limit, RECIPIENT_SEARCH_LIMIT))]
    )
    return [
        {
            "id": row.pk,
            "name": row.preferred_display_name(),
            "email": row.email,
            "officeId": getattr(row, "office_id", None),
            "officeName": row.office.name if row.office else "",
            "officeState": (
                _office_jurisdiction_state(row.office) if row.office else ""
            ),
            "licenseState": row.license_state or "",
            "agentIdentifier": row.agent_identifier or "",
        }
        for row in rows
    ]


def serialize_template_option(version: ContractTemplateVersion) -> dict[str, Any]:
    template = version.template
    return {
        "id": version.pk,
        "publicId": str(version.public_id),
        "versionLabel": version.version_label,
        "displayName": version.display_name or template.name,
        "templateName": template.name,
        "templateStableKey": template.stable_key,
        "jurisdictionStateCodes": list(template.jurisdiction_state_codes or []),
    }


def _term_audit_slice(contract: AgentContract) -> dict[str, Any]:
    return {
        field: getattr(contract, field)
        for field in _SENSITIVE_TERM_FIELDS
        if hasattr(contract, field)
    }


def update_draft_contract(
    actor: User,
    contract: AgentContract,
    *,
    expected_version: str,
    office: Office | None = None,
    effective_on: date | None = None,
    expires_on: date | None = UNSET,
    template_version: ContractTemplateVersion | None = UNSET,
    agent_split_percent: Decimal | str | None = UNSET,
    office_split_percent: Decimal | str | None = UNSET,
    transaction_fee_amount: Decimal | str | None = UNSET,
    transaction_fee_percent: Decimal | str | None = UNSET,
    annual_cap_amount: Decimal | str | None = UNSET,
    mentor_percent: Decimal | str | None = UNSET,
    mentor_fixed_amount: Decimal | str | None = UNSET,
    mentor_cap_amount: Decimal | str | None = UNSET,
    mentor_basis: str | None = None,
    mentor_payee: User | None = UNSET,
    mentor_notes: str | None = None,
    referral_percent: Decimal | str | None = UNSET,
    referral_fixed_amount: Decimal | str | None = UNSET,
    referral_cap_amount: Decimal | str | None = UNSET,
    referral_basis: str | None = None,
    referral_payee: User | None = UNSET,
    referral_notes: str | None = None,
    special_arrangements: str | None = None,
    addenda_references: list[str] | None = None,
    internal_notes: str | None = None,
    change_summary: str | None = None,
) -> AgentContract:
    """Update a draft. Ellipsis means leave unchanged; ``None`` clears nullable."""
    _ensure_manage(actor)
    if contract.status not in EDITABLE_STATUSES:
        raise ValidationError({"status": _("Only draft contracts can be edited here.")})
    if not scoped_contract_queryset(actor).filter(pk=contract.pk).exists():
        raise PermissionDenied(_("Contract is outside your scope."))
    if contract_version(contract) != (expected_version or ""):
        raise StaleContractVersion()

    before = _term_audit_slice(contract)

    with transaction.atomic():
        locked = AgentContract.objects.select_for_update(of=("self",)).get(
            pk=contract.pk
        )
        if locked.status not in EDITABLE_STATUSES:
            raise ValidationError(
                {"status": _("Only draft contracts can be edited here.")}
            )
        if contract_version(locked) != (expected_version or ""):
            raise StaleContractVersion()

        recipient = locked.recipient
        if not recipient.is_active or recipient.agent_status != ACTIVE_AGENT_STATUS:
            raise ValidationError(
                {"recipient": _("Recipient is no longer an active agent.")}
            )

        owning_office = office if office is not None else locked.office
        if owning_office is None:
            raise ValidationError({"office": _("Owning office is required.")})
        if not owning_office.is_active or not owning_office.is_assignable:
            raise ValidationError({"office": _("Owning office is not assignable.")})
        scope = administration_scope(actor)
        if not _office_in_scope(owning_office, scope):
            raise ValidationError(
                {"office": _("Owning office is outside your administrative scope.")}
            )
        if not is_user_in_scope(actor, recipient):
            raise ValidationError(
                {"recipient": _("Recipient is outside your administrative scope.")}
            )

        locked.office = owning_office
        if effective_on is not None:
            locked.effective_on = effective_on
        if expires_on is not UNSET:
            locked.expires_on = expires_on

        next_template = locked.template_version
        if template_version is not UNSET:
            next_template = template_version
        assert_template_applicable(
            next_template, office=owning_office, effective_on=locked.effective_on
        )
        locked.template_version = next_template

        def _maybe_set(field: str, value, *, quantize=None):
            if value is UNSET:
                return
            if quantize is not None and value is not None:
                value = quantize(value)
            setattr(locked, field, value)

        _maybe_set(
            "agent_split_percent", agent_split_percent, quantize=quantize_percent
        )
        _maybe_set(
            "office_split_percent", office_split_percent, quantize=quantize_percent
        )
        _maybe_set(
            "transaction_fee_amount", transaction_fee_amount, quantize=quantize_money
        )
        _maybe_set(
            "transaction_fee_percent",
            transaction_fee_percent,
            quantize=quantize_percent,
        )
        _maybe_set("annual_cap_amount", annual_cap_amount, quantize=quantize_money)
        _maybe_set("mentor_percent", mentor_percent, quantize=quantize_percent)
        _maybe_set("mentor_fixed_amount", mentor_fixed_amount, quantize=quantize_money)
        _maybe_set("mentor_cap_amount", mentor_cap_amount, quantize=quantize_money)
        if mentor_basis is not None:
            locked.mentor_basis = mentor_basis
        if mentor_payee is not UNSET:
            locked.mentor_payee = mentor_payee
        if mentor_notes is not None:
            locked.mentor_notes = mentor_notes
        _maybe_set("referral_percent", referral_percent, quantize=quantize_percent)
        _maybe_set(
            "referral_fixed_amount", referral_fixed_amount, quantize=quantize_money
        )
        _maybe_set("referral_cap_amount", referral_cap_amount, quantize=quantize_money)
        if referral_basis is not None:
            locked.referral_basis = referral_basis
        if referral_payee is not UNSET:
            locked.referral_payee = referral_payee
        if referral_notes is not None:
            locked.referral_notes = referral_notes
        if special_arrangements is not None:
            locked.special_arrangements = special_arrangements
        if addenda_references is not None:
            locked.addenda_references = list(addenda_references)
        if internal_notes is not None:
            locked.internal_notes = internal_notes
        if change_summary is not None:
            locked.change_summary = change_summary.strip()

        locked.party_snapshot = party_snapshot(recipient)
        locked.office_snapshot = office_snapshot(owning_office)
        locked.full_clean()
        locked.terms_snapshot = terms_snapshot_from_contract(locked)
        locked.save()
        after = _term_audit_slice(locked)
        if before != after:
            log_event(
                "contract.draft.updated",
                actor=actor_from_user(actor),
                target=AuditTarget(
                    target_type=AgentContract._meta.label_lower,
                    target_id=str(locked.public_id),
                    target_label=recipient.email,
                    target_snapshot={
                        "status": locked.status,
                        "recipient_id": recipient.pk,
                        "office_id": owning_office.pk,
                    },
                ),
                before={
                    k: str(v) if v is not None else None for k, v in before.items()
                },
                after={k: str(v) if v is not None else None for k, v in after.items()},
                outcome=AuditEvent.Outcome.SUCCESS,
                source="service",
                channel="contract",
                office_id=owning_office.stable_key,
            )
    return locked


def create_draft_with_applicability(actor: User, **kwargs) -> AgentContract:
    """Wrapper around ``create_draft_contract`` that enforces template applicability."""
    recipient = kwargs["recipient"]
    office = kwargs.get("office") or recipient.office
    effective_on = kwargs["effective_on"]
    template_version = kwargs.get("template_version")
    if office is not None:
        assert_template_applicable(
            template_version, office=office, effective_on=effective_on
        )
    return create_draft_contract(actor, **kwargs)


def commercial_preview(
    actor: User,
    contract: AgentContract,
    *,
    gross_commission: Decimal | str = "10000",
) -> dict[str, Any]:
    caps = capabilities(actor)
    if not caps["canViewCommission"]:
        raise PermissionDenied(_("Commission terms are not visible to you."))
    if not scoped_contract_queryset(actor).filter(pk=contract.pk).exists():
        raise PermissionDenied(_("Contract is outside your scope."))
    terms = terms_input_from_contract(contract)
    result = preview_commission(contract, gross_commission=gross_commission)
    return {
        "summaryLines": summarize_terms_for_display(terms),
        "breakdown": {
            "ruleVersion": result.rule_version,
            "currency": result.currency,
            "grossCommission": result.input_snapshot.get("grossCommission"),
            "agentNet": format(result.agent_net, "f"),
            "officeNet": format(result.office_net, "f"),
            "transactionFee": format(result.transaction_fee, "f"),
            "mentorAmount": format(result.mentor.amount, "f")
            if result.mentor
            else None,
            "referralAmount": (
                format(result.referral.amount, "f") if result.referral else None
            ),
            "explanation": list(result.explanation),
        },
        "units": {
            "percentUnit": "percent",
            "moneyCurrency": "USD",
            "percentQuantum": "0.001",
            "moneyQuantum": "0.01",
        },
    }


def agreement_preview_payload(actor: User, contract: AgentContract) -> dict[str, Any]:
    """Server-owned merge context for agreement preview (HTML summary)."""
    _ensure_manage(actor)
    if not scoped_contract_queryset(actor).filter(pk=contract.pk).exists():
        raise PermissionDenied(_("Contract is outside your scope."))
    if not contract.template_version_id:
        raise ValidationError(
            {"template_version": _("Choose a template before previewing.")}
        )
    version = contract.template_version
    try:
        from apps.contract.pdf_generation import build_merge_values

        merge_values = build_merge_values(contract)
    except Exception:  # noqa: BLE001 - preview falls back to a static key set
        party = contract.party_snapshot or {}
        office = contract.office_snapshot or {}
        merge_values = {
            "party.legalFirstName": party.get("legalFirstName") or "",
            "party.legalLastName": party.get("legalLastName") or "",
            "party.email": party.get("email") or "",
            "party.licenseNumber": party.get("licenseNumber") or "",
            "party.licenseState": party.get("licenseState") or "",
            "office.name": office.get("name") or "",
            "office.state": office.get("state") or "",
            "office.city": office.get("city") or "",
            "office.streetAddress": office.get("streetAddress") or "",
            "terms.agentSplitPercent": (contract.terms_snapshot or {}).get(
                "agentSplitPercent"
            )
            or "",
            "terms.officeSplitPercent": (contract.terms_snapshot or {}).get(
                "officeSplitPercent"
            )
            or "",
            "contract.effectiveOn": contract.effective_on.isoformat(),
            "contract.expiresOn": (
                contract.expires_on.isoformat() if contract.expires_on else ""
            ),
            "contract.publicId": str(contract.public_id),
            "template.versionLabel": version.version_label if version else "",
        }
    return {
        "status": "ready",
        "templateVersionId": version.pk if version else None,
        "templateName": version.template.name if version else "",
        "mergeValues": merge_values,
        "partySnapshot": contract.party_snapshot,
        "officeSnapshot": contract.office_snapshot,
        "termsSnapshot": contract.terms_snapshot
        if capabilities(actor)["canViewCommission"]
        else None,
        "html": _preview_html(contract, merge_values),
    }


def _preview_html(contract: AgentContract, merge_values: dict[str, str]) -> str:
    rows = "".join(
        f"<tr><th scope='row'>{escape(key)}</th><td>{escape(str(value))}</td></tr>"
        for key, value in sorted(merge_values.items())
    )
    return (
        f"<article class='contract-preview'>"
        f"<h1>Agreement preview</h1>"
        f"<p>Contract {escape(str(contract.public_id))} · "
        f"{escape(str(status_label(contract.status)))}</p>"
        f"<table>{rows}</table>"
        f"</article>"
    )


def issue_contract(
    actor: User,
    contract: AgentContract,
    *,
    expected_version: str,
    confirmed: bool,
    idempotency_key: str = "",
) -> AgentContract:
    """Issue via lifecycle after re-checking template applicability."""
    _ensure_manage(actor)
    if not scoped_contract_queryset(actor).filter(pk=contract.pk).exists():
        raise PermissionDenied(_("Contract is outside your scope."))
    assert_template_applicable(
        contract.template_version,
        office=contract.office,
        effective_on=contract.effective_on,
    )
    return transition(
        actor=actor,
        contract=contract,
        action="issue",
        expected_version=expected_version,
        confirmed=confirmed,
        idempotency_key=idempotency_key,
    )


def workspace_payload(actor: User, contract: AgentContract) -> dict[str, Any]:
    from apps.contract.versioning import (
        can_create_amendment,
        can_create_replacement,
        family_history_for_admin,
        governing_terms_payload,
        term_comparison_payload,
    )

    caps = capabilities(actor)
    payload = serialize_contract(actor, contract)
    recipient = contract.recipient
    office = contract.office
    template_options = [
        serialize_template_option(v)
        for v in applicable_template_versions(office, contract.effective_on)
    ]
    commercial = None
    if caps["canViewCommission"]:
        try:
            commercial = commercial_preview(actor, contract)
        except ValidationError:
            commercial = {"summaryLines": [], "breakdown": None, "units": {}}
    return {
        "contract": payload,
        "expectedVersion": contract_version(contract),
        "capabilities": {
            **caps,
            "canCreateAmendment": can_create_amendment(actor, contract),
            "canCreateReplacement": can_create_replacement(actor, contract),
        },
        "allowedActions": allowed_actions(actor, contract),
        "generatedPdfUrl": generated_pdf_download_url(contract)
        if contract.generated_pdf_id
        else None,
        "recipient": {
            "id": recipient.pk,
            "name": recipient.preferred_display_name(),
            "email": recipient.email,
            "officeId": recipient.office_id,
            "officeName": recipient.office.name if recipient.office else "",
            "licenseState": recipient.license_state or "",
            "agentStatus": recipient.agent_status,
        },
        "office": office_snapshot(office),
        "templateOptions": template_options,
        "commissionBasisOptions": [
            {"value": value, "label": str(label)}
            for value, label in CommissionBasis.choices
        ],
        "commercialPreview": commercial,
        "statusOptions": [
            {"value": value, "label": str(label), "tone": status_tone(value)}
            for value, label in ContractStatus.choices
        ],
        "familyHistory": family_history_for_admin(actor, contract),
        "termComparison": term_comparison_payload(actor, contract),
        "governingTerms": governing_terms_payload(contract),
    }
