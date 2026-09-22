"""Sealed-artifact production for a fully signed package.

Runs once every signer has a durable ``SignatureRecord``. For each document it
re-verifies the frozen source bytes, stamps every signer's appearance in
routing order, appends the package certificate of completion, and applies the
organization PAdES seal. One signed PDF per package document plus one
package-level certificate; the source versions are then locked as signed.

The whole run is idempotent — a retry after a partial failure reuses artifacts
that already exist rather than minting a second copy. Log lines carry ids and
outcome codes only, never a signer name, email, or request metadata.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.transactions.media import checksum_of
from apps.transactions.models import (
    SignatureArtifact,
    SignaturePackage,
    SignaturePackageDocument,
    SignaturePackageField,
    SignaturePackageSigner,
    SignatureRecord,
    TransactionDocumentVersion,
)
from apps.transactions.signing.certificate import (
    CERTIFICATE_RENDERER_VERSION,
    build_package_certificate_of_completion,
)
from apps.transactions.signing.lifecycle import (
    EVENT_PACKAGE_COMPLETED,
    all_signers_signed,
    lock_package,
    publish_package_event,
    set_package_status,
)
from apps.transactions.signing.pdf_stamp import (
    RENDERER_VERSION,
    append_pages,
    seal_pdf_with_org_cert,
    stamp_signer_package_fields,
)
from apps.transactions.taxonomy import (
    DocumentSignatureStatus,
    SignatureArtifactKind,
    SignaturePackageStatus,
)

logger = logging.getLogger("apps.transactions")

MEDIA_TYPE_PDF = "application/pdf"


class FinalizationError(Exception):
    """Terminal or retryable failure carrying a code, never PII."""

    def __init__(self, code: str, *, retryable: bool = True):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def _read_field_bytes(field) -> bytes:
    field.open("rb")
    try:
        return field.read()
    finally:
        field.close()


def _layout_by_document(package_id: int) -> dict[int, list[dict[str, Any]]]:
    layout: dict[int, list[dict[str, Any]]] = {}
    rows = SignaturePackageField.objects.filter(package_id=package_id).select_related(
        "signer", "document"
    )
    for field in rows:
        layout.setdefault(field.document_id, []).append(
            {
                "name": field.name,
                "type": field.field_type,
                "signerKey": str(field.signer.public_id),
                "documentKey": str(field.document.public_id),
                "page": field.page,
                "x": field.x,
                "y": field.y,
                "w": field.w,
                "h": field.h,
                "required": field.required,
            }
        )
    return layout


def _ordered_records(package_id: int) -> list[SignatureRecord]:
    """Signature evidence in routing order, so ink lands deterministically."""
    return list(
        SignatureRecord.objects.filter(package_id=package_id)
        .select_related("signer", "intent")
        .order_by("signer__routing_order", "signer__pk")
    )


def _certificate_facts(
    package: SignaturePackage,
    *,
    records: list[SignatureRecord],
    documents: list[SignaturePackageDocument],
    signed_checksums: dict[int, str],
    seal_subject: str = "",
    seal_fingerprint: str = "",
) -> dict[str, Any]:
    tx = package.transaction
    return {
        "packagePublicId": str(package.public_id),
        "packageTitle": package.title,
        "transactionPublicId": str(tx.public_id),
        "transactionReference": tx.reference,
        "routingMode": package.routing_mode,
        "disclosureVersion": package.disclosure_version,
        "sentAt": package.sent_at.isoformat() if package.sent_at else "",
        "completedAt": package.completed_at.isoformat()
        if package.completed_at
        else timezone.now().isoformat(),
        "sealCertSubject": seal_subject,
        "sealCertFingerprint": seal_fingerprint,
        "rendererVersion": RENDERER_VERSION,
        "documents": [
            {
                "publicId": str(document.public_id),
                "versionPublicId": str(document.version.public_id),
                "displayName": document.version.display_name,
                "pageCount": document.page_count,
                "sourceChecksum": document.source_checksum,
                "signedChecksum": signed_checksums.get(document.pk, ""),
            }
            for document in documents
        ],
        "signers": [
            {
                "displayName": record.signer.display_name,
                "roleLabel": record.signer.role_label,
                "email": record.signer.email,
                "deliveryMethod": record.signer.delivery_method,
                "routingOrder": record.signer.routing_order,
                "signaturePublicId": str(record.public_id),
                "intentPublicId": str(record.intent.public_id)
                if record.intent_id
                else "",
                "consentAcceptedAt": record.intent.consent_accepted_at.isoformat()
                if record.intent_id
                else "",
                "signedAt": record.signed_at.isoformat(),
                "method": record.method,
                "disclosureVersion": record.disclosure_version,
                "appearanceChecksum": record.appearance_checksum,
                "requestIpHash": record.request_ip_hash,
                "requestUaHash": record.request_ua_hash,
            }
            for record in records
        ],
    }


def _stamped_document_bytes(
    document: SignaturePackageDocument,
    *,
    records: list[SignatureRecord],
    layout: list[dict[str, Any]],
) -> bytes:
    """Verify the frozen source, then lay every signer's ink onto it."""
    source = _read_field_bytes(document.version.file)
    if checksum_of(source) != (document.source_checksum or "").lower():
        raise FinalizationError("source_checksum_mismatch", retryable=False)

    stamped = source
    for record in records:
        if not record.appearance_file:
            raise FinalizationError("missing_appearance", retryable=False)
        appearance = _read_field_bytes(record.appearance_file)
        if checksum_of(appearance) != (record.appearance_checksum or "").lower():
            raise FinalizationError("appearance_checksum_mismatch", retryable=False)
        initials = (
            _read_field_bytes(record.initials_file) if record.initials_file else b""
        )
        stamped = stamp_signer_package_fields(
            stamped,
            fields=layout,
            signer_key=str(record.signer.public_id),
            signature_png=appearance,
            signed_date=record.signed_date_value or "",
            initials_png=initials,
            text_values=dict(record.field_values or {}),
        )
    return stamped


