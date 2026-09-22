"""CamelCase projections for the Signatures workspace section and ceremony.

Two audiences with different rights: a workspace reader sees package state and
every signer's progress, while a signer in the ceremony sees only their own
fields. Checksums and hashed request metadata are manager-only, and neither
projection ever carries a raw token, IP address, or user agent.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch
from django.urls import NoReverseMatch, reverse

from apps.transactions.models import (
    SignatureArtifact,
    SignaturePackage,
    SignaturePackageDocument,
    SignaturePackageField,
    SignaturePackageSigner,
    SignatureRecord,
    Transaction,
)
from apps.transactions.signing.disclosure import disclosure_payload
from apps.transactions.taxonomy import (
    SIGNATURE_ARTIFACT_KIND_LABELS,
    SIGNATURE_DELIVERY_METHOD_CODES,
    SIGNATURE_DELIVERY_METHOD_LABELS,
    SIGNATURE_FIELD_TYPE_CODES,
    SIGNATURE_FIELD_TYPE_LABELS,
    SIGNATURE_PACKAGE_STATUS_CODES,
    SIGNATURE_PACKAGE_STATUS_LABELS,
    SIGNATURE_ROUTING_MODE_CODES,
    SIGNATURE_ROUTING_MODE_LABELS,
    SIGNATURE_SIGNER_STATUS_CODES,
    SIGNATURE_SIGNER_STATUS_LABELS,
    TERMINAL_SIGNATURE_PACKAGE_STATUSES,
    SignaturePackageStatus,
)
from apps.user.models import User

#: Placeholder routes until the signing views land in ``urls.py``.
CEREMONY_ROUTE = "transaction_signature_ceremony"
CEREMONY_PATH = "/transactions/sign/{package_id}/"
DOCUMENT_PREVIEW_ROUTE = "transaction_signature_document_preview"
DOCUMENT_PREVIEW_PATH = "/transactions/sign/{package_id}/documents/{document_id}/"
ARTIFACT_DOWNLOAD_ROUTE = "transaction_signature_artifact_download"
ARTIFACT_DOWNLOAD_PATH = "/transactions/signatures/artifacts/{artifact_id}/"


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _label(mapping: dict[str, str], code: str) -> str:
    return str(mapping.get(code, code))


def ceremony_path(package: SignaturePackage) -> str:
    try:
        return reverse(CEREMONY_ROUTE, kwargs={"public_id": package.public_id})
    except NoReverseMatch:
        return CEREMONY_PATH.format(package_id=package.public_id)


def document_preview_path(document: SignaturePackageDocument) -> str:
    package_id = document.package.public_id
    try:
        return reverse(
            DOCUMENT_PREVIEW_ROUTE,
            kwargs={"public_id": package_id, "document_id": document.public_id},
        )
    except NoReverseMatch:
        return DOCUMENT_PREVIEW_PATH.format(
            package_id=package_id, document_id=document.public_id
        )


def artifact_download_path(artifact: SignatureArtifact) -> str:
    try:
        return reverse(
            ARTIFACT_DOWNLOAD_ROUTE, kwargs={"public_id": artifact.public_id}
        )
    except NoReverseMatch:
        return ARTIFACT_DOWNLOAD_PATH.format(artifact_id=artifact.public_id)


def serialize_field(field: SignaturePackageField) -> dict[str, Any]:
    """Geometry the placer and the ceremony both read."""
    return {
        "publicId": str(field.public_id),
        "name": field.name,
        "type": field.field_type,
        "typeLabel": _label(SIGNATURE_FIELD_TYPE_LABELS, field.field_type),
        "signerKey": str(field.signer.public_id),
        "documentKey": str(field.document.public_id),
        "page": field.page,
        "x": field.x,
        "y": field.y,
        "w": field.w,
        "h": field.h,
        "required": field.required,
    }


def serialize_package_document(
    document: SignaturePackageDocument, *, can_manage: bool
) -> dict[str, Any]:
    version = document.version
    return {
        "publicId": str(document.public_id),
        "versionPublicId": str(version.public_id),
        "displayName": version.display_name,
        "pageCount": document.page_count,
        "sortOrder": document.sort_order,
        "sourceChecksum": document.source_checksum if can_manage else "",
        "previewUrl": document_preview_path(document),
    }


def serialize_signer(
    signer: SignaturePackageSigner, *, can_manage: bool
) -> dict[str, Any]:
    return {
        "publicId": str(signer.public_id),
        "signerKey": signer.signer_key,
        "roleLabel": signer.role_label,
        "displayName": signer.display_name,
        "email": signer.email if can_manage else "",
        "deliveryMethod": signer.delivery_method,
        "deliveryMethodLabel": _label(
            SIGNATURE_DELIVERY_METHOD_LABELS, signer.delivery_method
        ),
        "routingOrder": signer.routing_order,
        "status": signer.status,
        "statusLabel": _label(SIGNATURE_SIGNER_STATUS_LABELS, signer.status),
        "isHubUser": signer.user_id is not None,
        "partyPublicId": str(signer.party.public_id)
        if signer.party_id and signer.party
        else None,
        "invitedAt": _iso(signer.invited_at),
        "viewedAt": _iso(signer.viewed_at),
        "signedAt": _iso(signer.signed_at),
        "declinedAt": _iso(signer.declined_at),
        "declineReason": signer.decline_reason if can_manage else "",
    }


def serialize_artifact(
    artifact: SignatureArtifact, *, can_manage: bool
) -> dict[str, Any]:
    return {
        "publicId": str(artifact.public_id),
        "kind": artifact.kind,
        "kindLabel": _label(SIGNATURE_ARTIFACT_KIND_LABELS, artifact.kind),
        "displayName": artifact.display_name,
        "packageDocumentPublicId": str(artifact.package_document.public_id)
        if artifact.package_document_id and artifact.package_document
        else None,
        "mediaType": artifact.media_type,
        "byteSize": artifact.byte_size,
        "checksum": artifact.checksum if can_manage else "",
        "createdAt": _iso(artifact.created_at),
        "downloadUrl": artifact_download_path(artifact),
    }


def serialize_package(
    package: SignaturePackage,
    *,
    can_manage: bool,
    include_fields: bool = False,
) -> dict[str, Any]:
    """One package row for the workspace Signatures section."""
    documents = list(package.documents.all())
    signers = list(package.signers.all())
    artifacts = list(package.artifacts.all())

    signed = sum(1 for s in signers if s.signed_at is not None)
    payload: dict[str, Any] = {
        "publicId": str(package.public_id),
        "title": package.title,
        "status": package.status,
        "statusLabel": _label(SIGNATURE_PACKAGE_STATUS_LABELS, package.status),
        "routingMode": package.routing_mode,
        "routingModeLabel": _label(SIGNATURE_ROUTING_MODE_LABELS, package.routing_mode),
        "disclosureVersion": package.disclosure_version,
        "isDraft": package.status == SignaturePackageStatus.DRAFT,
        "isTerminal": package.status in TERMINAL_SIGNATURE_PACKAGE_STATUSES,
        "expiresAt": _iso(package.expires_at),
        "sentAt": _iso(package.sent_at),
        "completedAt": _iso(package.completed_at),
        "cancelledAt": _iso(package.cancelled_at),
        "createdAt": _iso(package.created_at),
        "updatedAt": _iso(package.updated_at),
        "progress": {"signed": signed, "total": len(signers)},
        "documents": [
            serialize_package_document(document, can_manage=can_manage)
            for document in documents
        ],
        "signers": [
            serialize_signer(signer, can_manage=can_manage) for signer in signers
        ],
        "artifacts": [
            serialize_artifact(artifact, can_manage=can_manage)
            for artifact in artifacts
        ],
        "ceremonyUrl": ceremony_path(package),
    }
    if include_fields:
        fields = SignaturePackageField.objects.filter(
            package_id=package.pk
        ).select_related("signer", "document")
        payload["fields"] = [serialize_field(field) for field in fields]
    return payload


def serialize_packages_for_reader(user: User, tx: Transaction) -> list[dict[str, Any]]:
    """Every package on a deal, newest first, projected for this reader."""
    from apps.transactions.concurrency import can_manage_workspace

    can_manage = can_manage_workspace(user, tx)
    packages = (
        SignaturePackage.objects.filter(transaction_id=tx.pk)
        .prefetch_related(
            Prefetch(
                "documents",
                queryset=SignaturePackageDocument.objects.select_related(
                    "version", "package"
                ).order_by("sort_order", "pk"),
            ),
            Prefetch(
                "signers",
                queryset=SignaturePackageSigner.objects.select_related(
                    "party"
                ).order_by("routing_order", "pk"),
            ),
            Prefetch(
                "artifacts",
                queryset=SignatureArtifact.objects.select_related(
                    "package_document"
                ).order_by("kind", "pk"),
            ),
        )
        .order_by("-created_at", "-pk")
    )
    # A draft is still editable, and the authoring UI replaces contents
    # wholesale — without its layout it would save the package back with every
    # field dropped. Sent and terminal packages are read-only, so their
    # geometry stays out of the workspace payload.
    return [
        serialize_package(
            package,
            can_manage=can_manage,
            include_fields=can_manage
            and package.status == SignaturePackageStatus.DRAFT,
        )
        for package in packages
    ]


def signature_schema_payload() -> dict[str, Any]:
    """Closed vocabularies the authoring UI renders as choices."""
    return {
        "packageStatuses": [
            {"value": code, "label": _label(SIGNATURE_PACKAGE_STATUS_LABELS, code)}
            for code in sorted(SIGNATURE_PACKAGE_STATUS_CODES)
        ],
        "routingModes": [
            {"value": code, "label": _label(SIGNATURE_ROUTING_MODE_LABELS, code)}
            for code in sorted(SIGNATURE_ROUTING_MODE_CODES)
        ],
        "deliveryMethods": [
            {"value": code, "label": _label(SIGNATURE_DELIVERY_METHOD_LABELS, code)}
            for code in sorted(SIGNATURE_DELIVERY_METHOD_CODES)
        ],
        "signerStatuses": [
            {"value": code, "label": _label(SIGNATURE_SIGNER_STATUS_LABELS, code)}
            for code in sorted(SIGNATURE_SIGNER_STATUS_CODES)
        ],
        "fieldTypes": [
            {"value": code, "label": _label(SIGNATURE_FIELD_TYPE_LABELS, code)}
            for code in sorted(SIGNATURE_FIELD_TYPE_CODES)
        ],
        "disclosure": disclosure_payload(),
    }


def serialize_ceremony_document(
    document: SignaturePackageDocument,
    *,
    fields: list[SignaturePackageField],
) -> dict[str, Any]:
    """One document as the signer sees it: preview plus their own boxes."""
    return {
        "publicId": str(document.public_id),
        "displayName": document.version.display_name,
        "pageCount": document.page_count,
        "sortOrder": document.sort_order,
        "previewUrl": document_preview_path(document),
        "fields": [serialize_field(field) for field in fields],
    }


def serialize_ceremony_signer(signer: SignaturePackageSigner) -> dict[str, Any]:
    """The signer's own identity block — no sibling signer detail."""
    return {
        "publicId": str(signer.public_id),
        "roleLabel": signer.role_label,
        "displayName": signer.display_name,
        "email": signer.email,
        "status": signer.status,
        "statusLabel": _label(SIGNATURE_SIGNER_STATUS_LABELS, signer.status),
        "routingOrder": signer.routing_order,
        "signedAt": _iso(signer.signed_at),
    }


def serialize_signature_record(record: SignatureRecord) -> dict[str, Any]:
    return {
        "publicId": str(record.public_id),
        "signedAt": _iso(record.signed_at),
        "method": record.method,
        "disclosureVersion": record.disclosure_version,
    }


__all__ = [
    "artifact_download_path",
    "ceremony_path",
    "document_preview_path",
    "serialize_artifact",
    "serialize_ceremony_document",
    "serialize_ceremony_signer",
    "serialize_field",
    "serialize_package",
    "serialize_package_document",
    "serialize_packages_for_reader",
    "serialize_signature_record",
    "serialize_signer",
    "signature_schema_payload",
]
