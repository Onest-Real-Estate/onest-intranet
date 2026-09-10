"""Recipient contract signing ceremony (Hub-native).

Creates short-lived intents, completes via authenticated Hub POST with
immutable signature records, and queues asynchronous final signed-PDF
generation. Lifecycle ``mark_signed`` runs once the durable signature exists —
final PDF failure retains the signature for idempotent regeneration.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.field_layout import (
    COMPANY_ROLE,
    SIGNER_ROLE,
    FieldType,
    agent_fields,
    company_fields,
    normalize_field_layout,
)
from apps.contract.lifecycle import (
    StaleContractVersion,
    TransitionRefused,
    contract_version,
    transition,
)
from apps.contract.models import (
    AgentContract,
    ContractArtifact,
    ContractSignature,
    ContractSigningIntent,
)
from apps.contract.my_contract import (
    is_signable,
    recipient_visible_queryset,
    select_current_contract,
)
from apps.contract.pdf_signing import (
    appearance_checksum,
    decode_data_url_image,
    require_signing_cert_or_raise,
    signing_is_ready,
)
from apps.contract.signing_disclosure import (
    DISCLOSURE_VERSION,
    disclosure_payload,
)
from apps.contract.statuses import ContractStatus, status_label
from apps.contract.template_security import checksum_of
from apps.user.models import User

logger = logging.getLogger(__name__)

MEDIA_TYPE_PDF = "application/pdf"
UA_TRUNCATE = 256


class SigningCeremonyError(ValidationError):
    """User-facing recovery error for the signing ceremony."""


@dataclass(frozen=True)
class RequestMeta:
    session_key: str
    ip_address: str
    user_agent: str


def hash_session_key(session_key: str) -> str:
    raw = (session_key or "").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def hash_ip(ip_address: str) -> str:
    value = (ip_address or "").strip()
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_user_agent(user_agent: str) -> str:
    value = (user_agent or "")[:UA_TRUNCATE]
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _party_display_name(contract: AgentContract, actor: User) -> str:
    snap = contract.party_snapshot or {}
    for key in ("legalName", "displayName", "fullName"):
        value = snap.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    first = (snap.get("legalFirstName") or "").strip()
    last = (snap.get("legalLastName") or "").strip()
    combined = f"{first} {last}".strip()
    if combined:
        return combined
    return (actor.get_full_name() or actor.email or "").strip() or actor.email


def _read_artifact_bytes(artifact: ContractArtifact) -> bytes:
    artifact.file.open("rb")
    try:
        return artifact.file.read()
    finally:
        artifact.file.close()


def _expire_stale_intents(contract: AgentContract, *, now) -> None:
    ContractSigningIntent.objects.filter(
        contract=contract,
        status=ContractSigningIntent.Status.PENDING,
        expires_at__lte=now,
    ).update(status=ContractSigningIntent.Status.EXPIRED)


def _cancel_pending_intents(
    contract: AgentContract,
    *,
    signer_role: str | None = None,
) -> None:
    qs = ContractSigningIntent.objects.filter(
        contract=contract,
        status=ContractSigningIntent.Status.PENDING,
    )
    if signer_role:
        qs = qs.filter(signer_role=signer_role)
    qs.update(status=ContractSigningIntent.Status.CANCELLED)


def _role_field_payload(contract: AgentContract, *, role: str) -> list[dict[str, Any]]:
    version = contract.template_version
    layout = normalize_field_layout(version.field_layout or []) if version else []
    items = company_fields(layout) if role == COMPANY_ROLE else agent_fields(layout)
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "type": item["type"],
            "role": item["role"],
            "page": item["page"],
            "x": item["x"],
            "y": item["y"],
            "w": item["w"],
            "h": item["h"],
        }
        for item in items
    ]


def _agent_field_payload(contract: AgentContract) -> list[dict[str, Any]]:
    return _role_field_payload(contract, role=SIGNER_ROLE)


def _review_pdf_url(contract: AgentContract, artifact: ContractArtifact) -> str:
    return reverse(
        "my_contract_artifact_preview",
        kwargs={
            "public_id": contract.public_id,
            "artifact_public_id": artifact.public_id,
        },
    )


def _company_review_pdf_url(contract: AgentContract, artifact: ContractArtifact) -> str:
    return reverse(
        "agent_contract_artifact_download",
        kwargs={"public_id": contract.public_id},
    )


def ceremony_page_payload(
    actor: User,
    *,
    version_public_id: UUID | None = None,
) -> dict[str, Any]:
    """Inertia props for GET /my-contract/sign."""
    focus = select_current_contract(actor, version_public_id=version_public_id)
    ready = signing_is_ready()
    can_sign = is_signable(focus) and ready
    recovery = None
    if focus is None:
        recovery = {
            "code": "no_contract",
            "message": str(_("No issued contract is available to sign.")),
        }
    elif not ready:
        recovery = {
            "code": "signing_unavailable",
            "message": str(
                _("Electronic signing is temporarily unavailable. Try again later.")
            ),
        }
    elif not is_signable(focus):
        recovery = {
            "code": "not_signable",
            "message": str(
                _(
                    "This agreement cannot be signed right now. Refresh My Contract "
                    "for the current status."
                )
            ),
        }

    artifact = focus.generated_pdf if focus is not None else None
    return {
        "canSign": can_sign,
        "signingReady": ready,
        "recovery": recovery,
        "disclosure": disclosure_payload(),
        "contract": None
        if focus is None
        else {
            "publicId": str(focus.public_id),
            "versionNumber": focus.version_number,
            "status": focus.status,
            "statusLabel": status_label(focus.status),
            "effectiveOn": focus.effective_on.isoformat(),
            "expectedVersion": contract_version(focus),
            "artifactChecksum": artifact.checksum if artifact else "",
            "partyDisplayName": _party_display_name(focus, actor),
            "signerEmail": actor.email,
        },
        "ceremony": None,
        "errors": {"fields": {}, "form": []},
    }


@transaction.atomic
def start_signing(
    actor: User,
    *,
    contract_public_id: UUID,
    expected_version: str,
    consent_accepted: bool,
    disclosure_version: str,
    request_meta: RequestMeta,
) -> dict[str, Any]:
    """Create a signing intent for the Hub signature pad ceremony."""
    if not signing_is_ready():
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "Electronic signing is temporarily unavailable. "
                            "Try again later."
                        )
                    )
                ]
            }
        )
    if not consent_accepted:
        raise SigningCeremonyError(
            {
                "consentAccepted": str(
                    _("You must acknowledge the disclosure to continue.")
                )
            }
        )
    if disclosure_version != DISCLOSURE_VERSION:
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "The disclosure text changed. Refresh this page and "
                            "acknowledge the current disclosure."
                        )
                    )
                ]
            }
        )
    if not (request_meta.session_key or "").strip():
        raise SigningCeremonyError(
            {"form": [str(_("Your session is missing. Sign in again and retry."))]}
        )

    scope = recipient_visible_queryset(actor)
    contract = (
        scope.select_for_update(of=("self",))
        .select_related("template_version", "generated_pdf")
        .filter(public_id=contract_public_id)
        .first()
    )
    if contract is None:
        raise PermissionDenied(_("Contract is not available for signing."))
    if actor.pk != contract.recipient_id:
        raise PermissionDenied(_("Only the named recipient can sign this contract."))

    if contract_version(contract) != (expected_version or ""):
        raise StaleContractVersion()
    if not is_signable(contract):
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "This agreement is not eligible to sign. Refresh My "
                            "Contract for the current status."
                        )
                    )
                ]
            }
        )

    artifact = (
        ContractArtifact.objects.filter(pk=contract.generated_pdf_id).first()
        if contract.generated_pdf_id
        else None
    )
    if artifact is None:
        raise SigningCeremonyError(
            {"form": [str(_("The review PDF is not ready yet. Try again shortly."))]}
        )

    now = timezone.now()
    _expire_stale_intents(contract, now=now)
    _cancel_pending_intents(contract, signer_role=SIGNER_ROLE)

    pdf_bytes = _read_artifact_bytes(artifact)
    live_checksum = checksum_of(pdf_bytes)
    if live_checksum != artifact.checksum.lower():
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "The agreement PDF changed since it was issued. "
                            "Contact your brokerage before signing."
                        )
                    )
                ]
            }
        )

    fields = _agent_field_payload(contract)
    if not any(f["type"] == FieldType.SIGNATURE for f in fields):
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "This agreement is missing a signature field. "
                            "Contact your brokerage."
                        )
                    )
                ]
            }
        )
    if not any(f["type"] == FieldType.DATE for f in fields):
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "This agreement is missing a date field. "
                            "Contact your brokerage."
                        )
                    )
                ]
            }
        )

    ttl = max(60, int(getattr(settings, "CONTRACT_SIGNING_INTENT_TTL_SECONDS", 900)))
    expires_at = now + timedelta(seconds=ttl)
    intent = ContractSigningIntent(
        contract=contract,
        actor=actor,
        signer_role=ContractSigningIntent.SignerRole.AGENT,
        contract_version=expected_version,
        artifact=artifact,
        artifact_checksum=artifact.checksum.lower(),
        session_key_hash=hash_session_key(request_meta.session_key),
        request_ip_hash=hash_ip(request_meta.ip_address),
        request_ua_hash=hash_user_agent(request_meta.user_agent),
        disclosure_version=DISCLOSURE_VERSION,
        consent_accepted_at=now,
        status=ContractSigningIntent.Status.PENDING,
        expires_at=expires_at,
    )
    intent.full_clean()
    intent.save()

    log_event(
        "contract.signing_intent.created",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type="contract.AgentContract",
            target_id=str(contract.public_id),
            target_label=actor.email,
            target_snapshot={
                "intent_id": str(intent.public_id),
                "disclosure_version": DISCLOSURE_VERSION,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="contract",
        office_id=getattr(contract.office, "stable_key", "") or "",
        metadata={
            "ip_hash": hash_ip(request_meta.ip_address),
            "ua_hash": hash_user_agent(request_meta.user_agent),
        },
    )

    return {
        **ceremony_page_payload(actor, version_public_id=contract.public_id),
        "ceremony": {
            "intentPublicId": str(intent.public_id),
            "expiresAt": expires_at.isoformat(),
            "reviewPdfUrl": _review_pdf_url(contract, artifact),
            "agentFields": fields,
        },
        "errors": {"fields": {}, "form": []},
    }


def signing_status_payload(
    actor: User,
    *,
    contract_public_id: UUID | None = None,
    intent_public_id: UUID | None = None,
) -> dict[str, Any]:
    """Pollable status for the success gate (signature row must exist)."""
    scope = recipient_visible_queryset(actor)
    contract = None
    if intent_public_id is not None:
        intent = (
            ContractSigningIntent.objects.select_related("contract")
            .filter(public_id=intent_public_id, actor=actor)
            .first()
        )
        if intent is not None and scope.filter(pk=intent.contract_id).exists():
            contract = intent.contract
    if contract is None and contract_public_id is not None:
        contract = scope.filter(public_id=contract_public_id).first()
    if contract is None:
        contract = select_current_contract(actor)
    if contract is None:
        return {
            "signed": False,
            "status": None,
            "signaturePublicId": None,
            "contractPublicId": None,
            "finalArtifactReady": False,
            "finalizationStatus": None,
        }

    signature = ContractSignature.objects.filter(
        contract=contract,
        signer_role=ContractSignature.SignerRole.AGENT,
    ).first()
    final_ready = bool(
        signature is not None
        and signature.finalization_status == ContractSignature.FinalizationStatus.READY
        and (signature.artifact_id or contract.signed_pdf_id)
    )
    return {
        "signed": signature is not None
        and contract.status in {ContractStatus.SIGNED, ContractStatus.ACTIVE},
        "status": contract.status,
        "signaturePublicId": str(signature.public_id) if signature else None,
        "contractPublicId": str(contract.public_id),
        "finalArtifactReady": final_ready,
        "finalizationStatus": (
            signature.finalization_status if signature is not None else None
        ),
    }


def _queue_signed_pdf_generation(signature_id: int) -> None:
    from apps.contract.tasks import generate_signed_contract_pdf

    generate_signed_contract_pdf.delay(signature_id)


@transaction.atomic
def complete_signing(
    actor: User,
    *,
    intent_public_id: UUID,
    signature_data_url: str,
    signed_date: str,
    initials_data_url: str = "",
    text_values: dict[str, str] | None = None,
    request_meta: RequestMeta,
) -> dict[str, Any]:
    """Idempotent Hub completion: durable signature + mark_signed + queue final PDF."""
    require_signing_cert_or_raise()

    intent = (
        ContractSigningIntent.objects.select_related(
            "contract",
            "contract__template_version",
            "actor",
            "artifact",
        )
        .filter(public_id=intent_public_id, actor=actor)
        .first()
    )
    if intent is None:
        raise PermissionDenied(_("Signing intent is not available."))

    locked = (
        AgentContract.objects.select_for_update(of=("self",))
        .select_related(
            "template_version",
            "generated_pdf",
            "office",
        )
        .get(pk=intent.contract_id)
    )

    existing = ContractSignature.objects.filter(
        contract_id=locked.pk,
        signer_role=ContractSignature.SignerRole.AGENT,
    ).first()
    if existing is not None:
        if (
            existing.finalization_status != ContractSignature.FinalizationStatus.READY
            and not existing.artifact_id
        ):
            existing_pk = existing.pk
            transaction.on_commit(lambda: _queue_signed_pdf_generation(existing_pk))
        return {
            "ok": True,
            "idempotent": True,
            "signaturePublicId": str(existing.public_id),
            "signed": True,
            "finalArtifactReady": existing.finalization_status
            == ContractSignature.FinalizationStatus.READY,
        }

    now = timezone.now()
    if intent.status != ContractSigningIntent.Status.PENDING:
        if locked.status in {ContractStatus.SIGNED, ContractStatus.ACTIVE}:
            return {"ok": True, "idempotent": True, "signed": True}
        raise TransitionRefused(str(_("Signing intent is no longer pending.")))
    if intent.expires_at <= now:
        intent.status = ContractSigningIntent.Status.EXPIRED
        intent.save(update_fields=["status"])
        raise TransitionRefused(str(_("Signing intent expired. Start again.")))

    if intent.signer_role != ContractSigningIntent.SignerRole.AGENT:
        raise PermissionDenied(_("This signing intent is not for the agent ceremony."))

    if locked.status not in {ContractStatus.SENT, ContractStatus.VIEWED}:
        raise TransitionRefused(str(_("Contract is not in a signable state.")))
    if locked.recipient_id != intent.actor_id:
        raise PermissionDenied(_("Signing intent recipient mismatch."))
    if intent.session_key_hash != hash_session_key(request_meta.session_key):
        raise PermissionDenied(
            _("Signing session does not match this browser session.")
        )

    artifact = (
        ContractArtifact.objects.filter(pk=locked.generated_pdf_id).first()
        if locked.generated_pdf_id
        else None
    )
    if (
        artifact is None
        or artifact.checksum.lower() != intent.artifact_checksum.lower()
    ):
        raise TransitionRefused(
            str(_("Agreement PDF checksum no longer matches the signing intent."))
        )

    review_bytes = _read_artifact_bytes(artifact)
    live_checksum = checksum_of(review_bytes)
    if live_checksum != intent.artifact_checksum.lower():
        raise TransitionRefused(
            str(_("Agreement PDF checksum no longer matches the signing intent."))
        )

    date_value = (signed_date or "").strip()
    if not date_value:
        raise SigningCeremonyError(
            {"signedDate": str(_("Enter the signature date on the agreement."))}
        )

    signature_png = decode_data_url_image(signature_data_url)
    if len(signature_png) < 32:
        raise SigningCeremonyError(
            {"signature": str(_("Draw or type your signature before submitting."))}
        )
    initials_png = (
        decode_data_url_image(initials_data_url) if initials_data_url else b""
    )

    # Company ceremony must already be on file before the agent can finalize.
    company_sig = ContractSignature.objects.filter(
        contract_id=locked.pk,
        signer_role=ContractSignature.SignerRole.COMPANY,
    ).first()
    if company_sig is None:
        raise TransitionRefused(
            str(_("Company signature is required before the agent can sign."))
        )

    expected = contract_version(locked)
    appearance_digest = appearance_checksum(signature_png)

    signature = ContractSignature(
        contract=locked,
        intent=intent,
        signer=intent.actor,
        signer_role=ContractSignature.SignerRole.AGENT,
        artifact=None,
        signed_at=now,
        disclosure_version=intent.disclosure_version,
        signature_method=ContractSignature.Method.HUB_EMBEDDED,
        appearance_checksum=appearance_digest,
        source_checksum=intent.artifact_checksum.lower(),
        signed_date_value=date_value,
        agent_text_values=dict(text_values or {}),
        finalization_status=ContractSignature.FinalizationStatus.PENDING,
        request_ip_hash=intent.request_ip_hash,
        request_ua_hash=intent.request_ua_hash,
    )
    signature.appearance_file.save(
        f"appearance-{signature.public_id}.png",
        ContentFile(signature_png),
        save=False,
    )
    if initials_png:
        signature.initials_file.save(
            f"initials-{signature.public_id}.png",
            ContentFile(initials_png),
            save=False,
        )
    signature.full_clean()
    signature.save()

    intent.status = ContractSigningIntent.Status.CONSUMED
    intent.consumed_at = now
    intent.save(update_fields=["status", "consumed_at"])

    transition(
        actor=intent.actor,
        contract=locked,
        action="mark_signed",
        expected_version=expected,
    )

    log_event(
        "contract.signature.created",
        actor=actor_from_user(intent.actor),
        target=AuditTarget(
            target_type="contract.AgentContract",
            target_id=str(locked.public_id),
            target_label=intent.actor.email,
            target_snapshot={
                "signature_id": str(signature.public_id),
                "intent_id": str(intent.public_id),
                "disclosure_version": intent.disclosure_version,
                "method": signature.signature_method,
                "source_checksum": signature.source_checksum,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="contract",
        office_id=getattr(locked.office, "stable_key", "") or "",
    )

    signature_pk = signature.pk
    transaction.on_commit(lambda: _queue_signed_pdf_generation(signature_pk))

    return {
        "ok": True,
        "signed": True,
        "signaturePublicId": str(signature.public_id),
        "finalArtifactReady": False,
    }


def company_ceremony_page_payload(
    actor: User, *, contract_public_id: UUID
) -> dict[str, Any]:
    """Inertia props for the named company signatory ceremony."""
    contract = (
        AgentContract.objects.select_related(
            "template_version",
            "generated_pdf",
            "recipient",
            "company_signatory",
            "office",
        )
        .filter(public_id=contract_public_id)
        .first()
    )
    if contract is None:
        raise PermissionDenied(_("Contract is not available."))
    if actor.pk != contract.company_signatory_id and not getattr(
        actor, "is_superuser", False
    ):
        raise PermissionDenied(
            _("Only the named company signatory can open this page.")
        )

    ready = signing_is_ready()
    can_sign = (
        contract.status == ContractStatus.AWAITING_COMPANY_SIGNATURE
        and bool(contract.generated_pdf_id)
        and ready
    )
    recovery = None
    if not ready:
        recovery = {
            "code": "signing_unavailable",
            "message": str(
                _("Electronic signing is temporarily unavailable. Try again later.")
            ),
        }
    elif contract.status != ContractStatus.AWAITING_COMPANY_SIGNATURE:
        recovery = {
            "code": "not_signable",
            "message": str(
                _("This agreement is not awaiting a company signature right now.")
            ),
        }
    elif not contract.generated_pdf_id:
        recovery = {
            "code": "pdf_pending",
            "message": str(_("The review PDF is still generating. Try again shortly.")),
        }

    artifact = contract.generated_pdf
    return {
        "canSign": can_sign,
        "signingReady": ready,
        "recovery": recovery,
        "disclosure": disclosure_payload(),
        "signerRole": COMPANY_ROLE,
        "contract": {
            "publicId": str(contract.public_id),
            "versionNumber": contract.version_number,
            "status": contract.status,
            "statusLabel": status_label(contract.status),
            "effectiveOn": contract.effective_on.isoformat(),
            "expectedVersion": contract_version(contract),
            "artifactChecksum": artifact.checksum if artifact else "",
            "partyDisplayName": _party_display_name(contract, contract.recipient),
            "recipientName": contract.recipient.preferred_display_name(),
            "signerEmail": actor.email,
            "workspaceUrl": reverse(
                "agent_contract_workspace", kwargs={"public_id": contract.public_id}
            ),
        },
        "ceremony": None,
        "errors": {"fields": {}, "form": []},
    }


@transaction.atomic
def start_company_signing(
    actor: User,
    *,
    contract_public_id: UUID,
    expected_version: str,
    consent_accepted: bool,
    disclosure_version: str,
    request_meta: RequestMeta,
) -> dict[str, Any]:
    """Create a Company-role signing intent for the named officer."""
    if not signing_is_ready():
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "Electronic signing is temporarily unavailable. "
                            "Try again later."
                        )
                    )
                ]
            }
        )
    if not consent_accepted:
        raise SigningCeremonyError(
            {
                "consentAccepted": str(
                    _("You must acknowledge the disclosure to continue.")
                )
            }
        )
    if disclosure_version != DISCLOSURE_VERSION:
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "The disclosure text changed. Refresh this page and "
                            "acknowledge the current disclosure."
                        )
                    )
                ]
            }
        )
    if not (request_meta.session_key or "").strip():
        raise SigningCeremonyError(
            {"form": [str(_("Your session is missing. Sign in again and retry."))]}
        )

    contract = (
        AgentContract.objects.select_for_update(of=("self",))
        .select_related("template_version", "generated_pdf", "recipient", "office")
        .filter(public_id=contract_public_id)
        .first()
    )
    if contract is None:
        raise PermissionDenied(_("Contract is not available for signing."))
    if actor.pk != contract.company_signatory_id:
        raise PermissionDenied(_("Only the named company signatory can sign."))

    if contract_version(contract) != (expected_version or ""):
        raise StaleContractVersion()
    if contract.status != ContractStatus.AWAITING_COMPANY_SIGNATURE:
        raise SigningCeremonyError(
            {"form": [str(_("This agreement is not awaiting a company signature."))]}
        )

    existing = ContractSignature.objects.filter(
        contract_id=contract.pk,
        signer_role=ContractSignature.SignerRole.COMPANY,
    ).first()
    if existing is not None:
        raise SigningCeremonyError(
            {"form": [str(_("Company signature is already recorded."))]}
        )

    artifact = (
        ContractArtifact.objects.filter(pk=contract.generated_pdf_id).first()
        if contract.generated_pdf_id
        else None
    )
    if artifact is None:
        raise SigningCeremonyError(
            {"form": [str(_("The review PDF is not ready yet. Try again shortly."))]}
        )

    now = timezone.now()
    _expire_stale_intents(contract, now=now)
    _cancel_pending_intents(contract, signer_role=COMPANY_ROLE)

    pdf_bytes = _read_artifact_bytes(artifact)
    live_checksum = checksum_of(pdf_bytes)
    if live_checksum != artifact.checksum.lower():
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "The agreement PDF changed since it was issued. "
                            "Contact operations before signing."
                        )
                    )
                ]
            }
        )

    fields = _role_field_payload(contract, role=COMPANY_ROLE)
    if not any(f["type"] == FieldType.SIGNATURE for f in fields):
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "This agreement is missing a Company signature field. "
                            "Contact operations."
                        )
                    )
                ]
            }
        )
    if not any(f["type"] == FieldType.DATE for f in fields):
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "This agreement is missing a Company date field. "
                            "Contact operations."
                        )
                    )
                ]
            }
        )

    ttl = max(60, int(getattr(settings, "CONTRACT_SIGNING_INTENT_TTL_SECONDS", 900)))
    expires_at = now + timedelta(seconds=ttl)
    intent = ContractSigningIntent(
        contract=contract,
        actor=actor,
        signer_role=ContractSigningIntent.SignerRole.COMPANY,
        contract_version=expected_version,
        artifact=artifact,
        artifact_checksum=artifact.checksum.lower(),
        session_key_hash=hash_session_key(request_meta.session_key),
        request_ip_hash=hash_ip(request_meta.ip_address),
        request_ua_hash=hash_user_agent(request_meta.user_agent),
        disclosure_version=DISCLOSURE_VERSION,
        consent_accepted_at=now,
        status=ContractSigningIntent.Status.PENDING,
        expires_at=expires_at,
    )
    intent.full_clean()
    intent.save()

    log_event(
        "contract.company_signing_intent.created",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type="contract.AgentContract",
            target_id=str(contract.public_id),
            target_label=actor.email,
            target_snapshot={
                "intent_id": str(intent.public_id),
                "disclosure_version": DISCLOSURE_VERSION,
                "signer_role": COMPANY_ROLE,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="contract",
        office_id=getattr(contract.office, "stable_key", "") or "",
    )

    return {
        **company_ceremony_page_payload(actor, contract_public_id=contract.public_id),
        "ceremony": {
            "intentPublicId": str(intent.public_id),
            "expiresAt": expires_at.isoformat(),
            "reviewPdfUrl": reverse(
                "agent_contract_company_sign_preview",
                kwargs={"public_id": contract.public_id},
            ),
            "agentFields": fields,
        },
        "errors": {"fields": {}, "form": []},
    }


@transaction.atomic
def complete_company_signing(
    actor: User,
    *,
    intent_public_id: UUID,
    signature_data_url: str,
    signed_date: str,
    initials_data_url: str = "",
    text_values: dict[str, str] | None = None,
    request_meta: RequestMeta,
) -> dict[str, Any]:
    """Record Company signature and release the contract to the agent (`sent`)."""
    require_signing_cert_or_raise()

    intent = (
        ContractSigningIntent.objects.select_related(
            "contract",
            "contract__template_version",
            "actor",
            "artifact",
        )
        .filter(public_id=intent_public_id, actor=actor)
        .first()
    )
    if intent is None:
        raise PermissionDenied(_("Signing intent is not available."))
    if intent.signer_role != ContractSigningIntent.SignerRole.COMPANY:
        raise PermissionDenied(_("This signing intent is not for company signing."))

    locked = (
        AgentContract.objects.select_for_update(of=("self",))
        .select_related("template_version", "generated_pdf", "office")
        .get(pk=intent.contract_id)
    )

    existing = ContractSignature.objects.filter(
        contract_id=locked.pk,
        signer_role=ContractSignature.SignerRole.COMPANY,
    ).first()
    if existing is not None:
        return {
            "ok": True,
            "idempotent": True,
            "signaturePublicId": str(existing.public_id),
            "companySigned": True,
            "status": locked.status,
        }

    now = timezone.now()
    if intent.status != ContractSigningIntent.Status.PENDING:
        raise TransitionRefused(str(_("Signing intent is no longer pending.")))
    if intent.expires_at <= now:
        intent.status = ContractSigningIntent.Status.EXPIRED
        intent.save(update_fields=["status"])
        raise TransitionRefused(str(_("Signing intent expired. Start again.")))

    if locked.status != ContractStatus.AWAITING_COMPANY_SIGNATURE:
        raise TransitionRefused(str(_("Contract is not awaiting company signature.")))
    if locked.company_signatory_id != intent.actor_id:
        raise PermissionDenied(_("Signing intent signatory mismatch."))
    if intent.session_key_hash != hash_session_key(request_meta.session_key):
        raise PermissionDenied(
            _("Signing session does not match this browser session.")
        )

    artifact = (
        ContractArtifact.objects.filter(pk=locked.generated_pdf_id).first()
        if locked.generated_pdf_id
        else None
    )
    if (
        artifact is None
        or artifact.checksum.lower() != intent.artifact_checksum.lower()
    ):
        raise TransitionRefused(
            str(_("Agreement PDF checksum no longer matches the signing intent."))
        )

    review_bytes = _read_artifact_bytes(artifact)
    if checksum_of(review_bytes) != intent.artifact_checksum.lower():
        raise TransitionRefused(
            str(_("Agreement PDF checksum no longer matches the signing intent."))
        )

    date_value = (signed_date or "").strip()
    if not date_value:
        raise SigningCeremonyError(
            {"signedDate": str(_("Enter the signature date on the agreement."))}
        )

    signature_png = decode_data_url_image(signature_data_url)
    if len(signature_png) < 32:
        raise SigningCeremonyError(
            {"signature": str(_("Draw or type your signature before submitting."))}
        )
    initials_png = (
        decode_data_url_image(initials_data_url) if initials_data_url else b""
    )

    expected = contract_version(locked)
    appearance_digest = appearance_checksum(signature_png)

    signature = ContractSignature(
        contract=locked,
        intent=intent,
        signer=intent.actor,
        signer_role=ContractSignature.SignerRole.COMPANY,
        artifact=None,
        signed_at=now,
        disclosure_version=intent.disclosure_version,
        signature_method=ContractSignature.Method.HUB_EMBEDDED,
        appearance_checksum=appearance_digest,
        source_checksum=intent.artifact_checksum.lower(),
        signed_date_value=date_value,
        agent_text_values=dict(text_values or {}),
        # Company row does not drive final PDF; agent ceremony triggers it.
        finalization_status=ContractSignature.FinalizationStatus.READY,
        request_ip_hash=intent.request_ip_hash,
        request_ua_hash=intent.request_ua_hash,
    )
    signature.appearance_file.save(
        f"appearance-{signature.public_id}.png",
        ContentFile(signature_png),
        save=False,
    )
    if initials_png:
        signature.initials_file.save(
            f"initials-{signature.public_id}.png",
            ContentFile(initials_png),
            save=False,
        )
    signature.full_clean()
    signature.save()

    intent.status = ContractSigningIntent.Status.CONSUMED
    intent.consumed_at = now
    intent.save(update_fields=["status", "consumed_at"])

    transition(
        actor=intent.actor,
        contract=locked,
        action="mark_company_signed",
        expected_version=expected,
    )

    log_event(
        "contract.company_signature.created",
        actor=actor_from_user(intent.actor),
        target=AuditTarget(
            target_type="contract.AgentContract",
            target_id=str(locked.public_id),
            target_label=intent.actor.email,
            target_snapshot={
                "signature_id": str(signature.public_id),
                "intent_id": str(intent.public_id),
                "disclosure_version": intent.disclosure_version,
                "method": signature.signature_method,
                "signer_role": COMPANY_ROLE,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="contract",
        office_id=getattr(locked.office, "stable_key", "") or "",
    )

    locked.refresh_from_db()
    return {
        "ok": True,
        "companySigned": True,
        "signaturePublicId": str(signature.public_id),
        "status": locked.status,
        "workspaceUrl": reverse(
            "agent_contract_workspace", kwargs={"public_id": locked.public_id}
        ),
    }
