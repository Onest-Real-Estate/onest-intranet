"""Deal document packages: upload, classify, version, lock, retire, serialize."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.service import AuditTarget, actor_from_user, log_on_commit
from apps.transactions.concurrency import (
    can_manage_workspace,
    require_writable_transaction,
    touch_transaction,
)
from apps.transactions.media import (
    MAX_TRANSACTION_DOCUMENTS,
    allowed_matrix_payload,
    inspect_transaction_upload,
)
from apps.transactions.models import (
    Transaction,
    TransactionDocument,
    TransactionDocumentVersion,
)
from apps.transactions.taxonomy import (
    DOCUMENT_CATEGORY_CODES,
    DOCUMENT_CATEGORY_LABELS,
    DOCUMENT_COMPLIANCE_STATUS_CODES,
    DOCUMENT_COMPLIANCE_STATUS_LABELS,
    DOCUMENT_REQUIREMENT_CODES,
    DOCUMENT_REQUIREMENT_LABELS,
    DOCUMENT_RETENTION_POLICY_CODES,
    DOCUMENT_RETENTION_POLICY_LABELS,
    DOCUMENT_SIGNATURE_STATUS_CODES,
    DOCUMENT_SIGNATURE_STATUS_LABELS,
    DocumentCategory,
    DocumentComplianceStatus,
    DocumentRequirement,
    DocumentRetentionPolicy,
    DocumentSignatureStatus,
)
from apps.user.models import User

State = TransactionDocumentVersion.ProcessingState


def _audit_target(tx: Transaction) -> AuditTarget:
    return AuditTarget(
        target_type="transaction.transaction",
        target_id=str(tx.public_id),
        target_label=tx.reference or str(tx.public_id),
        target_snapshot={
            "public_id": str(tx.public_id),
            "reference": tx.reference,
            "status": tx.status,
            "office_id": tx.office.stable_key if tx.office_pk else "",
        },
    )


def _version_target(version: TransactionDocumentVersion) -> AuditTarget:
    return AuditTarget(
        target_type="transaction.document_version",
        target_id=str(version.public_id),
        target_label=version.display_name,
        target_snapshot={
            "document_id": str(version.document.public_id),
            "version_number": version.version_number,
            "processing_state": version.processing_state,
            "checksum": version.checksum,
        },
    )


def _assert_package_room(tx: Transaction) -> None:
    count = TransactionDocument.objects.filter(
        transaction=tx, ended_at__isnull=True
    ).count()
    if count >= MAX_TRANSACTION_DOCUMENTS:
        raise ValidationError(
            {
                "file": _(
                    f"A transaction can carry at most {MAX_TRANSACTION_DOCUMENTS} "
                    "documents."
                )
            }
        )


def _next_version_number(document: TransactionDocument) -> int:
    current = (
        TransactionDocumentVersion.objects.filter(document=document)
        .aggregate(max_n=Max("version_number"))
        .get("max_n")
    )
    return 1 if current is None else int(current) + 1


def _parse_retain_until(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(
            {"retainUntil": ["Use an ISO date (YYYY-MM-DD)."]}
        ) from exc


def _parse_classify(
    payload: dict[str, Any], *, require_title: bool = True
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    if require_title and not title:
        raise ValidationError({"title": ["A document title is required."]})
    if len(title) > 180:
        raise ValidationError({"title": ["Titles are limited to 180 characters."]})

    category = str(payload.get("category") or DocumentCategory.OTHER).strip()
    if category not in DOCUMENT_CATEGORY_CODES:
        raise ValidationError({"category": ["Unknown document category."]})

    requirement = str(
        payload.get("requirement") or DocumentRequirement.OPTIONAL
    ).strip()
    if requirement not in DOCUMENT_REQUIREMENT_CODES:
        raise ValidationError({"requirement": ["Unknown requirement."]})

    retention_policy = str(
        payload.get("retentionPolicy")
        or payload.get("retention_policy")
        or DocumentRetentionPolicy.DEAL_CLOSE_PLUS_7Y
    ).strip()
    if retention_policy not in DOCUMENT_RETENTION_POLICY_CODES:
        raise ValidationError({"retentionPolicy": ["Unknown retention policy."]})

    retain_until = _parse_retain_until(
        payload.get("retainUntil") or payload.get("retain_until")
    )
    if retention_policy == DocumentRetentionPolicy.CUSTOM and retain_until is None:
        raise ValidationError(
            {"retainUntil": ["A retain-until date is required for custom retention."]}
        )
    if retention_policy != DocumentRetentionPolicy.CUSTOM:
        retain_until = None

    return {
        "title": title,
        "category": category,
        "requirement": requirement,
        "retention_policy": retention_policy,
        "retain_until": retain_until,
    }


def refresh_current_version(document: TransactionDocument) -> None:
    """Deterministic current: highest ready version_number, then pk."""
    ready = (
        TransactionDocumentVersion.objects.filter(
            document_id=document.pk,
            is_active=True,
            processing_state=State.READY,
        )
        .order_by("-version_number", "-pk")
        .first()
    )
    new_id = ready.pk if ready else None
    # Always write from a fresh DB read of the package so a stale in-memory
    # ``current_version_id`` cannot skip the update after Celery processing.
    TransactionDocument.objects.filter(pk=document.pk).update(current_version_id=new_id)
    document.current_version = ready


def assert_version_mutable(version: TransactionDocumentVersion) -> None:
    if version.is_locked:
        raise ValidationError(
            {
                "file": _(
                    "Signed or approved document versions cannot be replaced "
                    "or deleted. Upload a new revision instead."
                )
            }
        )


def _person(user: User | None) -> dict[str, Any] | None:
    if user is None or not getattr(user, "pk", None):
        return None
    return {
        "id": str(user.pk),
        "displayName": (
            user.preferred_display_name()
            if hasattr(user, "preferred_display_name")
            else str(user)
        ),
    }


def version_urls(version: TransactionDocumentVersion) -> dict[str, str]:
    if not version.is_readable:
        return {"downloadUrl": "", "previewUrl": ""}
    return {
        "downloadUrl": reverse(
            "transaction_document_download",
            kwargs={"public_id": version.public_id},
        ),
        "previewUrl": reverse(
            "transaction_document_preview",
            kwargs={"public_id": version.public_id},
        ),
    }


def serialize_version(
    version: TransactionDocumentVersion,
    *,
    can_manage: bool,
    is_current: bool,
) -> dict[str, Any] | None:
    """Hide non-ready rows from ordinary readers; managers see triage labels."""
    if not version.is_readable and not can_manage:
        return None
    urls = (
        version_urls(version)
        if version.is_readable
        else {
            "downloadUrl": "",
            "previewUrl": "",
        }
    )
    return {
        "publicId": str(version.public_id),
        "versionNumber": version.version_number,
        "originalName": version.original_name,
        "displayName": version.display_name,
        "mediaType": version.media_type,
        "byteSize": version.byte_size,
        "checksum": version.checksum if can_manage else "",
        "processingState": version.processing_state,
        "processingNote": version.processing_note if can_manage else "",
        "isReadable": version.is_readable,
        "isCurrent": is_current and version.is_readable,
        "isLocked": version.is_locked,
        "signatureStatus": version.signature_status,
        "signatureStatusLabel": str(
            DOCUMENT_SIGNATURE_STATUS_LABELS.get(
                version.signature_status, version.signature_status
            )
        ),
        "complianceStatus": version.compliance_status,
        "complianceStatusLabel": str(
            DOCUMENT_COMPLIANCE_STATUS_LABELS.get(
                version.compliance_status, version.compliance_status
            )
        ),
        "lockedAt": version.locked_at.isoformat() if version.locked_at else None,
        "lockReason": version.lock_reason,
        "uploadedBy": _person(version.uploaded_by),
        "createdAt": version.created_at.isoformat() if version.created_at else None,
        **urls,
    }


def serialize_documents_for_reader(user: User, tx: Transaction) -> list[dict[str, Any]]:
    from apps.transactions.document_reviews import serialize_comments_for_reader

    can_manage = can_manage_workspace(user, tx)
    packages = (
        TransactionDocument.objects.filter(transaction=tx, ended_at__isnull=True)
        .select_related("current_version", "created_by")
        .prefetch_related(
            models.Prefetch(
                "versions",
                queryset=TransactionDocumentVersion.objects.filter(is_active=True)
                .select_related("uploaded_by", "locked_by")
                .order_by("-version_number", "-pk"),
            )
        )
        .order_by("category", "title", "pk")
    )
    rows: list[dict[str, Any]] = []
    for package in packages:
        current_id = package.current_version_pk
        versions_out: list[dict[str, Any]] = []
        version_qs = TransactionDocumentVersion.objects.filter(
            document=package, is_active=True
        ).select_related("uploaded_by", "locked_by")
        # Prefer prefetched cache when workspace serialization loaded it.
        cache = getattr(package, "_prefetched_objects_cache", {})
        version_rows = cache.get("versions")
        if version_rows is None:
            version_rows = list(version_qs.order_by("-version_number", "-pk"))
        for version in version_rows:
            payload = serialize_version(
                version,
                can_manage=can_manage,
                is_current=version.pk == current_id,
            )
            if payload is None:
                continue
            payload["reviewComments"] = serialize_comments_for_reader(user, version)
            versions_out.append(payload)
        current_payload = None
        current = package.current_version
        if current is not None:
            current_pid = str(current.public_id)
            current_payload = next(
                (v for v in versions_out if v["publicId"] == current_pid),
                None,
            )
        rows.append(
            {
                "publicId": str(package.public_id),
                "title": package.title,
                "category": package.category,
                "categoryLabel": package.category_label,
                "requirement": package.requirement,
                "requirementLabel": package.requirement_label,
                "retentionPolicy": package.retention_policy,
                "retentionPolicyLabel": str(
                    DOCUMENT_RETENTION_POLICY_LABELS.get(
                        package.retention_policy, package.retention_policy
                    )
                ),
                "retainUntil": (
                    package.retain_until.isoformat() if package.retain_until else None
                ),
                "createdBy": _person(package.created_by),
                "createdAt": package.created_at.isoformat()
                if package.created_at
                else None,
                "updatedAt": package.updated_at.isoformat()
                if package.updated_at
                else None,
                "currentVersion": current_payload,
                "versions": versions_out,
            }
        )
    return rows


def document_schema_payload() -> dict[str, Any]:
    return {
        "categories": [
            {"value": code, "label": str(DOCUMENT_CATEGORY_LABELS[code])}
            for code in sorted(DOCUMENT_CATEGORY_CODES)
        ],
        "requirements": [
            {"value": code, "label": str(DOCUMENT_REQUIREMENT_LABELS[code])}
            for code in sorted(DOCUMENT_REQUIREMENT_CODES)
        ],
        "retentionPolicies": [
            {"value": code, "label": str(DOCUMENT_RETENTION_POLICY_LABELS[code])}
            for code in sorted(DOCUMENT_RETENTION_POLICY_CODES)
        ],
        "signatureStatuses": [
            {"value": code, "label": str(DOCUMENT_SIGNATURE_STATUS_LABELS[code])}
            for code in sorted(DOCUMENT_SIGNATURE_STATUS_CODES)
        ],
        "complianceStatuses": [
            {"value": code, "label": str(DOCUMENT_COMPLIANCE_STATUS_LABELS[code])}
            for code in sorted(DOCUMENT_COMPLIANCE_STATUS_CODES)
        ],
        "matrix": allowed_matrix_payload()["document"],
    }


def _create_version(
    *,
    actor: User,
    document: TransactionDocument,
    uploaded,
) -> TransactionDocumentVersion:
    inspected, data = inspect_transaction_upload(uploaded)
    version = TransactionDocumentVersion(
        document=document,
        version_number=_next_version_number(document),
        original_name=getattr(uploaded, "name", "") or inspected.display_name,
        display_name=inspected.display_name,
        media_type=inspected.media_type,
        byte_size=inspected.byte_size,
        checksum=inspected.checksum,
        processing_state=State.PENDING,
        uploaded_by=actor,
    )
    version.file.save(inspected.display_name, ContentFile(data), save=False)
    version.full_clean(exclude={"uploaded_by", "locked_by"})
    version.save()
    return version


def _enqueue_processing(version_id: int) -> None:
    from apps.transactions.tasks import process_transaction_document_version

    transaction.on_commit(
        lambda: process_transaction_document_version.delay(version_id)
    )


@transaction.atomic
def upload_document(
    *,
    actor: User,
    public_id: UUID,
    expected_version: str,
    uploaded,
    payload: dict[str, Any] | None = None,
) -> TransactionDocument:
    """Create a package + first version from an upload."""
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    _assert_package_room(tx)
    fields = _parse_classify(payload or {}, require_title=False)
    if not fields["title"]:
        fields["title"] = (getattr(uploaded, "name", "") or "Document").rsplit(".", 1)[
            0
        ][:180] or "Document"

    package = TransactionDocument(
        transaction=tx,
        title=fields["title"],
        category=fields["category"],
        requirement=fields["requirement"],
        retention_policy=fields["retention_policy"],
        retain_until=fields["retain_until"],
        created_by=actor,
    )
    package.full_clean(exclude={"created_by", "current_version"})
    package.save()

    version = _create_version(actor=actor, document=package, uploaded=uploaded)
    touch_transaction(tx)
    _enqueue_processing(version.pk)

    log_on_commit(
        "transaction.document_uploaded",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        after={
            "document_id": str(package.public_id),
            "version_id": str(version.public_id),
            "version_number": version.version_number,
            "category": package.category,
            "display_name": version.display_name,
        },
    )
    return package


@transaction.atomic
def upload_revision(
    *,
    actor: User,
    public_id: UUID,
    document_public_id: UUID,
    expected_version: str,
    uploaded,
) -> TransactionDocumentVersion:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    package = (
        TransactionDocument.objects.select_for_update(of=("self",))
        .filter(
            public_id=document_public_id,
            transaction=tx,
            ended_at__isnull=True,
        )
        .first()
    )
    if package is None:
        raise ValidationError({"document": ["No document matches that id."]})

    # Locked current versions stay; new revision is always allowed.
    version = _create_version(actor=actor, document=package, uploaded=uploaded)
    touch_transaction(tx)
    _enqueue_processing(version.pk)

    log_on_commit(
        "transaction.document_revision_uploaded",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        after={
            "document_id": str(package.public_id),
            "version_id": str(version.public_id),
            "version_number": version.version_number,
        },
    )
    return version


@transaction.atomic
def classify_document(
    *,
    actor: User,
    public_id: UUID,
    document_public_id: UUID,
    expected_version: str,
    payload: dict[str, Any],
) -> TransactionDocument:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    package = (
        TransactionDocument.objects.select_for_update(of=("self",))
        .filter(
            public_id=document_public_id,
            transaction=tx,
            ended_at__isnull=True,
        )
        .first()
    )
    if package is None:
        raise ValidationError({"document": ["No document matches that id."]})
    fields = _parse_classify(payload)
    package.title = fields["title"]
    package.category = fields["category"]
    package.requirement = fields["requirement"]
    package.retention_policy = fields["retention_policy"]
    package.retain_until = fields["retain_until"]
    package.full_clean(exclude={"created_by", "current_version"})
    package.save()
    touch_transaction(tx)
    log_on_commit(
        "transaction.document_classified",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        after={
            "document_id": str(package.public_id),
            "category": package.category,
            "requirement": package.requirement,
            "title": package.title,
        },
    )
    return package


@transaction.atomic
def retire_document(
    *,
    actor: User,
    public_id: UUID,
    document_public_id: UUID,
    expected_version: str,
) -> TransactionDocument:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    package = (
        TransactionDocument.objects.select_for_update(of=("self",))
        .filter(
            public_id=document_public_id,
            transaction=tx,
            ended_at__isnull=True,
        )
        .select_related("current_version")
        .first()
    )
    if package is None:
        raise ValidationError({"document": ["No document matches that id."]})
    if package.current_version is not None and package.current_version.is_locked:
        raise ValidationError(
            {
                "document": _(
                    "A package whose current version is signed or approved "
                    "cannot be retired."
                )
            }
        )
    locked = TransactionDocumentVersion.objects.filter(
        document=package,
        is_active=True,
    )
    for version in locked:
        if version.is_locked:
            raise ValidationError(
                {
                    "document": _(
                        "Packages with signed or approved versions cannot be retired."
                    )
                }
            )
    package.ended_at = timezone.now()
    package.current_version = None
    package.save(update_fields=["ended_at", "current_version", "updated_at"])
    touch_transaction(tx)
    log_on_commit(
        "transaction.document_retired",
        actor=actor_from_user(actor),
        target=_audit_target(tx),
        after={"document_id": str(package.public_id)},
    )
    return package


@transaction.atomic
def retry_version_processing(
    *,
    actor: User,
    public_id: UUID,
    version_public_id: UUID,
    expected_version: str,
) -> TransactionDocumentVersion:
    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    version = (
        TransactionDocumentVersion.objects.select_for_update(of=("self",))
        .select_related("document")
        .filter(
            public_id=version_public_id,
            document__transaction=tx,
            document__ended_at__isnull=True,
            is_active=True,
        )
        .first()
    )
    if version is None:
        raise ValidationError({"version": ["No version matches that id."]})
    if version.processing_state not in {State.FAILED, State.QUARANTINED}:
        raise ValidationError(
            {"version": ["Only failed or quarantined versions can be retried."]}
        )
    assert_version_mutable(version)
    version.processing_state = State.PENDING
    version.processing_note = ""
    version.save(update_fields=["processing_state", "processing_note", "updated_at"])
    touch_transaction(tx)
    _enqueue_processing(version.pk)
    return version


@transaction.atomic
def lock_version(
    *,
    actor: User,
    public_id: UUID,
    version_public_id: UUID,
    expected_version: str,
    payload: dict[str, Any],
) -> TransactionDocumentVersion:
    """Set signature/compliance lock fields (hook for #106 + AC testing)."""
    from apps.transactions.permissions import (
        MANAGE_TRANSACTIONS,
        TRANSITION_TRANSACTIONS,
    )
    from apps.user.services.role_assignments import has_effective_permission

    tx = require_writable_transaction(
        actor, public_id, expected_version=expected_version
    )
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, MANAGE_TRANSACTIONS)
        or has_effective_permission(actor, TRANSITION_TRANSACTIONS)
    ):
        raise PermissionDenied("You cannot lock document versions.")

    version = (
        TransactionDocumentVersion.objects.select_for_update(of=("self",))
        .select_related("document")
        .filter(
            public_id=version_public_id,
            document__transaction=tx,
            document__ended_at__isnull=True,
            is_active=True,
        )
        .first()
    )
    if version is None:
        raise ValidationError({"version": ["No version matches that id."]})
    if not version.is_readable:
        raise ValidationError({"version": ["Only ready versions can be locked."]})

    signature = str(
        payload.get("signatureStatus") or payload.get("signature_status") or ""
    ).strip()
    compliance = str(
        payload.get("complianceStatus") or payload.get("compliance_status") or ""
    ).strip()
    if signature and signature not in DOCUMENT_SIGNATURE_STATUS_CODES:
        raise ValidationError({"signatureStatus": ["Unknown signature status."]})
    if compliance and compliance not in DOCUMENT_COMPLIANCE_STATUS_CODES:
        raise ValidationError({"complianceStatus": ["Unknown compliance status."]})
    if not signature and not compliance:
        raise ValidationError(
            {"form": ["Provide a signatureStatus and/or complianceStatus."]}
        )

    update_fields = ["updated_at"]
    if signature:
        version.signature_status = signature
        update_fields.append("signature_status")
    if compliance:
        version.compliance_status = compliance
        update_fields.append("compliance_status")

    should_lock = (
        version.signature_status == DocumentSignatureStatus.SIGNED
        or version.compliance_status == DocumentComplianceStatus.APPROVED
    )
    if should_lock and version.locked_at is None:
        version.locked_at = timezone.now()
        version.locked_by = actor
        version.lock_reason = (
            "signed"
            if version.signature_status == DocumentSignatureStatus.SIGNED
            else "approved"
        )
        update_fields.extend(["locked_at", "locked_by", "lock_reason"])

    version.save(update_fields=update_fields)
    touch_transaction(tx)
    log_on_commit(
        "transaction.document_locked",
        actor=actor_from_user(actor),
        target=_version_target(version),
        after={
            "signature_status": version.signature_status,
            "compliance_status": version.compliance_status,
            "locked_at": version.locked_at.isoformat() if version.locked_at else None,
        },
    )
    return version


def load_version_for_reader(
    user: User, version_public_id: UUID
) -> TransactionDocumentVersion:
    """Resolve a version inside for_reader scope or raise DoesNotExist."""
    from apps.transactions.services import scoped_transaction_queryset

    qs = scoped_transaction_queryset(user)
    version = (
        TransactionDocumentVersion.objects.select_related(
            "document", "document__transaction", "document__transaction__office"
        )
        .filter(
            public_id=version_public_id,
            document__ended_at__isnull=True,
            document__transaction__in=qs,
        )
        .first()
    )
    if version is None:
        raise TransactionDocumentVersion.DoesNotExist
    return version


__all__ = [
    "assert_version_mutable",
    "classify_document",
    "document_schema_payload",
    "load_version_for_reader",
    "lock_version",
    "refresh_current_version",
    "retire_document",
    "retry_version_processing",
    "serialize_documents_for_reader",
    "serialize_version",
    "upload_document",
    "upload_revision",
    "version_urls",
]
