"""Self-service My Contract page payload (P1-041).

The recipient is always the authenticated user. Routes never accept an agent
id from the client. Presentation props omit internal notes, admin-only
calculations, and other agents' contracts.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.contract.calculations import summarize_terms_for_display
from apps.contract.change_kinds import change_kind_label
from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import AgentContract, ContractSignature
from apps.contract.pdf_signing import signing_is_ready
from apps.contract.permissions import VIEW_OWN_COMMISSION
from apps.contract.services import (
    _artifact_meta,
    _can_view_commission,
    _dec,
    _dt,
    models_order_priority,
    recipient_contract_queryset,
)
from apps.contract.services.calculation_service import terms_input_from_contract
from apps.contract.statuses import ContractStatus, status_label, status_tone
from apps.contract.versioning import serialize_family_history_row
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

#: Statuses a recipient may see on My Contract (issued and beyond).
RECIPIENT_VISIBLE_STATUSES = frozenset(
    {
        ContractStatus.SENT,
        ContractStatus.VIEWED,
        ContractStatus.SIGNED,
        ContractStatus.ACTIVE,
        ContractStatus.SUPERSEDED,
        ContractStatus.EXPIRED,
        ContractStatus.TERMINATED,
        ContractStatus.GENERATION_ERROR,
    }
)

SIGNABLE_STATUSES = frozenset({ContractStatus.SENT, ContractStatus.VIEWED})


def _related_public_id(related: AgentContract | None) -> str | None:
    if related is None:
        return None
    return str(related.public_id)


def recipient_visible_queryset(user: User) -> QuerySet[AgentContract]:
    """Self-only contracts that have left the draft authoring pipeline."""
    return (
        recipient_contract_queryset(user)
        .filter(status__in=RECIPIENT_VISIBLE_STATUSES)
        .select_related("amends", "supersedes")
    )


def select_current_contract(
    user: User, *, version_public_id: UUID | None = None
) -> AgentContract | None:
    """Resolve the focused contract for the signed-in recipient.

    Optional ``version_public_id`` must belong to the same recipient and a
    visible status — never another agent's row. Unknown ids fall back to the
    governing/current agreement rather than leaking existence.
    """
    visible = recipient_visible_queryset(user)
    if version_public_id is not None:
        focused = visible.filter(public_id=version_public_id).first()
        if focused is not None:
            return focused
    return visible.order_by(
        models_order_priority(),
        "-effective_on",
        "-version_number",
        "-pk",
    ).first()


def presentation_state(contract: AgentContract | None) -> str:
    """Stable UX state key for the My Contract page shell."""
    if contract is None:
        return "no_contract"
    if contract.status == ContractStatus.GENERATION_ERROR:
        return "generation_failed"
    if contract.status == ContractStatus.SENT and not contract.generated_pdf_id:
        return "generating"
    if contract.status in SIGNABLE_STATUSES:
        return "awaiting_signature"
    if contract.status == ContractStatus.SIGNED:
        return "signed"
    if contract.status == ContractStatus.ACTIVE:
        return "active"
    if contract.status == ContractStatus.EXPIRED:
        return "expired"
    if contract.status == ContractStatus.SUPERSEDED:
        return "superseded"
    if contract.status == ContractStatus.TERMINATED:
        return "terminated"
    return "no_contract"


def next_action_copy(state: str) -> dict[str, str]:
    """Title + body for the status callout (informational, not legal)."""
    mapping = {
        "no_contract": {
            "title": _("No contract on file"),
            "description": _(
                "Your brokerage has not issued an agreement yet. Contact "
                "your branch manager or operations team if you expected one."
            ),
            "ctaLabel": _("Open profile"),
            "ctaKind": "profile",
        },
        "generating": {
            "title": _("Preparing your agreement"),
            "description": _(
                "Your contract PDF is being generated. This page will show "
                "the document when it is ready — refresh in a moment."
            ),
            "ctaLabel": _("Refresh"),
            "ctaKind": "refresh",
        },
        "generation_failed": {
            "title": _("Document generation failed"),
            "description": _(
                "We could not prepare your agreement PDF. Contact your "
                "branch manager or operations support so they can retry."
            ),
            "ctaLabel": _("Open profile"),
            "ctaKind": "profile",
        },
        "awaiting_signature": {
            "title": _("Signature required"),
            "description": _(
                "Review the agreement PDF and summary below. Sign when you "
                "are ready — the PDF is the controlling document."
            ),
            "ctaLabel": _("Sign contract"),
            "ctaKind": "sign",
        },
        "signed": {
            "title": _("Signed — activation pending"),
            "description": _(
                "Your signature is on file. Operations will activate the "
                "agreement when brokerage checks are complete."
            ),
            "ctaLabel": "",
            "ctaKind": "",
        },
        "active": {
            "title": _("Your agreement is active"),
            "description": _(
                "These terms govern your current relationship. Download the "
                "PDF for the complete legal text."
            ),
            "ctaLabel": "",
            "ctaKind": "",
        },
        "expired": {
            "title": _("This agreement has expired"),
            "description": _(
                "Effective dates for this version have ended. Contact your "
                "branch if you need a renewal or replacement."
            ),
            "ctaLabel": _("Open profile"),
            "ctaKind": "profile",
        },
        "superseded": {
            "title": _("This version was replaced"),
            "description": _(
                "A newer agreement superseded this version. Open the current "
                "contract from the history list when available."
            ),
            "ctaLabel": _("View current"),
            "ctaKind": "current",
        },
        "terminated": {
            "title": _("This agreement was terminated"),
            "description": _(
                "This version is no longer in force. Contact your branch "
                "manager with questions about standing."
            ),
            "ctaLabel": _("Open profile"),
            "ctaKind": "profile",
        },
    }
    return mapping.get(state, mapping["no_contract"])


def is_signable(contract: AgentContract | None) -> bool:
    """True only for the exact recipient version that may enter signing."""
    if contract is None:
        return False
    return (
        contract.status in SIGNABLE_STATUSES and contract.generated_pdf_id is not None
    )


def artifact_urls(contract: AgentContract) -> dict[str, str | None]:
    """Authorized stream URLs for the current generated or signed PDF."""
    artifact = contract.signed_pdf or contract.generated_pdf
    if artifact is None:
        return {"previewUrl": None, "downloadUrl": None, "artifactKind": None}
    kwargs = {
        "public_id": contract.public_id,
        "artifact_public_id": artifact.public_id,
    }
    download = reverse("agent_contract_artifact_download", kwargs=kwargs)
    preview = reverse("my_contract_artifact_preview", kwargs=kwargs)
    return {
        "previewUrl": preview,
        "downloadUrl": download,
        "artifactKind": artifact.kind,
    }


def serialize_recipient_contract(
    viewer: User, contract: AgentContract
) -> dict[str, Any]:
    """Minimal camelCase props for the recipient — never internal notes."""
    office_snap = contract.office_snapshot or {}
    party_snap = contract.party_snapshot or {}
    urls = artifact_urls(contract)
    payload: dict[str, Any] = {
        "publicId": str(contract.public_id),
        "familyId": str(contract.family_id),
        "versionNumber": contract.version_number,
        "changeKind": contract.change_kind,
        "changeKindLabel": change_kind_label(contract.change_kind),
        "changeSummary": contract.change_summary or "",
        "status": contract.status,
        "statusLabel": str(status_label(contract.status)),
        "statusTone": status_tone(contract.status),
        "effectiveOn": contract.effective_on.isoformat(),
        "expiresOn": (contract.expires_on.isoformat() if contract.expires_on else None),
        "officeName": office_snap.get("name")
        or (contract.office.name if contract.office_id else ""),
        "partyDisplayName": party_snap.get("displayName")
        or contract.recipient.preferred_display_name(),
        "sentAt": _dt(contract.sent_at),
        "viewedAt": _dt(contract.viewed_at),
        "signedAt": _dt(contract.signed_at),
        "activatedAt": _dt(contract.activated_at),
        "supersededAt": _dt(contract.superseded_at),
        "expiredAt": _dt(contract.expired_at),
        "terminatedAt": _dt(contract.terminated_at),
        "updatedAt": _dt(contract.updated_at),
        "expectedVersion": contract_version(contract),
        "generatedPdf": _artifact_meta(contract.generated_pdf),
        "signedPdf": _artifact_meta(contract.signed_pdf),
        "signedPdfFinalization": _signed_pdf_finalization(contract),
        "previewUrl": urls["previewUrl"],
        "downloadUrl": urls["downloadUrl"],
        "artifactKind": urls["artifactKind"],
        "verifyUrl": (
            reverse(
                "my_contract_signed_pdf_verify",
                kwargs={"public_id": contract.public_id},
            )
            if ContractSignature.objects.filter(contract_id=contract.pk).exists()
            else None
        ),
        "isCurrentFocus": True,
        "amendsPublicId": _related_public_id(contract.amends),
        "supersedesPublicId": _related_public_id(contract.supersedes),
        "isGoverning": contract.status == ContractStatus.ACTIVE,
    }
    if _can_view_commission(viewer, contract):
        payload["commission"] = _commission_block(contract)
        payload["summaryLines"] = _summary_lines(contract)
        payload["specialArrangements"] = contract.special_arrangements or (
            (contract.terms_snapshot or {}).get("specialArrangements") or ""
        )
        payload["addendaReferences"] = list(
            contract.addenda_references
            or (contract.terms_snapshot or {}).get("addendaReferences")
            or []
        )
        payload["annualCapAmount"] = _dec(contract.annual_cap_amount) or (
            (contract.terms_snapshot or {}).get("annualCapAmount")
        )
    return payload


def _signed_pdf_finalization(contract: AgentContract) -> dict[str, Any] | None:
    signature = (
        ContractSignature.objects.filter(contract_id=contract.pk)
        .only("finalization_status", "finalization_error", "public_id")
        .first()
    )
    if signature is None:
        return None
    return {
        "status": signature.finalization_status,
        "error": signature.finalization_error or None,
        "signaturePublicId": str(signature.public_id),
        "ready": signature.finalization_status
        == ContractSignature.FinalizationStatus.READY
        and bool(contract.signed_pdf_id),
    }


def _commission_block(contract: AgentContract) -> dict[str, Any]:
    snap = contract.terms_snapshot or {}
    mentor = snap.get("mentor") or {}
    referral = snap.get("referral") or {}
    return {
        "agentSplitPercent": snap.get("agentSplitPercent")
        or _dec(contract.agent_split_percent),
        "officeSplitPercent": snap.get("officeSplitPercent")
        or _dec(contract.office_split_percent),
        "transactionFeeAmount": snap.get("transactionFeeAmount")
        or _dec(contract.transaction_fee_amount),
        "transactionFeePercent": snap.get("transactionFeePercent")
        or _dec(contract.transaction_fee_percent),
        "annualCapAmount": snap.get("annualCapAmount")
        or _dec(contract.annual_cap_amount),
        "mentor": {
            "percent": mentor.get("percent") or _dec(contract.mentor_percent),
            "fixedAmount": mentor.get("fixedAmount")
            or _dec(contract.mentor_fixed_amount),
            "capAmount": mentor.get("capAmount") or _dec(contract.mentor_cap_amount),
            "basis": mentor.get("basis") or contract.mentor_basis or "",
            "notes": mentor.get("notes") or contract.mentor_notes or "",
        },
        "referral": {
            "percent": referral.get("percent") or _dec(contract.referral_percent),
            "fixedAmount": referral.get("fixedAmount")
            or _dec(contract.referral_fixed_amount),
            "capAmount": referral.get("capAmount")
            or _dec(contract.referral_cap_amount),
            "basis": referral.get("basis") or contract.referral_basis or "",
            "notes": referral.get("notes") or contract.referral_notes or "",
        },
    }


def _summary_lines(contract: AgentContract) -> list[str]:
    try:
        return summarize_terms_for_display(terms_input_from_contract(contract))
    except Exception:  # noqa: BLE001 — display falls back to empty
        return []


def serialize_history_row(
    viewer: User, contract: AgentContract, *, focus_id: int
) -> dict[str, Any]:
    """One family/history entry the recipient may open."""
    href = reverse("my_contract") + (
        f"?v={contract.public_id}" if contract.pk != focus_id else ""
    )
    row = serialize_family_history_row(contract, focus_id=focus_id, workspace_href=href)
    # Recipient surface uses the same relationship labels; href stays
    # on My Contract rather than the admin workspace.
    row["href"] = href
    return row


def family_history(viewer: User, focus: AgentContract) -> list[dict[str, Any]]:
    """Superseded agreements and amendments in the same family."""
    rows = (
        recipient_visible_queryset(viewer)
        .filter(family_id=focus.family_id)
        .order_by("-version_number", "-pk")
    )
    return [serialize_history_row(viewer, row, focus_id=focus.pk) for row in rows]


def mark_viewed_after_access(actor: User, contract: AgentContract) -> AgentContract:
    """Idempotent ``mark_viewed`` once the recipient has authorized content.

    Call only from the My Contract page (or artifact stream), never from a
    dashboard preload that does not render the agreement.
    """
    if contract.status != ContractStatus.SENT:
        return contract
    if actor.pk != contract.recipient_id:
        return contract
    # Content is ready: PDF exists, or generation failed (still "content").
    if not contract.generated_pdf_id and contract.status == ContractStatus.SENT:
        # Generating — do not mark viewed until the document is available.
        return contract
    return transition(
        actor=actor,
        contract=contract,
        action="mark_viewed",
        expected_version=contract_version(contract),
    )


def my_contract_page_payload(
    actor: User,
    *,
    version_public_id: UUID | None = None,
    record_viewed: bool = True,
) -> dict[str, Any]:
    """Everything the MyContract Inertia page needs for one actor."""
    focus = select_current_contract(actor, version_public_id=version_public_id)
    if (
        record_viewed
        and focus is not None
        and focus.status == ContractStatus.SENT
        and focus.generated_pdf_id
    ):
        focus = mark_viewed_after_access(actor, focus)
        focus = recipient_visible_queryset(actor).filter(pk=focus.pk).first() or focus

    state = presentation_state(focus)
    action = next_action_copy(state)
    can_view_commission = bool(
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, VIEW_OWN_COMMISSION)
    )
    # Signing ceremony (P1-042) when Hub signing is configured.
    can_sign = is_signable(focus)
    signing_ready = signing_is_ready()

    contract_payload = (
        serialize_recipient_contract(actor, focus) if focus is not None else None
    )
    history = family_history(actor, focus) if focus is not None else []

    current = select_current_contract(actor)
    current_href = reverse("my_contract")
    if current is not None and focus is not None and current.pk != focus.pk:
        action = {**action}
        if state == "superseded":
            action["ctaKind"] = "current"
            action["ctaHref"] = current_href

    empty = None
    if focus is None:
        empty = {
            "kind": "no_contract",
            "title": action["title"],
            "description": action["description"],
        }

    return {
        "state": state,
        "nextAction": {
            "title": action["title"],
            "description": action["description"],
            "ctaLabel": action.get("ctaLabel") or "",
            "ctaKind": action.get("ctaKind") or "",
            "ctaHref": action.get("ctaHref")
            or (
                reverse("profile")
                if action.get("ctaKind") == "profile"
                else current_href
                if action.get("ctaKind") in {"refresh", "current"}
                else ""
            ),
        },
        "contract": contract_payload,
        "history": history,
        "capabilities": {
            "canViewCommission": can_view_commission
            and (focus is None or _can_view_commission(actor, focus)),
            "canSign": can_sign,
            "signingReady": signing_ready,
        },
        "disclaimer": _(
            "Summary values are informational. If anything disagrees with the "
            "PDF agreement, the PDF controls."
        ),
        "empty": empty,
    }
