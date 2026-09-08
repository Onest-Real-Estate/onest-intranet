"""Contract family versioning: amendments, addenda, and replacements.

Signed/active rows stay immutable. Changes create a new draft in the same
``family_id`` with a collision-safe ``version_number``, an explicit
``change_kind``, and ``amends`` / ``supersedes`` links. Activation of a
replacement (or any new governing version) still goes through
:mod:`apps.contract.lifecycle`, which supersedes the prior active row without
deleting it.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.change_kinds import (
    AMENDMENT_KINDS,
    ContractChangeKind,
    change_kind_label,
)
from apps.contract.models import FROZEN_CONTRACT_STATUSES, AgentContract
from apps.contract.permissions import MANAGE_AGENT_CONTRACTS
from apps.contract.snapshots import (
    office_snapshot,
    party_snapshot,
    terms_snapshot_from_contract,
)
from apps.contract.statuses import (
    PIPELINE_STATUSES,
    ContractStatus,
    status_label,
    status_tone,
)
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

#: Bases that may spawn an amendment or replacement.
ELIGIBLE_BASE_STATUSES = frozenset({ContractStatus.SIGNED, ContractStatus.ACTIVE})

#: Term keys compared for before/after presentation (flat + nested).
_TERM_DIFF_LABELS: dict[str, str] = {
    "agentSplitPercent": "Agent split %",
    "officeSplitPercent": "Office split %",
    "transactionFeeAmount": "Transaction fee ($)",
    "transactionFeePercent": "Transaction fee %",
    "annualCapAmount": "Annual cap",
    "specialArrangements": "Special arrangements",
    "addendaReferences": "Addenda references",
    "mentor.percent": "Mentor %",
    "mentor.fixedAmount": "Mentor fixed amount",
    "mentor.capAmount": "Mentor cap",
    "mentor.basis": "Mentor basis",
    "mentor.payeeId": "Mentor payee",
    "mentor.notes": "Mentor notes",
    "referral.percent": "Referral %",
    "referral.fixedAmount": "Referral fixed amount",
    "referral.capAmount": "Referral cap",
    "referral.basis": "Referral basis",
    "referral.payeeId": "Referral payee",
    "referral.notes": "Referral notes",
    "effectiveOn": "Effective on",
    "expiresOn": "Expires on",
    "changeSummary": "Change summary",
}


def _ensure_manage(actor: User) -> None:
    if getattr(actor, "is_superuser", False):
        return
    if not has_effective_permission(actor, MANAGE_AGENT_CONTRACTS):
        raise PermissionDenied(_("You cannot manage agent contracts."))


def family_root(contract: AgentContract) -> AgentContract:
    """Return the first agreement in the family (the row itself when root)."""
    root = contract.root_agreement
    if root is not None:
        return root
    return contract


def lock_family(family_id: uuid.UUID) -> list[AgentContract]:
    """Serialize version allocation for one family inside an open transaction."""
    return list(
        AgentContract.objects.select_for_update(of=("self",))
        .filter(family_id=family_id)
        .order_by("pk")
    )


def next_version_number(family_id: uuid.UUID) -> int:
    """Monotonic next version. Caller must hold the family lock."""
    current = (
        AgentContract.objects.filter(family_id=family_id)
        .order_by("-version_number")
        .values_list("version_number", flat=True)
        .first()
    )
    return (current or 0) + 1


def _assert_no_relationship_cycle(
    *,
    starting: AgentContract | None,
    attr: str,
    label: str,
) -> None:
    """Walk ``amends`` or ``supersedes`` and refuse self-cycles."""
    seen: set[int] = set()
    current = starting
    while current is not None:
        if current.pk in seen:
            raise ValidationError(
                {
                    attr: _(
                        "That %(label)s link would create a cycle in the "
                        "contract family."
                    )
                    % {"label": label}
                }
            )
        seen.add(current.pk)
        current = getattr(current, attr, None)


def family_has_open_pipeline(
    family_id: uuid.UUID, *, exclude_pk: int | None = None
) -> bool:
    """True when another in-flight draft/signing row already exists."""
    qs = AgentContract.objects.filter(
        family_id=family_id,
        status__in=PIPELINE_STATUSES,
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def assert_eligible_base(
    base: AgentContract,
    *,
    change_kind: str,
) -> None:
    """Refuse amendments/replacements against an invalid base."""
    if base.status not in ELIGIBLE_BASE_STATUSES:
        raise ValidationError(
            {
                "base": _(
                    "Only signed or active contracts can receive an "
                    "amendment or replacement."
                )
            }
        )
    if family_has_open_pipeline(base.family_id, exclude_pk=base.pk):
        raise ValidationError(
            {
                "base": _(
                    "This contract family already has an in-flight draft or "
                    "unsigned version. Finish or discard it before creating "
                    "another amendment or replacement."
                )
            }
        )
    if change_kind in AMENDMENT_KINDS:
        _assert_no_relationship_cycle(starting=base, attr="amends", label="amendment")
    elif change_kind == ContractChangeKind.REPLACEMENT:
        _assert_no_relationship_cycle(
            starting=base, attr="supersedes", label="replacement"
        )
        # One active replacement path: refuse when another replacement draft
        # already targets this base (covered by open-pipeline check) or when
        # the base is not the current tip for the recipient.
        if base.status == ContractStatus.ACTIVE:
            others = (
                AgentContract.objects.filter(
                    recipient_id=base.recipient_id,
                    status=ContractStatus.ACTIVE,
                )
                .exclude(pk=base.pk)
                .exists()
            )
            if others:
                raise ValidationError(
                    {
                        "base": _(
                            "Recipient already has another active contract; "
                            "resolve that before creating a replacement."
                        )
                    }
                )


def can_create_amendment(actor: User, base: AgentContract) -> bool:
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, MANAGE_AGENT_CONTRACTS)
    ):
        return False
    try:
        assert_eligible_base(base, change_kind=ContractChangeKind.AMENDMENT)
    except (ValidationError, PermissionDenied):
        return False
    return True


def can_create_replacement(actor: User, base: AgentContract) -> bool:
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, MANAGE_AGENT_CONTRACTS)
    ):
        return False
    try:
        assert_eligible_base(base, change_kind=ContractChangeKind.REPLACEMENT)
    except (ValidationError, PermissionDenied):
        return False
    return True


def _copy_commercial_kwargs(base: AgentContract) -> dict[str, Any]:
    return {
        "effective_on": base.effective_on,
        "expires_on": base.expires_on,
        "template_version": base.template_version,
        "agent_split_percent": base.agent_split_percent,
        "office_split_percent": base.office_split_percent,
        "transaction_fee_amount": base.transaction_fee_amount,
        "transaction_fee_percent": base.transaction_fee_percent,
        "annual_cap_amount": base.annual_cap_amount,
        "mentor_percent": base.mentor_percent,
        "mentor_fixed_amount": base.mentor_fixed_amount,
        "mentor_cap_amount": base.mentor_cap_amount,
        "mentor_basis": base.mentor_basis or "",
        "mentor_payee": base.mentor_payee,
        "mentor_notes": base.mentor_notes or "",
        "referral_percent": base.referral_percent,
        "referral_fixed_amount": base.referral_fixed_amount,
        "referral_cap_amount": base.referral_cap_amount,
        "referral_basis": base.referral_basis or "",
        "referral_payee": base.referral_payee,
        "referral_notes": base.referral_notes or "",
        "special_arrangements": base.special_arrangements or "",
        "addenda_references": list(base.addenda_references or []),
        "internal_notes": base.internal_notes or "",
    }


def _build_family_draft(
    actor: User,
    base: AgentContract,
    *,
    change_kind: str,
    change_summary: str,
    amends: AgentContract | None,
    supersedes: AgentContract | None,
    effective_on: date | None = None,
    expires_on: date | None | object = ...,
) -> AgentContract:
    """Create a prepopulated draft under the base family (locked)."""
    from apps.contract.calculations.rules import CURRENT_RULE_VERSION
    from apps.contract.services import scoped_contract_queryset

    _ensure_manage(actor)
    if not scoped_contract_queryset(actor).filter(pk=base.pk).exists():
        raise PermissionDenied(_("Contract is outside your scope."))

    assert_eligible_base(base, change_kind=change_kind)
    root = family_root(base)
    kwargs = _copy_commercial_kwargs(base)
    if effective_on is not None:
        kwargs["effective_on"] = effective_on
    if expires_on is not ...:
        kwargs["expires_on"] = expires_on

    with transaction.atomic():
        lock_family(base.family_id)
        # Re-check after lock — another writer may have branched.
        assert_eligible_base(base, change_kind=change_kind)
        version_number = next_version_number(base.family_id)

        # Children always point at the family's root row (never null on
        # amendments/replacements). The root itself keeps root_agreement=null.
        contract = AgentContract(
            recipient=base.recipient,
            office=base.office,
            created_by=actor,
            status=ContractStatus.DRAFT,
            family_id=base.family_id,
            version_number=version_number,
            change_kind=change_kind,
            change_summary=(change_summary or "").strip(),
            root_agreement=root,
            amends=amends,
            supersedes=supersedes,
            calculation_rule_version=CURRENT_RULE_VERSION,
            template_version=kwargs["template_version"],
            effective_on=kwargs["effective_on"],
            expires_on=kwargs["expires_on"],
            agent_split_percent=kwargs["agent_split_percent"],
            office_split_percent=kwargs["office_split_percent"],
            transaction_fee_amount=kwargs["transaction_fee_amount"],
            transaction_fee_percent=kwargs["transaction_fee_percent"],
            annual_cap_amount=kwargs["annual_cap_amount"],
            mentor_percent=kwargs["mentor_percent"],
            mentor_fixed_amount=kwargs["mentor_fixed_amount"],
            mentor_cap_amount=kwargs["mentor_cap_amount"],
            mentor_basis=kwargs["mentor_basis"],
            mentor_payee=kwargs["mentor_payee"],
            mentor_notes=kwargs["mentor_notes"],
            referral_percent=kwargs["referral_percent"],
            referral_fixed_amount=kwargs["referral_fixed_amount"],
            referral_cap_amount=kwargs["referral_cap_amount"],
            referral_basis=kwargs["referral_basis"],
            referral_payee=kwargs["referral_payee"],
            referral_notes=kwargs["referral_notes"],
            special_arrangements=kwargs["special_arrangements"],
            addenda_references=kwargs["addenda_references"],
            internal_notes=kwargs["internal_notes"],
        )

        contract.party_snapshot = party_snapshot(base.recipient)
        contract.office_snapshot = office_snapshot(base.office)
        contract.full_clean()
        contract.terms_snapshot = terms_snapshot_from_contract(contract)

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
            "contract.version.created",
            actor=actor_from_user(actor),
            target=AuditTarget(
                target_type=AgentContract._meta.label_lower,
                target_id=str(contract.public_id),
                target_label=base.recipient.email,
                target_snapshot={
                    "status": contract.status,
                    "changeKind": contract.change_kind,
                    "familyId": str(contract.family_id),
                    "versionNumber": contract.version_number,
                    "basePublicId": str(base.public_id),
                },
            ),
            before={
                "basePublicId": str(base.public_id),
                "baseStatus": base.status,
                "baseVersionNumber": base.version_number,
            },
            after={
                "publicId": str(contract.public_id),
                "changeKind": contract.change_kind,
                "versionNumber": contract.version_number,
                "amendsId": contract.amends_id,
                "supersedesId": contract.supersedes_id,
            },
            outcome=AuditEvent.Outcome.SUCCESS,
            source="service",
            channel="contract",
            office_id=base.office.stable_key,
        )
    return contract


def create_amendment_draft(
    actor: User,
    base: AgentContract,
    *,
    change_kind: str = ContractChangeKind.AMENDMENT,
    change_summary: str = "",
    effective_on: date | None = None,
    expires_on: date | None | object = ...,
) -> AgentContract:
    """Spawn an amendment/addendum draft prepopulated from ``base``."""
    if change_kind not in AMENDMENT_KINDS:
        raise ValidationError(
            {"change_kind": _("Use amendment or addendum for this workflow.")}
        )
    return _build_family_draft(
        actor,
        base,
        change_kind=change_kind,
        change_summary=change_summary,
        amends=base,
        supersedes=None,
        effective_on=effective_on,
        expires_on=expires_on,
    )


def create_replacement_draft(
    actor: User,
    base: AgentContract,
    *,
    change_summary: str = "",
    effective_on: date | None = None,
    expires_on: date | None | object = ...,
) -> AgentContract:
    """Spawn a full replacement draft that will supersede ``base`` on activate."""
    return _build_family_draft(
        actor,
        base,
        change_kind=ContractChangeKind.REPLACEMENT,
        change_summary=change_summary,
        amends=None,
        supersedes=base,
        effective_on=effective_on,
        expires_on=expires_on,
    )


def _flatten_terms(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    data = snapshot or {}
    for key in (
        "agentSplitPercent",
        "officeSplitPercent",
        "transactionFeeAmount",
        "transactionFeePercent",
        "annualCapAmount",
        "specialArrangements",
        "addendaReferences",
    ):
        flat[key] = data.get(key)
    for block in ("mentor", "referral"):
        nested = data.get(block) or {}
        if not isinstance(nested, dict):
            nested = {}
        for sub in ("percent", "fixedAmount", "capAmount", "basis", "payeeId", "notes"):
            flat[f"{block}.{sub}"] = nested.get(sub)
    return flat


def comparison_terms(contract: AgentContract) -> dict[str, Any]:
    """Terms used for before/after UI, including dates and change summary."""
    snapshot = contract.terms_snapshot or terms_snapshot_from_contract(contract)
    terms = _flatten_terms(snapshot)
    terms["effectiveOn"] = contract.effective_on.isoformat()
    terms["expiresOn"] = (
        contract.expires_on.isoformat() if contract.expires_on else None
    )
    terms["changeSummary"] = contract.change_summary or ""
    return terms


def term_diff(
    before: AgentContract,
    after: AgentContract,
) -> list[dict[str, Any]]:
    """Structured before/after rows for issuance review."""
    left = comparison_terms(before)
    right = comparison_terms(after)
    rows: list[dict[str, Any]] = []
    for key, label in _TERM_DIFF_LABELS.items():
        old = left.get(key)
        new = right.get(key)
        if old == new:
            continue
        rows.append(
            {
                "key": key,
                "label": label,
                "before": _display_term(old),
                "after": _display_term(new),
                "changed": True,
            }
        )
    return rows


def _display_term(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def related_base(contract: AgentContract) -> AgentContract | None:
    if contract.amends_id:
        return contract.amends
    if contract.supersedes_id:
        return contract.supersedes
    return None


def term_comparison_payload(
    actor: User, contract: AgentContract
) -> dict[str, Any] | None:
    """Workspace/issue comparison against the related base version."""
    base = related_base(contract)
    if base is None:
        return None
    from apps.contract.services import scoped_contract_queryset

    if not scoped_contract_queryset(actor).filter(pk=base.pk).exists():
        return None
    return {
        "basePublicId": str(base.public_id),
        "baseVersionNumber": base.version_number,
        "baseStatus": base.status,
        "baseStatusLabel": str(status_label(base.status)),
        "baseEffectiveOn": base.effective_on.isoformat(),
        "baseExpiresOn": (base.expires_on.isoformat() if base.expires_on else None),
        "draftEffectiveOn": contract.effective_on.isoformat(),
        "draftExpiresOn": (
            contract.expires_on.isoformat() if contract.expires_on else None
        ),
        "changeKind": contract.change_kind,
        "changeKindLabel": change_kind_label(contract.change_kind),
        "changeSummary": contract.change_summary or "",
        "rows": term_diff(base, contract),
        "effectiveDateNote": _effective_date_note(base, contract),
    }


def _effective_date_note(base: AgentContract, draft: AgentContract) -> str:
    if draft.effective_on == base.effective_on and draft.expires_on == base.expires_on:
        return (
            "Effective and expiration dates match the base version. "
            "Confirm that is intentional before issuing."
        )
    parts: list[str] = []
    if draft.effective_on != base.effective_on:
        parts.append(
            f"Effective date moves from {base.effective_on.isoformat()} "
            f"to {draft.effective_on.isoformat()}."
        )
    if draft.expires_on != base.expires_on:
        before = base.expires_on.isoformat() if base.expires_on else "none"
        after = draft.expires_on.isoformat() if draft.expires_on else "none"
        parts.append(f"Expiration moves from {before} to {after}.")
    return " ".join(parts)


def governing_terms_payload(contract: AgentContract) -> dict[str, Any]:
    """Currently governing commercial terms for the focused version.

    Rules:
    - An **active** (or otherwise current) row's own frozen terms govern.
    - An amendment/addendum that is itself active carries the full governing
      commercial snapshot (prepopulated from base, then edited); the
      ``amends`` link documents provenance, and ``term_diff`` shows deltas.
    - Superseded/expired/terminated rows still expose *their* historical terms
      for that version — never rewritten by later family members.
    """
    snapshot = contract.terms_snapshot or terms_snapshot_from_contract(contract)
    return {
        "publicId": str(contract.public_id),
        "versionNumber": contract.version_number,
        "changeKind": contract.change_kind,
        "changeKindLabel": change_kind_label(contract.change_kind),
        "status": contract.status,
        "isGoverning": contract.status == ContractStatus.ACTIVE,
        "effectiveOn": contract.effective_on.isoformat(),
        "expiresOn": (contract.expires_on.isoformat() if contract.expires_on else None),
        "amendsPublicId": (
            str(contract.amends.public_id) if contract.amends is not None else None
        ),
        "supersedesPublicId": (
            str(contract.supersedes.public_id)
            if contract.supersedes is not None
            else None
        ),
        "terms": snapshot,
        "changeSummary": contract.change_summary or "",
    }


def serialize_family_history_row(
    contract: AgentContract,
    *,
    focus_id: int,
    workspace_href: str | None = None,
) -> dict[str, Any]:
    role = "version"
    if contract.change_kind == ContractChangeKind.ORIGINAL and not contract.amends_id:
        role = "base"
    elif contract.change_kind in AMENDMENT_KINDS:
        role = "amendment"
    elif contract.change_kind == ContractChangeKind.REPLACEMENT:
        role = "replacement"
    if contract.status == ContractStatus.ACTIVE:
        governing = "current"
    elif contract.status in FROZEN_CONTRACT_STATUSES and contract.status in {
        ContractStatus.SUPERSEDED,
        ContractStatus.EXPIRED,
        ContractStatus.TERMINATED,
    }:
        governing = "historical"
    else:
        governing = "in_flight"

    return {
        "publicId": str(contract.public_id),
        "versionNumber": contract.version_number,
        "changeKind": contract.change_kind,
        "changeKindLabel": change_kind_label(contract.change_kind),
        "role": role,
        "governing": governing,
        "status": contract.status,
        "statusLabel": str(status_label(contract.status)),
        "statusTone": status_tone(contract.status),
        "effectiveOn": contract.effective_on.isoformat(),
        "expiresOn": (contract.expires_on.isoformat() if contract.expires_on else None),
        "isFocus": contract.pk == focus_id,
        "amendsPublicId": (
            str(contract.amends.public_id) if contract.amends is not None else None
        ),
        "supersedesPublicId": (
            str(contract.supersedes.public_id)
            if contract.supersedes is not None
            else None
        ),
        "hasArtifact": bool(contract.generated_pdf_id or contract.signed_pdf_id),
        "href": workspace_href or "",
    }


def family_history_for_admin(actor: User, focus: AgentContract) -> list[dict[str, Any]]:
    from django.urls import reverse

    from apps.contract.services import scoped_contract_queryset

    rows = (
        scoped_contract_queryset(actor)
        .filter(family_id=focus.family_id)
        .select_related("amends", "supersedes")
        .order_by("-version_number", "-pk")
    )
    return [
        serialize_family_history_row(
            row,
            focus_id=focus.pk,
            workspace_href=reverse(
                "agent_contract_workspace", kwargs={"public_id": row.public_id}
            ),
        )
        for row in rows
    ]