def _store_artifact(
    *,
    package: SignaturePackage,
    package_document: SignaturePackageDocument | None,
    kind: str,
    display_name: str,
    data: bytes,
    source_checksum: str = "",
) -> SignatureArtifact:
    artifact = SignatureArtifact(
        package=package,
        package_document=package_document,
        kind=kind,
        display_name=display_name[:180],
        media_type=MEDIA_TYPE_PDF,
        byte_size=len(data),
        checksum=checksum_of(data),
        source_checksum=source_checksum,
    )
    artifact.full_clean(exclude={"file"})
    artifact.file.save(display_name[:180], ContentFile(data), save=False)
    artifact.save()
    return artifact


def _lock_source_versions(package_id: int, *, now) -> int:
    version_ids = list(
        SignaturePackageDocument.objects.filter(package_id=package_id).values_list(
            "version_id", flat=True
        )
    )
    if not version_ids:
        return 0
    locked = 0
    for version in TransactionDocumentVersion.objects.filter(pk__in=version_ids):
        version.signature_status = DocumentSignatureStatus.SIGNED
        update_fields = ["signature_status", "updated_at"]
        if version.locked_at is None:
            version.locked_at = now
            version.lock_reason = "signed"
            update_fields.extend(["locked_at", "lock_reason"])
        version.save(update_fields=update_fields)
        locked += 1
    return locked


def _queue_completion_emails(package_id: int) -> None:
    def _send() -> None:
        from apps.transactions.signing.emails import send_package_completed_email

        signers = SignaturePackageSigner.objects.select_related("package").filter(
            package_id=package_id
        )
        for signer in signers:
            send_package_completed_email(signer)

    db_transaction.on_commit(_send)


