"""Cryptographic signing and public verification for training certificates."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from apps.training.models import TrainingCertificate, TrainingProgress

ALGORITHM_V1 = "hmac-sha256-v1"
ProgressStatus = TrainingProgress.Status
Status = TrainingCertificate.Status


def _signing_key() -> bytes:
    configured = (
        getattr(settings, "TRAINING_CERTIFICATE_SIGNING_KEY", "") or ""
    ).strip()
    if configured:
        return configured.encode("utf-8")
    # Purpose-bound derivation so a leaked HMAC is not a raw SECRET_KEY copy.
    material = f"training-certificate-v1:{settings.SECRET_KEY}".encode()
    return hashlib.sha256(material).digest()


def canonical_payload(
    *,
    public_id: UUID | str,
    learner_id: int,
    content_id: int,
    content_title: str,
    completed_at: str,
    approved_at: str,
) -> dict[str, Any]:
    return {
        "v": 1,
        "public_id": str(public_id),
        "learner_id": learner_id,
        "content_id": content_id,
        "content_title": content_title,
        "completed_at": completed_at,
        "approved_at": approved_at,
    }


def sign_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hmac.new(_signing_key(), body, hashlib.sha256).hexdigest()


def verify_signature(payload: dict[str, Any], signature: str) -> bool:
    if not signature:
        return False
    expected = sign_payload(payload)
    return hmac.compare_digest(expected, signature)


def signature_fingerprint(signature: str) -> str:
    """Human-readable truncated fingerprint for the PDF face."""
    if not signature:
        return "—"
    compact = signature.lower()
    return f"{compact[:8]}…{compact[-8:]}".upper()


def verify_url(public_id: UUID | str) -> str:
    base = getattr(settings, "SITE_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/verify/training-certificates/{public_id}"


def seal_certificate(
    certificate: TrainingCertificate,
    *,
    completed_at,
    approved_at,
) -> str:
    """Compute and persist the HMAC signature; return the hex digest."""
    completed_label = (
        completed_at.isoformat()
        if hasattr(completed_at, "isoformat")
        else str(completed_at)
    )
    approved_label = (
        approved_at.isoformat()
        if hasattr(approved_at, "isoformat")
        else str(approved_at)
    )
    payload = canonical_payload(
        public_id=certificate.public_id,
        learner_id=certificate.user.pk,
        content_id=certificate.content.pk,
        content_title=certificate.content.title,
        completed_at=completed_label,
        approved_at=approved_label,
    )
    digest = sign_payload(payload)
    certificate.signature = digest
    certificate.signature_algorithm = ALGORITHM_V1
    return digest


def verification_result(public_id: UUID | str) -> dict[str, Any]:
    """Public verification envelope for QR / external providers."""
    try:
        cert = (
            TrainingCertificate.objects.select_related("user", "content")
            .filter(public_id=public_id)
            .first()
        )
    except (TypeError, ValueError):
        cert = None

    if cert is None:
        return {
            "valid": False,
            "status": "not_found",
            "publicId": str(public_id),
            "message": "No certificate matches this verification id.",
        }

    progress = TrainingProgress.objects.filter(
        user=cert.user, content=cert.content, status=ProgressStatus.COMPLETED
    ).first()
    completed_at = (
        progress.completed_at.date().isoformat()
        if progress and progress.completed_at
        else None
    )
    approved_at = cert.approved_at.isoformat() if cert.approved_at else ""
    payload = canonical_payload(
        public_id=cert.public_id,
        learner_id=cert.user.pk,
        content_id=cert.content.pk,
        content_title=cert.content.title,
        completed_at=completed_at or "",
        approved_at=approved_at,
    )
    signature_ok = verify_signature(payload, cert.signature)
    status = cert.status
    valid = status == Status.APPROVED and signature_ok and bool(cert.file)

    if status == Status.REVOKED:
        message = "This certificate has been revoked."
    elif status != Status.APPROVED:
        message = "This certificate has not been issued."
    elif not signature_ok:
        message = "The cryptographic signature does not match this record."
    elif not cert.file:
        message = "The certificate file is missing."
    else:
        message = "Certificate verified."

    return {
        "valid": valid,
        "status": status,
        "publicId": str(cert.public_id),
        "signatureValid": signature_ok,
        "signatureAlgorithm": cert.signature_algorithm or ALGORITHM_V1,
        "signatureFingerprint": signature_fingerprint(cert.signature),
        "learnerName": cert.user.get_full_name() or cert.user.email,
        "trainingTitle": cert.content.title,
        "completedAt": completed_at,
        "issuedAt": approved_at or None,
        "verifiedAt": timezone.now().isoformat(),
        "message": message,
        "verifyUrl": verify_url(cert.public_id),
    }
