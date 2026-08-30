"""Background tasks for contract templates and agent-contract lifecycle."""

from __future__ import annotations

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Bound the LibreOffice / pypdf work so a stuck conversion cannot hold a worker.
_PDF_SOFT_TIME_LIMIT = 120
_PDF_HARD_TIME_LIMIT = 150


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_contract_template_preview(self, version_id: int) -> str:
    from apps.contract.models import ContractTemplateVersion
    from apps.contract.services.template_service import generate_preview

    version = (
        ContractTemplateVersion.objects.select_related("template")
        .filter(pk=version_id)
        .first()
    )
    if version is None:
        return "missing"

    try:
        generate_preview(version)
    except ValidationError as exc:
        version.validation_errors = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else [{"form": [str(message) for message in exc.messages]}]
        )
        version.save(update_fields=["validation_errors", "updated_at"])
        return "invalid"
    return "ready"


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=_PDF_SOFT_TIME_LIMIT,
    time_limit=_PDF_HARD_TIME_LIMIT,
    acks_late=True,
)
def generate_contract_pdf(self, contract_id: int) -> str:
    """Render, validate, and attach the authoritative review PDF.

    Idempotent: identical frozen inputs reuse the current artifact and do not
    emit a second readiness event. Logs only ids and outcome codes — never
    party or commercial content.
    """
    from apps.contract.pdf_generation import (
        PdfGenerationError,
        generate_and_store,
        mark_generation_failed,
    )

    try:
        return generate_and_store(contract_id)
    except SoftTimeLimitExceeded as exc:
        logger.warning(
            "generate_contract_pdf timeout contract_id=%s",
            contract_id,
        )
        if self.request.retries >= self.max_retries:
            mark_generation_failed(contract_id, code="timeout")
            return "failed:timeout"
        raise self.retry(exc=exc) from exc
    except PdfGenerationError as exc:
        # Non-retryable failures are finalized inside generate_and_store.
        if not exc.retryable:
            return f"failed:{exc.code}"
        logger.warning(
            "generate_contract_pdf retryable contract_id=%s code=%s attempt=%s",
            contract_id,
            exc.code,
            self.request.retries,
        )
        if self.request.retries >= self.max_retries:
            mark_generation_failed(contract_id, code=exc.code)
            return f"failed:{exc.code}"
        raise self.retry(exc=exc) from exc
    except Exception as exc:  # noqa: BLE001 - unknown failures retry then terminal
        logger.exception(
            "generate_contract_pdf unexpected contract_id=%s",
            contract_id,
        )
        if self.request.retries >= self.max_retries:
            mark_generation_failed(contract_id, code="unexpected")
            return "failed:unexpected"
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=_PDF_SOFT_TIME_LIMIT,
    time_limit=_PDF_HARD_TIME_LIMIT,
    acks_late=True,
)
def generate_signed_contract_pdf(self, signature_id: int) -> str:
    """Build the authoritative final signed PDF from a durable signature.

    Idempotent: an already-attached final artifact is reused. Failures retain
    the signature record and set ``finalization_status=failed`` for safe retry.
    Logs only ids and outcome codes — never party or commercial content.
    """
    from apps.contract.signed_pdf_generation import (
        SignedPdfGenerationError,
        generate_and_store_signed_pdf,
        mark_finalization_failed,
    )

    task_id = str(getattr(self.request, "id", "") or "")
    try:
        return generate_and_store_signed_pdf(signature_id, task_id=task_id)
    except SoftTimeLimitExceeded as exc:
        logger.warning(
            "generate_signed_contract_pdf timeout signature_id=%s",
            signature_id,
        )
        if self.request.retries >= self.max_retries:
            mark_finalization_failed(signature_id, code="timeout", task_id=task_id)
            return "failed:timeout"
        raise self.retry(exc=exc) from exc
    except SignedPdfGenerationError as exc:
        if not exc.retryable:
            return f"failed:{exc.code}"
        logger.warning(
            "generate_signed_contract_pdf retryable signature_id=%s code=%s attempt=%s",
            signature_id,
            exc.code,
            self.request.retries,
        )
        if self.request.retries >= self.max_retries:
            mark_finalization_failed(signature_id, code=exc.code, task_id=task_id)
            return f"failed:{exc.code}"
        raise self.retry(exc=exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "generate_signed_contract_pdf unexpected signature_id=%s",
            signature_id,
        )
        if self.request.retries >= self.max_retries:
            mark_finalization_failed(signature_id, code="unexpected", task_id=task_id)
            return "failed:unexpected"
        raise self.retry(exc=exc) from exc


@shared_task
def expire_due_contracts() -> int:
    """Beat-safe expiry: active contracts past ``expires_on`` become expired."""
    from apps.contract.lifecycle import expire_due_contracts as run_expire

    return run_expire()


@shared_task
def send_contract_signature_reminders() -> int:
    """Beat-safe signature reminders while contracts remain signable."""
    from apps.contract.notification_schedule import publish_signature_reminders

    return publish_signature_reminders()


@shared_task
def send_contract_expiration_warnings() -> int:
    """Beat-safe warnings for active contracts approaching ``expires_on``."""
    from apps.contract.notification_schedule import publish_expiration_warnings

    return publish_expiration_warnings()


@shared_task
def cleanup_orphan_contract_artifacts(*, older_than_hours: int = 24) -> int:
    """Remove generated PDFs that were never pointed at by a contract.

    History rows that remain referenced (including superseded current pointers)
    are preserved. Only unreferenced generated_pdf artifacts older than the
    grace window are deleted, including their private storage objects.
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from apps.contract.models import AgentContract, ContractArtifact

    cutoff = timezone.now() - timedelta(hours=max(1, older_than_hours))
    referenced = AgentContract.objects.exclude(generated_pdf_id=None).values_list(
        "generated_pdf_id", flat=True
    )
    signed_refs = AgentContract.objects.exclude(signed_pdf_id=None).values_list(
        "signed_pdf_id", flat=True
    )
    from apps.contract.models import ContractSignature

    signature_artifact_refs = ContractSignature.objects.exclude(
        artifact_id=None
    ).values_list("artifact_id", flat=True)
    coc_refs = ContractSignature.objects.exclude(
        certificate_of_completion_id=None
    ).values_list("certificate_of_completion_id", flat=True)
    orphans = list(
        ContractArtifact.objects.filter(
            kind=ContractArtifact.Kind.GENERATED_PDF,
            created_at__lt=cutoff,
        )
        .exclude(
            Q(pk__in=referenced)
            | Q(pk__in=signed_refs)
            | Q(pk__in=signature_artifact_refs)
            | Q(pk__in=coc_refs)
        )
        .order_by("pk")[:200]
    )
    deleted = 0
    for artifact in orphans:
        storage = artifact.file.storage
        name = artifact.file.name
        artifact.delete()
        if name:
            try:
                if storage.exists(name):
                    storage.delete(name)
            except Exception:  # noqa: BLE001
                logger.warning("orphan storage delete failed artifact=%s", artifact.pk)
        deleted += 1
    if deleted:
        logger.info("cleanup_orphan_contract_artifacts deleted=%s", deleted)
    return deleted