@db_transaction.atomic
def finalize_package(package_id: int) -> str:
    """Produce sealed artifacts and complete the package. Safe to re-run."""
    package = (
        SignaturePackage.objects.select_related("transaction")
        .filter(pk=package_id)
        .first()
    )
    if package is None:
        return "missing"

    locked = lock_package(package.pk)
    locked.transaction = package.transaction
    if locked.status == SignaturePackageStatus.COMPLETED:
        return "already"
    if locked.status in {
        SignaturePackageStatus.DECLINED,
        SignaturePackageStatus.CANCELLED,
        SignaturePackageStatus.EXPIRED,
    }:
        return f"skipped:{locked.status}"
    if not all_signers_signed(locked):
        return "incomplete"

    documents = list(
        SignaturePackageDocument.objects.filter(package_id=locked.pk)
        .select_related("version")
        .order_by("sort_order", "pk")
    )
    if not documents:
        raise FinalizationError("no_documents", retryable=False)

    records = _ordered_records(locked.pk)
    if not records:
        raise FinalizationError("no_signature_records", retryable=False)

    layouts = _layout_by_document(locked.pk)
    existing = {
        artifact.package_document_id: artifact
        for artifact in SignatureArtifact.objects.filter(
            package_id=locked.pk, kind=SignatureArtifactKind.SIGNED_PDF
        )
    }

    # The embedded certificate is rendered before sealing, so it cannot carry
    # its own output checksum; the standalone certificate below does.
    pre_seal_facts = _certificate_facts(
        locked, records=records, documents=documents, signed_checksums={}
    )
    certificate_page = build_package_certificate_of_completion(pre_seal_facts)

    signed_checksums: dict[int, str] = {}
    seal_subject = ""
    seal_fingerprint = ""
    for document in documents:
        already = existing.get(document.pk)
        if already is not None:
            signed_checksums[document.pk] = already.checksum
            continue

        stamped = _stamped_document_bytes(
            document, records=records, layout=layouts.get(document.pk, [])
        )
        combined = append_pages(stamped, extra_pdf=certificate_page)
        sealed = seal_pdf_with_org_cert(combined)
        seal_subject = sealed.cert_subject or seal_subject
        seal_fingerprint = sealed.cert_fingerprint or seal_fingerprint

        artifact = _store_artifact(
            package=locked,
            package_document=document,
            kind=SignatureArtifactKind.SIGNED_PDF,
            display_name=f"{document.version.display_name}".rsplit(".", 1)[0][:150]
            + "-signed.pdf",
            data=sealed.pdf_bytes,
            source_checksum=document.source_checksum,
        )
        signed_checksums[document.pk] = artifact.checksum

    certificate_exists = SignatureArtifact.objects.filter(
        package_id=locked.pk,
        package_document__isnull=True,
        kind=SignatureArtifactKind.CERTIFICATE_OF_COMPLETION,
    ).exists()
    if not certificate_exists:
        final_facts = _certificate_facts(
            locked,
            records=records,
            documents=documents,
            signed_checksums=signed_checksums,
            seal_subject=seal_subject,
            seal_fingerprint=seal_fingerprint,
        )
        final_facts["rendererVersion"] = CERTIFICATE_RENDERER_VERSION
        _store_artifact(
            package=locked,
            package_document=None,
            kind=SignatureArtifactKind.CERTIFICATE_OF_COMPLETION,
            display_name=f"package-{locked.public_id}-certificate.pdf",
            data=build_package_certificate_of_completion(final_facts),
        )

    now = timezone.now()
    _lock_source_versions(locked.pk, now=now)
    set_package_status(locked, SignaturePackageStatus.COMPLETED, completed_at=now)

    publish_package_event(
        EVENT_PACKAGE_COMPLETED,
        locked,
        document_count=str(len(documents)),
        signer_count=str(len(records)),
    )
    _queue_completion_emails(locked.pk)

    logger.info(
        "transactions: signature package finalized package_id=%s documents=%s",
        locked.pk,
        len(documents),
    )
    return "completed"


__all__ = ["FinalizationError", "finalize_package"]
