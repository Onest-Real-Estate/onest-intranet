"""Immutable final signed-contract PDF generation (P1-043).

Builds one authoritative artifact from the durable signature record: the exact
issued/reviewed PDF (checksum-bound) with Agent appearance stamped, a
certificate/audit page appended, and an optional org PKCS#12 seal. Generation
is asynchronous and idempotent — retries never replace an attached final PDF.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader, PdfWriter

from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, log_event, system_actor
from apps.contract.certificate_of_completion import (
    CERTIFICATE_MARKER,
    build_certificate_of_completion,
)
from apps.contract.field_layout import COMPANY_ROLE, SIGNER_ROLE, normalize_field_layout
from apps.contract.models import AgentContract, ContractArtifact, ContractSignature
from apps.contract.pdf_signing import (
    seal_pdf_with_org_cert,
    stamp_signer_fields,
)
from apps.contract.template_security import checksum_of

logger = logging.getLogger(__name__)

RENDERER_VERSION = "hub-signed-final-1.0.0"
MEDIA_TYPE_PDF = "application/pdf"


class SignedPdfGenerationError(Exception):
    """Terminal or retryable failure without embedding PII in the message."""

    def __init__(self, code: str, *, retryable: bool = True):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class FinalSignedPdf:
    data: bytes
    checksum: str
    source_checksum: str
    page_count: int
    source_page_count: int
    markers: tuple[str, ...]
    seal_cert_subject: str
    seal_cert_fingerprint: str
    document_id: str


def document_identifier(contract: AgentContract) -> str:
    return f"{contract.public_id}@v{contract.version_number}"


def _read_file_bytes(field) -> bytes:
    field.open("rb")
    try:
        return field.read()
    finally:
        field.close()


def _read_artifact_bytes(artifact: ContractArtifact) -> bytes:
    if not artifact.file:
        raise SignedPdfGenerationError("missing_source_file", retryable=False)
    return _read_file_bytes(artifact.file)


def append_certificate_pages(legal_pdf: bytes, *, certificate_pdf: bytes) -> bytes:
    """Concatenate certificate page(s) after the stamped legal agreement."""
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(legal_pdf)).pages:
        writer.add_page(page)
    for page in PdfReader(io.BytesIO(certificate_pdf)).pages:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def validate_final_signed_pdf(
    data: bytes,
    *,
    source_page_count: int,
    document_id: str,
    source_checksum: str,
) -> tuple[int, tuple[str, ...]]:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise SignedPdfGenerationError("pdf_unreadable") from exc

    page_count = len(reader.pages)
    if page_count < source_page_count + 1:
        raise SignedPdfGenerationError("missing_certificate_page", retryable=False)

    markers: list[str] = [
        "opened",
        f"pages:{page_count}",
        "hub_signed_final",
        f"source_pages:{source_page_count}",
        CERTIFICATE_MARKER,
    ]
    if document_id:
        markers.append("document_id")
    if source_checksum:
        markers.append("source_checksum_bound")

    # Soft content probe: certificate page should mention the document id.
    try:
        last = reader.pages[-1]
        text = last.extract_text() or ""
    except Exception:  # noqa: BLE001
        text = ""
    if (
        document_id
        and document_id not in text
        and "Certificate of Completion" not in text
    ):
        raise SignedPdfGenerationError("certificate_markers_missing", retryable=False)

    return page_count, tuple(markers)


def certificate_facts_for_signature(
    signature: ContractSignature,
    *,
    signed_checksum: str = "",
) -> dict[str, Any]:
    contract = signature.contract
    signer = signature.signer
    snap = contract.party_snapshot or {}
    party_name = ""
    for key in ("legalName", "displayName", "fullName"):
        value = snap.get(key)
        if isinstance(value, str) and value.strip():
            party_name = value.strip()
            break
    if not party_name:
        first = (snap.get("legalFirstName") or "").strip()
        last = (snap.get("legalLastName") or "").strip()
        party_name = f"{first} {last}".strip() or (
            signer.get_full_name() or signer.email or ""
        )

    doc_id = document_identifier(contract)
    facts: dict[str, Any] = {
        "contractPublicId": str(contract.public_id),
        "versionNumber": contract.version_number,
        "documentIdentifier": doc_id,
        "verificationIdentifier": str(signature.public_id),
        "partyDisplayName": party_name,
        "signerEmail": signer.email,
        "signerRole": signature.signer_role,
        "signedAt": signature.signed_at.isoformat(),
        "consentAcceptedAt": (
            signature.intent.consent_accepted_at.isoformat()
            if signature.intent_id
            else ""
        ),
        "disclosureVersion": signature.disclosure_version,
        "signatureMethod": signature.signature_method,
        "intentPublicId": str(signature.intent.public_id)
        if signature.intent_id
        else "",
        "signaturePublicId": str(signature.public_id),
        "reviewChecksum": signature.source_checksum,
        "signedChecksum": signed_checksum,
        "appearanceChecksum": signature.appearance_checksum,
        "requestIpHash": signature.request_ip_hash,
        "requestUaHash": signature.request_ua_hash,
        "sealCertSubject": signature.seal_cert_subject,
        "sealCertFingerprint": signature.seal_cert_fingerprint,
        "rendererVersion": RENDERER_VERSION,
    }
    company = (
        ContractSignature.objects.select_related("signer", "intent")
        .filter(
            contract_id=contract.pk,
            signer_role=ContractSignature.SignerRole.COMPANY,
        )
        .first()
    )
    if company is not None:
        facts["companySignerEmail"] = company.signer.email
        facts["companySignedAt"] = company.signed_at.isoformat()
        facts["companySignaturePublicId"] = str(company.public_id)
        facts["companyDisclosureVersion"] = company.disclosure_version
    return facts


def render_final_signed_pdf(signature: ContractSignature) -> FinalSignedPdf:
    """Stamp + certificate + seal from durable signatures and source PDF."""
    if signature.signer_role != ContractSignature.SignerRole.AGENT:
        raise SignedPdfGenerationError("agent_signature_required", retryable=False)

    contract = signature.contract
    if not signature.source_checksum:
        raise SignedPdfGenerationError("missing_source_checksum", retryable=False)

    source = (
        ContractArtifact.objects.filter(pk=contract.generated_pdf_id).first()
        if contract.generated_pdf_id
        else None
    )
    if source is None:
        # Fall back to the intent-bound artifact (same bytes identity).
        source = signature.intent.artifact if signature.intent_id else None
    if source is None:
        raise SignedPdfGenerationError("missing_source_artifact", retryable=False)

    review_bytes = _read_artifact_bytes(source)
    live_checksum = checksum_of(review_bytes)
    if live_checksum != signature.source_checksum.lower():
        raise SignedPdfGenerationError("source_checksum_mismatch", retryable=False)
    if source.checksum.lower() != signature.source_checksum.lower():
        raise SignedPdfGenerationError("source_checksum_mismatch", retryable=False)

    company = (
        ContractSignature.objects.select_related("intent")
        .filter(
            contract_id=contract.pk,
            signer_role=ContractSignature.SignerRole.COMPANY,
        )
        .first()
    )
    if company is None:
        raise SignedPdfGenerationError("missing_company_signature", retryable=False)
    if not company.appearance_file:
        raise SignedPdfGenerationError("missing_company_appearance", retryable=False)
    company_png = _read_file_bytes(company.appearance_file)
    if checksum_of(company_png) != (company.appearance_checksum or "").lower():
        raise SignedPdfGenerationError(
            "company_appearance_checksum_mismatch", retryable=False
        )
    company_initials = b""
    if company.initials_file:
        company_initials = _read_file_bytes(company.initials_file)

    if not signature.appearance_file:
        raise SignedPdfGenerationError("missing_appearance", retryable=False)
    appearance_png = _read_file_bytes(signature.appearance_file)
    if checksum_of(appearance_png) != (signature.appearance_checksum or "").lower():
        raise SignedPdfGenerationError("appearance_checksum_mismatch", retryable=False)

    initials_png = b""
    if signature.initials_file:
        initials_png = _read_file_bytes(signature.initials_file)

    version = contract.template_version
    layout = normalize_field_layout(version.field_layout or []) if version else []
    stamped = stamp_signer_fields(
        review_bytes,
        layout=layout,
        role=COMPANY_ROLE,
        signature_png=company_png,
        signed_date=company.signed_date_value or "",
        initials_png=company_initials,
        text_values=dict(company.agent_text_values or {}),
    )
    stamped = stamp_signer_fields(
        stamped,
        layout=layout,
        role=SIGNER_ROLE,
        signature_png=appearance_png,
        signed_date=signature.signed_date_value or "",
        initials_png=initials_png,
        text_values=dict(signature.agent_text_values or {}),
    )

    source_reader = PdfReader(io.BytesIO(review_bytes))
    source_page_count = len(source_reader.pages)
    doc_id = document_identifier(contract)

    # Certificate page first (pre-seal) so the org seal covers legal + audit pages.
    facts = certificate_facts_for_signature(signature, signed_checksum="")
    coc_bytes = build_certificate_of_completion(facts=facts)
    combined = append_certificate_pages(stamped, certificate_pdf=coc_bytes)

    sealed = seal_pdf_with_org_cert(combined)
    digest = checksum_of(sealed.pdf_bytes)

    # Rebuild certificate with the final output checksum for the stored CoC
    # sibling artifact; the sealed PDF already embeds the pre-seal certificate
    # page (checksum field blank or omitted there is acceptable — verification
    # uses artifact metadata). Re-stamp certificate text only for the separate
    # CoC artifact in attach().
    page_count, markers = validate_final_signed_pdf(
        sealed.pdf_bytes,
        source_page_count=source_page_count,
        document_id=doc_id,
        source_checksum=signature.source_checksum,
    )

    return FinalSignedPdf(
        data=sealed.pdf_bytes,
        checksum=digest,
        source_checksum=signature.source_checksum.lower(),
        page_count=page_count,
        source_page_count=source_page_count,
        markers=markers,
        seal_cert_subject=sealed.cert_subject,
        seal_cert_fingerprint=sealed.cert_fingerprint,
        document_id=doc_id,
    )


def _delete_storage_quietly(storage, name: str) -> None:
    if not name:
        return
    try:
        if storage.exists(name):
            storage.delete(name)
    except Exception:  # noqa: BLE001
        logger.warning("orphan cleanup failed key_suffix=%s", name[-24:])


def _emit_signed_pdf_ready(
    contract: AgentContract,
    signature: ContractSignature,
    artifact: ContractArtifact,
) -> None:
    now = timezone.now()
    publish_event(
        "contract.signed_pdf_ready",
        actor_id="system",
        subject=str(contract.public_id),
        payload={
            "contract_id": str(contract.public_id),
            "office_id": str(contract.office_id),
            "agent_id": str(contract.recipient_id),
            "signature_id": str(signature.public_id),
            "artifact_id": str(artifact.public_id),
            "checksum": artifact.checksum,
            "source_checksum": signature.source_checksum,
            "occurred_at": now.isoformat(),
        },
    )
    log_event(
        "contract.signed_pdf_generated",
        actor=system_actor("signed_pdf_generation"),
        target=AuditTarget(
            target_type=AgentContract._meta.label_lower,
            target_id=str(contract.public_id),
            target_label=f"contract:{contract.public_id}",
            target_snapshot={
                "signature_id": str(signature.public_id),
                "artifact_id": str(artifact.public_id),
                "checksum": artifact.checksum,
                "source_checksum": signature.source_checksum,
            },
        ),
        after={
            "artifact_id": str(artifact.public_id),
            "checksum": artifact.checksum,
            "source_checksum": signature.source_checksum,
            "byte_size": artifact.byte_size,
            "renderer_version": artifact.renderer_version,
            "task_id": signature.generation_task_id,
        },
        outcome=AuditEvent.Outcome.SUCCESS,
        source="task",
        channel="contract",
        office_id=getattr(contract.office, "stable_key", "") or "",
    )


@transaction.atomic
def attach_final_signed_pdf(
    signature: ContractSignature,
    rendered: FinalSignedPdf,
    *,
    task_id: str = "",
) -> tuple[ContractArtifact, bool]:
    """Attach the authoritative final PDF once under row locks.

    Returns ``(artifact, created)``. If a final artifact is already linked,
    returns it without replacement.
    """
    locked_sig = (
        ContractSignature.objects.select_for_update(of=("self",))
        .select_related("contract", "intent", "signer")
        .get(pk=signature.pk)
    )
    locked = AgentContract.objects.select_for_update(of=("self",)).get(
        pk=locked_sig.contract_id
    )

    if locked_sig.artifact_id and locked.signed_pdf_id == locked_sig.artifact_id:
        current = ContractArtifact.objects.filter(pk=locked_sig.artifact_id).first()
        if current is not None:
            return current, False

    if locked.signed_pdf_id:
        existing = ContractArtifact.objects.filter(pk=locked.signed_pdf_id).first()
        if existing is not None:
            if existing.checksum == rendered.checksum:
                if locked_sig.artifact_id != existing.pk:
                    locked_sig.artifact = existing
                    locked_sig.finalization_status = (
                        ContractSignature.FinalizationStatus.READY
                    )
                    locked_sig.finalization_error = ""
                    if task_id:
                        locked_sig.generation_task_id = task_id
                    locked_sig.save(
                        update_fields=[
                            "artifact",
                            "finalization_status",
                            "finalization_error",
                            "generation_task_id",
                        ]
                    )
                return existing, False
            raise SignedPdfGenerationError(
                "signed_pdf_already_attached", retryable=False
            )

    display_name = f"contract-{locked.public_id}-v{locked.version_number}-signed.pdf"
    artifact = ContractArtifact(
        contract=locked,
        kind=ContractArtifact.Kind.SIGNED_PDF,
        display_name=display_name,
        media_type=MEDIA_TYPE_PDF,
        byte_size=len(rendered.data),
        checksum=rendered.checksum,
        renderer_version=RENDERER_VERSION,
        rule_version=locked.calculation_rule_version or "",
        input_fingerprint=rendered.source_checksum,
        generation_metadata={
            "pageCount": rendered.page_count,
            "sourcePageCount": rendered.source_page_count,
            "markers": list(rendered.markers),
            "sourceChecksum": rendered.source_checksum,
            "documentIdentifier": rendered.document_id,
            "signaturePublicId": str(locked_sig.public_id),
            "renderer": RENDERER_VERSION,
            "taskId": task_id,
            "createdAt": timezone.now().isoformat(),
        },
        created_by=locked_sig.signer,
    )
    artifact.full_clean(exclude=["file"])
    orphan_key = ""
    try:
        artifact.file.save(display_name, ContentFile(rendered.data), save=False)
        orphan_key = artifact.file.name
        artifact.full_clean()
        artifact.save()
    except Exception:
        if orphan_key:
            _delete_storage_quietly(artifact.file.storage, orphan_key)
        raise

    # Standalone CoC sibling for ops (same facts, includes output checksum).
    coc_facts = certificate_facts_for_signature(
        locked_sig, signed_checksum=rendered.checksum
    )
    coc_facts["sealCertSubject"] = rendered.seal_cert_subject
    coc_facts["sealCertFingerprint"] = rendered.seal_cert_fingerprint
    coc_bytes = build_certificate_of_completion(facts=coc_facts)
    coc_digest = checksum_of(coc_bytes)
    coc_name = f"contract-{locked.public_id}-v{locked.version_number}-certificate.pdf"
    coc_artifact = ContractArtifact(
        contract=locked,
        kind=ContractArtifact.Kind.CERTIFICATE_OF_COMPLETION,
        display_name=coc_name,
        media_type=MEDIA_TYPE_PDF,
        byte_size=len(coc_bytes),
        checksum=coc_digest,
        renderer_version="hub-coc-1.0.0",
        rule_version=locked.calculation_rule_version or "",
        generation_metadata={
            "source": "certificate_of_completion",
            "signaturePublicId": str(locked_sig.public_id),
            "finalChecksum": rendered.checksum,
            "sourceChecksum": rendered.source_checksum,
        },
        created_by=locked_sig.signer,
    )
    coc_orphan = ""
    try:
        coc_artifact.full_clean(exclude=["file"])
        coc_artifact.file.save(coc_name, ContentFile(coc_bytes), save=False)
        coc_orphan = coc_artifact.file.name
        coc_artifact.full_clean()
        coc_artifact.save()
    except Exception:
        if coc_orphan:
            _delete_storage_quietly(coc_artifact.file.storage, coc_orphan)
        raise

    locked.signed_pdf = artifact
    locked.save(update_fields=["signed_pdf", "updated_at"])

    locked_sig.artifact = artifact
    locked_sig.certificate_of_completion = coc_artifact
    locked_sig.finalization_status = ContractSignature.FinalizationStatus.READY
    locked_sig.finalization_error = ""
    locked_sig.seal_cert_subject = rendered.seal_cert_subject
    locked_sig.seal_cert_fingerprint = rendered.seal_cert_fingerprint
    if task_id:
        locked_sig.generation_task_id = task_id
    locked_sig.save(
        update_fields=[
            "artifact",
            "certificate_of_completion",
            "finalization_status",
            "finalization_error",
            "seal_cert_subject",
            "seal_cert_fingerprint",
            "generation_task_id",
        ]
    )

    def _after_commit() -> None:
        _emit_signed_pdf_ready(locked, locked_sig, artifact)

    transaction.on_commit(_after_commit)
    return artifact, True


def mark_finalization_failed(
    signature_id: int, *, code: str, task_id: str = ""
) -> None:
    signature = ContractSignature.objects.filter(pk=signature_id).first()
    if signature is None:
        return
    if signature.finalization_status == ContractSignature.FinalizationStatus.READY:
        return
    signature.finalization_status = ContractSignature.FinalizationStatus.FAILED
    signature.finalization_error = code[:64]
    update_fields = ["finalization_status", "finalization_error"]
    if task_id:
        signature.generation_task_id = task_id
        update_fields.append("generation_task_id")
    try:
        signature.save(update_fields=update_fields)
    except Exception:  # noqa: BLE001
        logger.warning(
            "mark_finalization_failed save error signature_id=%s code=%s",
            signature_id,
            code,
        )
    log_event(
        "contract.signed_pdf_generation_failed",
        actor=system_actor("signed_pdf_generation"),
        target=AuditTarget(
            target_type=ContractSignature._meta.label_lower,
            target_id=str(signature.public_id),
            target_label=f"signature:{signature.public_id}",
            target_snapshot={"contract_id": str(signature.contract.public_id)},
        ),
        after={"code": code, "task_id": task_id},
        outcome=AuditEvent.Outcome.FAILURE,
        source="task",
        channel="contract",
        office_id=getattr(signature.contract.office, "stable_key", "") or "",
    )


def generate_and_store_signed_pdf(signature_id: int, *, task_id: str = "") -> str:
    """Full pipeline used by the Celery task. Returns a stable outcome code."""
    signature = (
        ContractSignature.objects.select_related(
            "contract",
            "contract__template_version",
            "contract__generated_pdf",
            "contract__office",
            "intent",
            "intent__artifact",
            "signer",
            "artifact",
        )
        .filter(pk=signature_id)
        .first()
    )
    if signature is None:
        return "missing"

    if (
        signature.artifact_id
        and signature.contract.signed_pdf_id == signature.artifact_id
        and signature.finalization_status == ContractSignature.FinalizationStatus.READY
    ):
        return "ready_idempotent"

    if task_id and signature.generation_task_id != task_id:
        signature.generation_task_id = task_id
        signature.save(update_fields=["generation_task_id"])

    try:
        rendered = render_final_signed_pdf(signature)
    except SignedPdfGenerationError as exc:
        if not exc.retryable:
            mark_finalization_failed(signature_id, code=exc.code, task_id=task_id)
            logger.warning(
                "generate_signed_contract_pdf terminal signature_id=%s code=%s",
                signature_id,
                exc.code,
            )
            return f"failed:{exc.code}"
        raise

    artifact, created = attach_final_signed_pdf(signature, rendered, task_id=task_id)
    logger.info(
        "generate_signed_contract_pdf ready signature_id=%s artifact=%s "
        "created=%s bytes=%s",
        signature_id,
        artifact.public_id,
        created,
        artifact.byte_size,
    )
    return "ready" if created else "ready_idempotent"


def integrity_payload(contract: AgentContract) -> dict[str, Any] | None:
    """Ops-safe integrity facts without streaming private PDF bytes."""
    signature = (
        ContractSignature.objects.select_related(
            "artifact", "certificate_of_completion"
        )
        .filter(contract_id=contract.pk)
        .first()
    )
    if signature is None:
        return None
    artifact = signature.artifact or contract.signed_pdf
    return {
        "contractPublicId": str(contract.public_id),
        "versionNumber": contract.version_number,
        "documentIdentifier": document_identifier(contract),
        "signaturePublicId": str(signature.public_id),
        "finalizationStatus": signature.finalization_status,
        "finalizationError": signature.finalization_error or None,
        "sourceChecksum": signature.source_checksum or None,
        "outputChecksum": artifact.checksum if artifact else None,
        "byteSize": artifact.byte_size if artifact else None,
        "rendererVersion": (artifact.renderer_version if artifact else None)
        or RENDERER_VERSION,
        "storageKeySuffix": (
            artifact.file.name[-48:] if artifact and artifact.file else None
        ),
        "createdAt": (
            artifact.created_at.isoformat()
            if artifact
            else signature.created_at.isoformat()
        ),
        "generationTaskId": signature.generation_task_id or None,
        "signatureMethod": signature.signature_method,
        "disclosureVersion": signature.disclosure_version,
        "signedAt": signature.signed_at.isoformat(),
        "artifactPublicId": str(artifact.public_id) if artifact else None,
    }
