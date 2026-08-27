"""Recipient contract signing ceremony (P1-042).

Creates short-lived DocuSeal-backed intents, completes via webhook with
immutable signature records, and transitions through the lifecycle service.
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
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.docuseal_client import (
    DocuSealError,
    DocuSealNotConfigured,
    docuseal_embeds_available,
    download_submission_documents,
    embed_host,
    embed_origin,
    embed_protocol,
    get_submission,
    is_docuseal_configured,
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


def signing_is_ready() -> bool:
    return is_docuseal_configured()


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


def _cancel_pending_intents(contract: AgentContract) -> None:
    ContractSigningIntent.objects.filter(
        contract=contract,
        status=ContractSigningIntent.Status.PENDING,
    ).update(status=ContractSigningIntent.Status.CANCELLED)


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
    """Create a signing intent and DocuSeal submission for the recipient."""
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
    _cancel_pending_intents(contract)

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

    if not contract.docuseal_submission_id:
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "Signing is not ready for this agreement yet. "
                            "Contact your brokerage."
                        )
                    )
                ]
            }
        )

    ttl = max(60, int(settings.DOCUSEAL_SIGNING_INTENT_TTL_SECONDS))
    expires_at = now + timedelta(seconds=ttl)
    intent = ContractSigningIntent(
        contract=contract,
        actor=actor,
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

    try:
        submission = get_submission(int(contract.docuseal_submission_id))
        submitter = submission.agent_submitter()
    except DocuSealNotConfigured as exc:
        intent.status = ContractSigningIntent.Status.CANCELLED
        intent.save(update_fields=["status"])
        raise SigningCeremonyError(
            {"form": [str(_("Electronic signing is temporarily unavailable."))]}
        ) from exc
    except DocuSealError as exc:
        intent.status = ContractSigningIntent.Status.CANCELLED
        intent.save(update_fields=["status"])
        logger.warning("docuseal start_signing failed intent=%s", intent.public_id)
        raise SigningCeremonyError(
            {
                "form": [
                    str(
                        _(
                            "Could not start the signing form. Return to My Contract "
                            "and try again."
                        )
                    )
                ]
            }
        ) from exc

    slug = submitter.slug or (contract.docuseal_agent_submitter_slug or "")
    embed_src = submitter.embed_src
    if not embed_src and slug:
        embed_src = f"{embed_origin()}/s/{slug}"
    if not embed_src:
        intent.status = ContractSigningIntent.Status.CANCELLED
        intent.save(update_fields=["status"])
        raise SigningCeremonyError(
            {"form": [str(_("Signing form URL was missing. Try again."))]}
        )

    intent.docuseal_submission_id = submission.id
    intent.docuseal_submitter_slug = slug
    intent.embed_src = embed_src
    intent.save(
        update_fields=[
            "docuseal_submission_id",
            "docuseal_submitter_slug",
            "embed_src",
        ]
    )

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
                "submission_id": submission.id,
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
            "embedSrc": intent.embed_src,
            "expiresAt": expires_at.isoformat(),
            "docusealSubmissionId": submission.id,
            "embedsAvailable": docuseal_embeds_available(),
            "docusealHost": embed_host(),
            "docusealProtocol": embed_protocol(),
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
        }

    signature = ContractSignature.objects.filter(contract=contract).first()
    return {
        "signed": signature is not None
        and contract.status in {ContractStatus.SIGNED, ContractStatus.ACTIVE},
        "status": contract.status,
        "signaturePublicId": str(signature.public_id) if signature else None,
        "contractPublicId": str(contract.public_id),
    }


def _attach_signed_pdf(
    locked: AgentContract,
    *,
    pdf_bytes: bytes,
    signer: User,
) -> ContractArtifact:
    digest = checksum_of(pdf_bytes)
    current = (
        ContractArtifact.objects.filter(pk=locked.signed_pdf_id).first()
        if locked.signed_pdf_id
        else None
    )
    if current is not None and current.checksum == digest:
        return current

    display_name = f"contract-{locked.public_id}-v{locked.version_number}-signed.pdf"
    artifact = ContractArtifact(
        contract=locked,
        kind=ContractArtifact.Kind.SIGNED_PDF,
        display_name=display_name,
        media_type=MEDIA_TYPE_PDF,
        byte_size=len(pdf_bytes),
        checksum=digest,
        renderer_version="docuseal",
        rule_version=locked.calculation_rule_version or "",
        generation_metadata={"source": "docuseal"},
        created_by=signer,
    )
    artifact.full_clean(exclude=["file"])
    artifact.file.save(display_name, ContentFile(pdf_bytes), save=False)
    artifact.full_clean()
    artifact.save()
    locked.signed_pdf = artifact
    locked.save(update_fields=["signed_pdf", "updated_at"])
    return artifact


@transaction.atomic
def complete_signing_from_docuseal(
    *,
    submission_id: int,
    event_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Idempotent webhook completion: signature row + mark_signed once."""
    del event_payload  # reserved for future correlation fields
    intent = (
        ContractSigningIntent.objects.select_related("contract", "actor", "artifact")
        .filter(docuseal_submission_id=submission_id)
        .first()
    )
    if intent is None:
        logger.info("docuseal webhook unknown submission_id=%s", submission_id)
        return {"ok": True, "ignored": True}

    locked = AgentContract.objects.select_for_update(of=("self",)).get(
        pk=intent.contract_id
    )
    existing = ContractSignature.objects.filter(contract_id=locked.pk).first()
    if existing is not None:
        return {
            "ok": True,
            "idempotent": True,
            "signaturePublicId": str(existing.public_id),
        }

    now = timezone.now()
    if intent.status != ContractSigningIntent.Status.PENDING:
        if locked.status in {ContractStatus.SIGNED, ContractStatus.ACTIVE}:
            return {"ok": True, "idempotent": True}
        raise TransitionRefused(str(_("Signing intent is no longer pending.")))
    if intent.expires_at <= now:
        intent.status = ContractSigningIntent.Status.EXPIRED
        intent.save(update_fields=["status"])
        raise TransitionRefused(str(_("Signing intent expired. Start again.")))

    if locked.status not in {ContractStatus.SENT, ContractStatus.VIEWED}:
        raise TransitionRefused(str(_("Contract is not in a signable state.")))
    if locked.recipient_id != intent.actor_id:
        raise PermissionDenied(_("Signing intent recipient mismatch."))

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

    try:
        signed_bytes = download_submission_documents(submission_id)
    except DocuSealError as exc:
        logger.warning(
            "docuseal complete download failed submission_id=%s", submission_id
        )
        raise TransitionRefused(
            str(_("Could not retrieve the signed PDF from DocuSeal."))
        ) from exc
    if not signed_bytes:
        raise TransitionRefused(str(_("Signed PDF was empty.")))

    expected = contract_version(locked)
    signed_artifact = _attach_signed_pdf(
        locked, pdf_bytes=signed_bytes, signer=intent.actor
    )
    # Re-lock after attach (updated_at changed) — reload version for transition.
    locked = AgentContract.objects.select_for_update(of=("self",)).get(pk=locked.pk)
    expected = contract_version(locked)

    signature = ContractSignature(
        contract=locked,
        intent=intent,
        signer=intent.actor,
        artifact=signed_artifact,
        signed_at=now,
        disclosure_version=intent.disclosure_version,
        signature_method=ContractSignature.Method.DOCUSEAL_EMBEDDED,
        docuseal_submission_id=submission_id,
        docuseal_submitter_slug=intent.docuseal_submitter_slug,
        request_ip_hash=intent.request_ip_hash,
        request_ua_hash=intent.request_ua_hash,
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
                "submission_id": submission_id,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="webhook",
        channel="contract",
        office_id=getattr(locked.office, "stable_key", "") or "",
    )
    return {"ok": True, "signaturePublicId": str(signature.public_id)}
