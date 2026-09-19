"""Approval-gated training completion certificates."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone

from apps.audit.service import (
    AuditTarget,
    actor_from_user,
    log_on_commit,
)
from apps.training.administration import assert_can_author
from apps.training.audience import assert_visible, targetable_user_queryset
from apps.training.certificate_pdf import build_training_certificate_pdf
from apps.training.models import TrainingCertificate, TrainingContent, TrainingProgress
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

MANAGE_PERMISSION = "web.manage_training"
CERTIFICATE_LEARNER_CAP = 50
Status = TrainingCertificate.Status
ProgressStatus = TrainingProgress.Status


class CertificateError(ValidationError):
    """Domain validation for certificate mutations."""


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


def _admin_certificate_summary(
    cert: TrainingCertificate | None,
) -> dict[str, Any] | None:
    if cert is None:
        return None
    return {
        "status": cert.status,
        "available": cert.status == Status.APPROVED and bool(cert.file),
    }


def certificates_workspace_payload(
    actor: User, content: TrainingContent
) -> dict[str, Any]:
    """Completed learners in scope for the training workspace Issue panel."""
    targetable = targetable_user_queryset(actor)
    completed_qs = (
        TrainingProgress.objects.filter(
            content=content,
            status=ProgressStatus.COMPLETED,
            user__in=targetable,
        )
        .select_related("user", "user__office")
        .order_by("-completed_at", "user_id")
    )
    eligible_count = completed_qs.count()
    rows = list(completed_qs[:CERTIFICATE_LEARNER_CAP])
    user_ids = [row.user.pk for row in rows]
    certs = {
        cert.user.pk: cert
        for cert in TrainingCertificate.objects.filter(
            content=content, user_id__in=user_ids
        ).select_related("user")
    }
    issued_count = TrainingCertificate.objects.filter(
        content=content,
        status=Status.APPROVED,
        user__in=targetable,
        user_id__in=TrainingProgress.objects.filter(
            content=content, status=ProgressStatus.COMPLETED
        ).values("user_id"),
    ).count()
    learners = [
        {
            "id": row.user.pk,
            "name": row.user.get_full_name() or row.user.email,
            "email": row.user.email,
            "officeName": row.user.office.name if row.user.office else "",
            "completedAt": (row.completed_at.isoformat() if row.completed_at else None),
            "certificate": _admin_certificate_summary(certs.get(row.user.pk)),
        }
        for row in rows
    ]
    return {
        "learners": learners,
        "eligibleCount": eligible_count,
        "issuedCount": issued_count,
        "capped": eligible_count > CERTIFICATE_LEARNER_CAP,
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


def _assert_can_manage_certificate(
    *, actor: User, content: TrainingContent, learner: User
) -> None:
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        raise PermissionDenied("You cannot issue training certificates.")
    assert_can_author(actor, content.owner_office)
    if not targetable_user_queryset(actor).filter(pk=learner.pk).exists():
        raise PermissionDenied("That learner is outside your training scope.")


def _finalize_approval(
    *, actor: User, locked: TrainingCertificate, force: bool = False
) -> TrainingCertificate:
    """Generate signed PDF and mark approved. Caller must hold the row lock."""
    from apps.training.certificate_crypto import (
        seal_certificate,
        verify_url,
    )

    if (
        not force
        and locked.status == Status.APPROVED
        and locked.file
        and locked.signature
    ):
        return locked

    learner_name = locked.user.get_full_name() or locked.user.email
    completed = TrainingProgress.objects.filter(
        user=locked.user, content=locked.content, status=ProgressStatus.COMPLETED
    ).first()
    completed_at = (
        completed.completed_at.date()
        if completed and completed.completed_at
        else timezone.localdate()
    )
    approved_at = timezone.now()
    was_new = locked.status != Status.APPROVED or not locked.signature

    digest = seal_certificate(
        locked, completed_at=completed_at, approved_at=approved_at
    )
    pdf = build_training_certificate_pdf(
        title=locked.content.title,
        learner_name=learner_name,
        completed_at=completed_at,
        public_id=str(locked.public_id),
        verify_url=verify_url(locked.public_id),
        signature=digest,
        signature_algorithm=locked.signature_algorithm,
    )
    filename = f"training-{locked.content.pk}-certificate.pdf"
    locked.file.save(filename, ContentFile(pdf), save=False)
    locked.status = Status.APPROVED
    locked.approved_by = actor
    locked.approved_at = approved_at
    locked.save()

    if was_new:
        log_on_commit(
            "training.certificate_approved",
            actor=actor_from_user(actor),
            target=AuditTarget(
                target_type=TrainingCertificate._meta.label_lower,
                target_id=str(locked.pk),
                target_label=locked.content.title,
                target_snapshot={
                    "status": locked.status,
                    "learner_id": locked.user.pk,
                    "content_id": locked.content.pk,
                    "public_id": str(locked.public_id),
                    "has_file": bool(locked.file),
                },
            ),
            metadata={
                "learner_id": locked.user.pk,
                "content_id": locked.content.pk,
                "certificate_id": locked.pk,
                "public_id": str(locked.public_id),
            },
        )
    return locked


@transaction.atomic
def approve_certificate(
    *,
    actor: User,
    certificate: TrainingCertificate,
    force: bool = False,
) -> TrainingCertificate:
    _assert_can_manage_certificate(
        actor=actor, content=certificate.content, learner=certificate.user
    )

    locked = (
        TrainingCertificate.objects.select_for_update(of=("self",))
        .select_related("user", "content")
        .filter(pk=certificate.pk)
        .first()
    )
    if locked is None:
        raise CertificateError({"certificate": ["Certificate no longer exists."]})
    return _finalize_approval(actor=actor, locked=locked, force=force)


@transaction.atomic
def issue_certificate(
    *,
    actor: User,
    content: TrainingContent,
    learner: User,
    force: bool = False,
) -> TrainingCertificate:
    """One-click issue: create (if needed) and approve a signed certificate PDF."""
    _assert_can_manage_certificate(actor=actor, content=content, learner=learner)

    progress = TrainingProgress.objects.filter(
        user=learner, content=content, status=ProgressStatus.COMPLETED
    ).first()
    if progress is None:
        raise CertificateError(
            {
                "learnerId": [
                    "Issue a certificate only after the learner has completed "
                    "this training."
                ]
            }
        )

    cert, _ = TrainingCertificate.objects.get_or_create(
        user=learner,
        content=content,
        defaults={"status": Status.PENDING},
    )
    locked = (
        TrainingCertificate.objects.select_for_update(of=("self",))
        .select_related("user", "content")
        .filter(pk=cert.pk)
        .first()
    )
    if locked is None:
        raise CertificateError({"certificate": ["Certificate no longer exists."]})
    return _finalize_approval(actor=actor, locked=locked, force=force)


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
