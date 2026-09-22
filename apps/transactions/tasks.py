"""Background processing and orphan cleanup for transaction documents."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.transactions.media import ABANDONED_PENDING_DAYS, ORPHAN_GRACE_HOURS

logger = logging.getLogger("apps.transactions")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_transaction_document_version(self, version_id: int) -> str:
    """Verify stored bytes and mark ready / quarantined / failed."""
    from apps.announcements.media import checksum_of
    from apps.transactions.deal_documents import refresh_current_version
    from apps.transactions.models import TransactionDocumentVersion

    State = TransactionDocumentVersion.ProcessingState

    version = (
        TransactionDocumentVersion.objects.select_related("document")
        .filter(pk=version_id)
        .first()
    )
    if version is None:
        return "missing"

    try:
        with version.file.storage.open(version.file.name, "rb") as handle:
            data = handle.read()
    except (FileNotFoundError, OSError):
        return _fail(version, State.FAILED, "The stored file could not be read.")

    if checksum_of(data) != version.checksum:
        return _fail(
            version,
            State.QUARANTINED,
            "Stored bytes do not match the upload checksum.",
        )

    if version.is_image:
        try:
            sanitized, _size = _sanitize_image(data, version.media_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "transactions: document version %s image pass failed: %s",
                version.pk,
                exc,
            )
            return _fail(
                version,
                State.QUARANTINED,
                "The image could not be processed safely.",
            )
        version.file.storage.delete(version.file.name)
        version.file.storage.save(version.file.name, io.BytesIO(sanitized))
        version.byte_size = len(sanitized)
        version.checksum = checksum_of(sanitized)
        version.processing_state = State.READY
        version.processing_note = ""
        version.save(
            update_fields=[
                "byte_size",
                "checksum",
                "processing_state",
                "processing_note",
                "updated_at",
            ]
        )
    else:
        version.processing_state = State.READY
        version.processing_note = ""
        version.save(
            update_fields=["processing_state", "processing_note", "updated_at"]
        )

    with transaction.atomic():
        refresh_current_version(version.document)
    return State.READY


def _pil_format(media_type: str) -> str:
    return {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(media_type, "PNG")


def _sanitize_image(data: bytes, media_type: str) -> tuple[bytes, tuple[int, int]]:
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image) or image
        if media_type == "image/jpeg" and image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        clean = Image.frombytes(image.mode, image.size, image.tobytes())
        buffer = io.BytesIO()
        clean.save(buffer, format=_pil_format(media_type))
        return buffer.getvalue(), clean.size


def _fail(version, state: str, note: str) -> str:
    version.processing_state = state
    version.processing_note = note[:255]
    version.save(update_fields=["processing_state", "processing_note", "updated_at"])
    return state


@dataclass
class SweepReport:
    deleted_objects: list[str] = field(default_factory=list)
    deleted_rows: list[int] = field(default_factory=list)


@shared_task
def sweep_transaction_document_orphans() -> dict[str, int]:
    report = sweep_orphan_documents()
    return {
        "deleted_objects": len(report.deleted_objects),
        "deleted_rows": len(report.deleted_rows),
    }


def sweep_orphan_documents(*, now=None) -> SweepReport:
    """Remove abandoned pending rows and unreferenced storage keys."""
    from apps.transactions.models import TransactionDocumentVersion
    from apps.user.storage import private_storage

    moment = now or timezone.now()
    report = SweepReport()
    State = TransactionDocumentVersion.ProcessingState

    stale_cutoff = moment - timedelta(days=ABANDONED_PENDING_DAYS)
    abandoned = TransactionDocumentVersion.objects.filter(
        processing_state__in={State.PENDING, State.FAILED},
        created_at__lt=stale_cutoff,
        is_active=True,
    ).select_related("document")
    for version in abandoned:
        key = version.file.name
        if key:
            try:
                version.file.storage.delete(key)
                report.deleted_objects.append(key)
            except (FileNotFoundError, OSError):
                pass
        report.deleted_rows.append(version.pk)
        version.delete()

    known = {
        name
        for name in TransactionDocumentVersion.objects.exclude(file="").values_list(
            "file", flat=True
        )
        if name
    }
    storage = private_storage()
    grace = moment - timedelta(hours=ORPHAN_GRACE_HOURS)
    try:
        _, files = storage.listdir("transactions")
    except (FileNotFoundError, NotImplementedError):
        return report
    for name in files:
        key = f"transactions/{name}"
        if key in known:
            continue
        try:
            if storage.get_modified_time(key) > grace:
                continue
        except (NotImplementedError, OSError):
            continue
        storage.delete(key)
        report.deleted_objects.append(key)
    return report


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(OSError,),
    retry_backoff=True,
)
def finalize_signature_package(self, package_id: int) -> str:
    """Seal signed PDFs and the certificate once every party has signed.

    Idempotent by design: a retry reuses artifacts that already landed. A
    terminal failure (checksum drift, missing appearance) is logged with its
    code and not retried, because replaying it cannot succeed.
    """
    from apps.transactions.signing.finalize import (
        FinalizationError,
        finalize_package,
    )

    try:
        return finalize_package(package_id)
    except FinalizationError as exc:
        if exc.retryable:
            raise
        logger.warning(
            "transactions: finalize terminal package_id=%s code=%s",
            package_id,
            exc.code,
        )
        return f"failed:{exc.code}"


@shared_task
def send_signature_package_reminders() -> int:
    """Beat-safe reminders for signers still holding up an open package."""
    from apps.transactions.signing.notification_schedule import (
        publish_signature_reminders,
    )

    return publish_signature_reminders()


@shared_task
def expire_signature_packages() -> int:
    """Beat-safe expiry for open packages past their ``expires_at``."""
    from apps.transactions.signing.lifecycle import expire_due_packages

    return expire_due_packages()


__all__ = [
    "expire_signature_packages",
    "finalize_signature_package",
    "process_transaction_document_version",
    "send_signature_package_reminders",
    "sweep_orphan_documents",
    "sweep_transaction_document_orphans",
]
