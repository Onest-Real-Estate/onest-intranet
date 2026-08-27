"""Deterministic review-PDF generation via DocuSeal template submissions.

Renders through the immutable published DocuSeal template already attached at
issuance: Prefill role auto-completes commercial fields; Agent signs later.
Task logs must never include party or commercial payloads — only contract
public ids and outcome codes.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader

from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, log_event, system_actor
from apps.contract.docuseal_client import (
    DocuSealError,
    DocuSealNotConfigured,
    agent_submitter_payload,
    create_submission,
    download_submission_documents,
    prefill_submitter_payload,
)
from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import AgentContract, ContractArtifact
from apps.contract.statuses import ContractStatus
from apps.contract.template_security import checksum_of, validate_merge_schema

logger = logging.getLogger(__name__)

RENDERER_VERSION = "docuseal-1.0.0"
MEDIA_TYPE_PDF = "application/pdf"

_ALLOWED_STATUSES = frozenset(
    {
        ContractStatus.SENT,
        ContractStatus.GENERATION_ERROR,
    }
)


class PdfGenerationError(Exception):
    """Terminal or retryable failure without embedding PII in the message."""

    def __init__(self, code: str, *, retryable: bool = True):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class RenderedPdf:
    data: bytes
    checksum: str
    page_count: int
    merge_values: dict[str, str]
    input_fingerprint: str
    markers: tuple[str, ...]
    docuseal_submission_id: int
    docuseal_agent_submitter_slug: str


def build_merge_values(contract: AgentContract) -> dict[str, str]:
    """Resolve allowlisted merge keys from frozen snapshots and contract facts."""
    version = contract.template_version
    if version is None:
        raise PdfGenerationError("missing_template", retryable=False)

    party = contract.party_snapshot or {}
    office = contract.office_snapshot or {}
    terms = contract.terms_snapshot or {}
    raw_mentor = terms.get("mentor")
    raw_referral = terms.get("referral")
    mentor: dict[str, Any] = raw_mentor if isinstance(raw_mentor, dict) else {}
    referral: dict[str, Any] = raw_referral if isinstance(raw_referral, dict) else {}

    catalog: dict[str, str] = {
        "party.legalFirstName": str(party.get("legalFirstName") or ""),
        "party.legalLastName": str(party.get("legalLastName") or ""),
        "party.displayName": str(party.get("displayName") or ""),
        "party.email": str(party.get("email") or ""),
        "party.licenseNumber": str(party.get("licenseNumber") or ""),
        "party.licenseState": str(party.get("licenseState") or ""),
        "party.agentIdentifier": str(party.get("agentIdentifier") or ""),
        "office.name": str(office.get("name") or ""),
        "office.state": str(office.get("state") or ""),
        "office.city": str(office.get("city") or ""),
        "office.streetAddress": str(office.get("streetAddress") or ""),
        "office.zipCode": str(office.get("zipCode") or ""),
        "office.mainPhone": str(office.get("mainPhone") or ""),
        "office.publicEmail": str(office.get("publicEmail") or ""),
        "terms.agentSplitPercent": str(terms.get("agentSplitPercent") or ""),
        "terms.officeSplitPercent": str(terms.get("officeSplitPercent") or ""),
        "terms.transactionFeeAmount": str(terms.get("transactionFeeAmount") or ""),
        "terms.transactionFeePercent": str(terms.get("transactionFeePercent") or ""),
        "terms.annualCapAmount": str(terms.get("annualCapAmount") or ""),
        "terms.specialArrangements": str(terms.get("specialArrangements") or ""),
        "terms.mentor.percent": str(mentor.get("percent") or ""),
        "terms.mentor.fixedAmount": str(mentor.get("fixedAmount") or ""),
        "terms.mentor.capAmount": str(mentor.get("capAmount") or ""),
        "terms.mentor.basis": str(mentor.get("basis") or ""),
        "terms.referral.percent": str(referral.get("percent") or ""),
        "terms.referral.fixedAmount": str(referral.get("fixedAmount") or ""),
        "terms.referral.capAmount": str(referral.get("capAmount") or ""),
        "terms.referral.basis": str(referral.get("basis") or ""),
        "contract.effectiveOn": contract.effective_on.isoformat(),
        "contract.expiresOn": (
            contract.expires_on.isoformat() if contract.expires_on else ""
        ),
        "contract.publicId": str(contract.public_id),
        "contract.versionNumber": str(contract.version_number),
        "contract.calculationRuleVersion": contract.calculation_rule_version or "",
        "template.versionLabel": version.version_label,
        "template.stableKey": version.template.stable_key,
        "document.identifier": f"{contract.public_id}@v{contract.version_number}",
        "document.rendererVersion": RENDERER_VERSION,
    }

    merge_schema = list(version.merge_schema or [])
    if not merge_schema:
        return {
            key: catalog[key]
            for key in (
                "party.legalFirstName",
                "party.legalLastName",
                "party.email",
                "party.licenseNumber",
                "party.licenseState",
                "office.name",
                "office.state",
                "office.city",
                "office.streetAddress",
                "terms.agentSplitPercent",
                "terms.officeSplitPercent",
                "contract.effectiveOn",
                "contract.expiresOn",
                "contract.publicId",
                "template.versionLabel",
            )
            if key in catalog
        }

    values: dict[str, str] = {}
    for item in merge_schema:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        source = str(item.get("source", "")).strip() or key
        if not key:
            continue
        if source in catalog:
            values[key] = catalog[source]
        elif key in catalog:
            values[key] = catalog[key]
        else:
            raise PdfGenerationError("unresolved_merge_source", retryable=False)
    return values


def input_fingerprint(
    contract: AgentContract,
    *,
    merge_values: dict[str, str],
    source_checksum: str,
) -> str:
    payload = {
        "renderer": RENDERER_VERSION,
        "rule": contract.calculation_rule_version or "",
        "template_version_id": contract.template_version_id,
        "docuseal_template_id": (
            contract.template_version.docuseal_template_id
            if contract.template_version
            else None
        ),
        "source_checksum": source_checksum,
        "party": contract.party_snapshot or {},
        "office": contract.office_snapshot or {},
        "terms": contract.terms_snapshot or {},
        "merge": merge_values,
        "public_id": str(contract.public_id),
        "version_number": contract.version_number,
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def validate_rendered_pdf(
    data: bytes,
    *,
    document_id: str,
) -> tuple[int, tuple[str, ...]]:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise PdfGenerationError("pdf_unreadable") from exc

    page_count = len(reader.pages)
    if page_count < 1:
        raise PdfGenerationError("empty_pdf", retryable=False)

    markers: list[str] = ["opened", f"pages:{page_count}"]
    # DocuSeal-filled PDFs may not retain AcroForm /V values; identity is the
    # submission + checksum we store on the artifact.
    if document_id:
        markers.append("document_id")
    return page_count, tuple(markers)


def _party_display_name(contract: AgentContract) -> str:
    snap = contract.party_snapshot or {}
    display = str(snap.get("displayName") or "").strip()
    if display:
        return display
    first = str(snap.get("legalFirstName") or "").strip()
    last = str(snap.get("legalLastName") or "").strip()
    combined = f"{first} {last}".strip()
    return combined or str(snap.get("email") or "Agent")


def render_contract_pdf(contract: AgentContract) -> RenderedPdf:
    if contract.status not in _ALLOWED_STATUSES:
        raise PdfGenerationError("invalid_status", retryable=False)
    if not contract.party_snapshot or not contract.office_snapshot:
        raise PdfGenerationError("missing_snapshots", retryable=False)
    if not contract.terms_snapshot:
        raise PdfGenerationError("missing_terms_snapshot", retryable=False)

    version = contract.template_version
    if version is None:
        raise PdfGenerationError("missing_template", retryable=False)
    if version.status != version.Status.PUBLISHED:
        raise PdfGenerationError("template_not_published", retryable=False)
    if not version.docuseal_template_id:
        raise PdfGenerationError("missing_docuseal_template", retryable=False)

    merge_schema = list(version.merge_schema or [])
    placeholders = list(version.extracted_placeholder_keys or [])
    if merge_schema and placeholders:
        try:
            validate_merge_schema(merge_schema, placeholder_keys=placeholders)
        except Exception as exc:  # noqa: BLE001
            raise PdfGenerationError("merge_schema_invalid", retryable=False) from exc

    merge_values = build_merge_values(contract)
    source_checksum = (
        version.source_checksum or f"docuseal:{version.docuseal_template_id}"
    )
    fingerprint = input_fingerprint(
        contract, merge_values=merge_values, source_checksum=source_checksum
    )

    recipient = contract.recipient
    agent_email = str(
        (contract.party_snapshot or {}).get("email") or getattr(recipient, "email", "")
    )
    if not agent_email:
        raise PdfGenerationError("missing_recipient_email", retryable=False)

    prefill_email = (settings.DOCUSEAL_PREFILL_EMAIL or "").strip()
    if not prefill_email:
        raise PdfGenerationError("missing_prefill_email", retryable=False)

    try:
        submission = create_submission(
            template_id=int(version.docuseal_template_id),
            name=f"Agent contract {contract.public_id} v{contract.version_number}",
            submitters=[
                prefill_submitter_payload(email=prefill_email, values=merge_values),
                agent_submitter_payload(
                    email=agent_email,
                    name=_party_display_name(contract),
                    external_id=str(contract.public_id),
                ),
            ],
        )
        pdf_bytes = download_submission_documents(submission.id)
    except DocuSealNotConfigured as exc:
        raise PdfGenerationError("docuseal_not_configured", retryable=False) from exc
    except DocuSealError as exc:
        raise PdfGenerationError("docuseal_render_failed") from exc

    document_id = f"{contract.public_id}@v{contract.version_number}"
    page_count, markers = validate_rendered_pdf(pdf_bytes, document_id=document_id)
    agent = submission.agent_submitter()
    digest = checksum_of(pdf_bytes)
    return RenderedPdf(
        data=pdf_bytes,
        checksum=digest,
        page_count=page_count,
        merge_values=merge_values,
        input_fingerprint=fingerprint,
        markers=markers,
        docuseal_submission_id=submission.id,
        docuseal_agent_submitter_slug=agent.slug,
    )


def _delete_storage_quietly(storage, name: str) -> None:
    if not name:
        return
    try:
        if storage.exists(name):
            storage.delete(name)
    except Exception:  # noqa: BLE001
        logger.warning("orphan cleanup failed key_suffix=%s", name[-24:])


def _emit_pdf_ready(contract: AgentContract, artifact: ContractArtifact) -> None:
    now = timezone.now()
    publish_event(
        "contract.pdf_ready",
        actor_id="system",
        subject=str(contract.public_id),
        payload={
            "contract_id": str(contract.public_id),
            "office_id": str(contract.office_id),
            "agent_id": str(contract.recipient_id),
            "artifact_id": str(artifact.public_id),
            "checksum": artifact.checksum,
            "occurred_at": now.isoformat(),
        },
    )
    log_event(
        "contract.pdf_generated",
        actor=system_actor("pdf_generation"),
        target=AuditTarget(
            target_type=AgentContract._meta.label_lower,
            target_id=str(contract.public_id),
            target_label=f"contract:{contract.public_id}",
            target_snapshot={
                "status": contract.status,
                "artifact_id": str(artifact.public_id),
                "checksum": artifact.checksum,
            },
        ),
        after={
            "artifact_id": str(artifact.public_id),
            "checksum": artifact.checksum,
            "byte_size": artifact.byte_size,
            "renderer_version": artifact.renderer_version,
            "input_fingerprint": artifact.input_fingerprint,
        },
        outcome=AuditEvent.Outcome.SUCCESS,
        source="task",
        channel="contract",
        office_id=getattr(contract.office, "stable_key", "") or "",
    )


@transaction.atomic
def attach_generated_pdf(
    contract: AgentContract,
    rendered: RenderedPdf,
) -> tuple[ContractArtifact, bool]:
    """Attach (or reuse) the authoritative generated PDF under row lock.

    Returns ``(artifact, emitted_ready)``. Duplicate delivery with the same
    fingerprint/checksum reuses the current artifact and does not emit again.
    """
    locked = AgentContract.objects.select_for_update(of=("self",)).get(pk=contract.pk)
    current = (
        ContractArtifact.objects.filter(pk=locked.generated_pdf_id).first()
        if locked.generated_pdf_id
        else None
    )
    if (
        current is not None
        and current.input_fingerprint == rendered.input_fingerprint
        and current.checksum == rendered.checksum
        and locked.docuseal_submission_id == rendered.docuseal_submission_id
    ):
        return current, False

    display_name = f"contract-{locked.public_id}-v{locked.version_number}.pdf"
    artifact = ContractArtifact(
        contract=locked,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name=display_name,
        media_type=MEDIA_TYPE_PDF,
        byte_size=len(rendered.data),
        checksum=rendered.checksum,
        renderer_version=RENDERER_VERSION,
        rule_version=locked.calculation_rule_version or "",
        input_fingerprint=rendered.input_fingerprint,
        generation_metadata={
            "pageCount": rendered.page_count,
            "markers": list(rendered.markers),
            "mergeKeys": sorted(rendered.merge_values.keys()),
            "docusealSubmissionId": rendered.docuseal_submission_id,
        },
        created_by=None,
    )
    artifact.full_clean(exclude=["file"])
    orphan_key = ""
    try:
        artifact.file.save(
            display_name,
            ContentFile(rendered.data),
            save=False,
        )
        orphan_key = artifact.file.name
        artifact.full_clean()
        artifact.save()
    except Exception:
        if orphan_key:
            _delete_storage_quietly(artifact.file.storage, orphan_key)
        raise

    previous_id = locked.generated_pdf_id
    locked.generated_pdf = artifact
    locked.docuseal_submission_id = rendered.docuseal_submission_id
    locked.docuseal_agent_submitter_slug = rendered.docuseal_agent_submitter_slug
    update_fields = [
        "generated_pdf",
        "docuseal_submission_id",
        "docuseal_agent_submitter_slug",
        "updated_at",
    ]
    if locked.status == ContractStatus.GENERATION_ERROR:
        from apps.contract.lifecycle import allow_status_write

        locked.status = ContractStatus.SENT
        update_fields.append("status")
        with allow_status_write():
            locked.save(update_fields=update_fields)
    else:
        locked.save(update_fields=update_fields)

    if previous_id and previous_id != artifact.pk:
        logger.info(
            "pdf replaced previous_artifact_id=%s contract_id=%s",
            previous_id,
            locked.pk,
        )

    def _after_commit() -> None:
        _emit_pdf_ready(locked, artifact)

    transaction.on_commit(_after_commit)
    return artifact, True


def mark_generation_failed(contract_id: int, *, code: str) -> None:
    """Move a sent contract into generation_error without leaking PII."""
    contract = AgentContract.objects.filter(pk=contract_id).first()
    if contract is None:
        return
    if contract.status != ContractStatus.SENT:
        return
    try:
        transition(
            actor=None,
            contract=contract,
            action="mark_generation_error",
            expected_version=contract_version(contract),
            confirmed=False,
            idempotency_key=f"pdf-fail:{code}:{contract.public_id}",
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "mark_generation_error failed contract_id=%s code=%s",
            contract_id,
            code,
        )


def generate_and_store(contract_id: int) -> str:
    """Full pipeline used by the Celery task. Returns a stable outcome code."""
    contract = (
        AgentContract.objects.select_related(
            "template_version",
            "template_version__template",
            "office",
            "recipient",
            "generated_pdf",
        )
        .filter(pk=contract_id)
        .first()
    )
    if contract is None:
        return "missing"
    if contract.status not in _ALLOWED_STATUSES:
        logger.info(
            "generate_contract_pdf skipped contract_id=%s status=%s",
            contract_id,
            contract.status,
        )
        return "skipped"

    if (
        contract.generated_pdf_id
        and contract.generated_pdf is not None
        and contract.docuseal_submission_id
    ):
        try:
            merge_values = build_merge_values(contract)
            version = contract.template_version
            source_checksum = (
                version.source_checksum if version else ""
            ) or f"docuseal:{getattr(version, 'docuseal_template_id', '')}"
            fingerprint = input_fingerprint(
                contract,
                merge_values=merge_values,
                source_checksum=source_checksum,
            )
            current = contract.generated_pdf
            if (
                current.input_fingerprint == fingerprint
                and current.checksum
                and current.file
            ):
                return "ready_idempotent"
        except PdfGenerationError:
            pass

    try:
        rendered = render_contract_pdf(contract)
    except PdfGenerationError as exc:
        if not exc.retryable:
            mark_generation_failed(contract_id, code=exc.code)
            logger.warning(
                "generate_contract_pdf terminal contract_id=%s code=%s",
                contract_id,
                exc.code,
            )
            return f"failed:{exc.code}"
        raise

    artifact, emitted = attach_generated_pdf(contract, rendered)
    logger.info(
        "generate_contract_pdf ready contract_id=%s artifact=%s emitted=%s bytes=%s",
        contract_id,
        artifact.public_id,
        emitted,
        artifact.byte_size,
    )
    return "ready" if emitted else "ready_idempotent"
