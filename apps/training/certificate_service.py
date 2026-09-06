"""Approval-gated training completion certificates."""

from __future__ import annotations

import io
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone

from apps.audit.service import actor_from_user, log_on_commit, target_from_instance
from apps.training.administration import assert_can_author
from apps.training.audience import assert_visible, targetable_user_queryset
from apps.training.models import TrainingCertificate, TrainingContent, TrainingProgress
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

MANAGE_PERMISSION = "web.manage_training"
Status = TrainingCertificate.Status
ProgressStatus = TrainingProgress.Status


class CertificateError(ValidationError):
    """Domain validation for certificate mutations."""


def _build_simple_pdf(*, title: str, learner_name: str, completed_at: str) -> bytes:
    """Minimal PDF evidence page (not cryptographic)."""
    # Hand-rolled one-page PDF avoids a heavy dependency for a short certificate.
    lines = [
        "Certificate of Completion",
        title,
        f"Awarded to {learner_name}",
        f"Completed {completed_at}",
        "oNEST Hub training evidence",
    ]
    content_lines = []
    y = 720
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"BT /F1 16 Tf 72 {y} Td ({safe}) Tj ET")
        y -= 28
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
    )
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj)
    xref = out.tell()
    out.write(f"xref\n0 {len(offsets)}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.write(f"{offset:010d} 00000 n \n".encode())
    trailer = (
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    )
    out.write(trailer.encode())
    return out.getvalue()


def certificate_payload(content: TrainingContent, user: User) -> dict[str, Any] | None:
    cert = TrainingCertificate.objects.filter(user=user, content=content).first()
    if cert is None:
        return None
    return {
        "status": cert.status,
        "available": cert.status == Status.APPROVED and bool(cert.file),
        "approvedAt": cert.approved_at.isoformat() if cert.approved_at else None,
        "downloadUrl": (
            f"/training-learning/{content.pk}/certificate"
            if cert.status == Status.APPROVED and cert.file
            else None
        ),
    }


@transaction.atomic
def ensure_pending_certificate(
    user: User, content: TrainingContent
) -> TrainingCertificate:
    """Create a pending certificate once progress is completed."""
    progress = TrainingProgress.objects.filter(
        user=user, content=content, status=ProgressStatus.COMPLETED
    ).first()
    if progress is None:
        raise CertificateError(
            {"progress": ["Complete the training before requesting a certificate."]}
        )
    cert, _ = TrainingCertificate.objects.get_or_create(
        user=user,
        content=content,
        defaults={"status": Status.PENDING},
    )
    return cert


@transaction.atomic
def approve_certificate(
    *,
    actor: User,
    certificate: TrainingCertificate,
) -> TrainingCertificate:
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        raise PermissionDenied("You cannot approve training certificates.")
    assert_can_author(actor, certificate.content.owner_office)
    if not targetable_user_queryset(actor).filter(pk=certificate.user.pk).exists():
        raise PermissionDenied("That learner is outside your training scope.")

    locked = (
        TrainingCertificate.objects.select_for_update(of=("self",))
        .filter(pk=certificate.pk)
        .first()
    )
    if locked is None:
        raise CertificateError({"certificate": ["Certificate no longer exists."]})
    if locked.status == Status.APPROVED and locked.file:
        return locked

    learner_name = locked.user.get_full_name() or locked.user.email
    completed = TrainingProgress.objects.filter(
        user=locked.user, content=locked.content, status=ProgressStatus.COMPLETED
    ).first()
    completed_at = (
        completed.completed_at.date().isoformat()
        if completed and completed.completed_at
        else timezone.localdate().isoformat()
    )
    pdf = _build_simple_pdf(
        title=locked.content.title,
        learner_name=learner_name,
        completed_at=completed_at,
    )
    filename = f"training-{locked.content.pk}-certificate.pdf"
    locked.file.save(filename, ContentFile(pdf), save=False)
    locked.status = Status.APPROVED
    locked.approved_by = actor
    locked.approved_at = timezone.now()
    locked.save()

    log_on_commit(
        "training.certificate_approved",
        actor=actor_from_user(actor),
        target=target_from_instance(locked, label=locked.content.title),
        metadata={
            "learner_id": locked.user.pk,
            "content_id": locked.content.pk,
            "certificate_id": locked.pk,
        },
    )
    return locked


def stream_certificate(user: User, content: TrainingContent):
    assert_visible(user, content, reason="certificate_out_of_audience")
    cert = TrainingCertificate.objects.filter(user=user, content=content).first()
    if cert is None or cert.status != Status.APPROVED or not cert.file:
        raise Http404("Certificate is not available.")
    return FileResponse(
        cert.file.open("rb"),
        as_attachment=True,
        filename=f"training-{content.pk}-certificate.pdf",
        content_type="application/pdf",
    )
