"""Async export jobs: idempotency, progress, expiry, protected download."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.text import slugify

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import User
from apps.user.services.role_assignments import get_effective_access
from apps.web.capability import has_capability
from apps.web.reporting.filters import filters_query_string
from apps.web.reporting.registry import REPORT_BY_KEY, run_report

EXPORT_TTL = timedelta(hours=24)
IDEMPOTENCY_WINDOW = timedelta(hours=1)


def _idempotency_key(
    user_id: int,
    report_key: str,
    filters: dict[str, str],
    export_format: str,
) -> str:
    material = "|".join(
        [
            str(user_id),
            report_key,
            filters_query_string(filters),
            export_format,
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]
    return f"report-export:{digest}"


def _scope_level(access) -> str:
    if access.company_wide:
        return "company"
    if access.region_keys:
        return "region"
    if access.office_keys:
        return "office"
    return "self"


def create_export_job(
    actor: User,
    report_key: str,
    *,
    filters: dict[str, str] | None = None,
    export_format: str = "csv",
):
    """Create or reuse an in-flight/recent export for the same request shape."""
    from apps.web.models import ReportExportJob

    definition = REPORT_BY_KEY.get(report_key)
    if definition is None:
        raise Http404
    if export_format not in definition.export_policy.formats:
        raise ValidationError({"format": "Unsupported export format."})

    access = get_effective_access(actor)
    if not has_capability(actor, definition.export_policy.export_permission):
        raise PermissionDenied("Export permission required.")

    # Permission / scope check before any job row is written.
    run_report(actor, definition, filters=filters or {}, access=access)

    key = _idempotency_key(actor.pk, report_key, filters or {}, export_format)
    now = timezone.now()
    existing = (
        ReportExportJob.objects.filter(
            idempotency_key=key,
            requested_at__gte=now - IDEMPOTENCY_WINDOW,
        )
        .exclude(status=ReportExportJob.Status.EXPIRED)
        .order_by("-requested_at")
        .first()
    )
    if existing is not None:
        return existing

    job = ReportExportJob(
        report_key=report_key,
        requested_by=actor,
        filters=filters or {},
        export_format=export_format,
        idempotency_key=key,
        calculation_version=definition.calculation_version,
        scope_level=_scope_level(access),
        expires_at=now + EXPORT_TTL,
        status=ReportExportJob.Status.QUEUED,
    )
    try:
        with transaction.atomic():
            job.save()
            log_event(
                "reporting.export.requested",
                actor=actor_from_user(actor),
                target=AuditTarget(
                    target_type=ReportExportJob._meta.label_lower,
                    target_id=str(job.pk),
                    target_label=report_key,
                ),
                metadata={
                    "reportKey": report_key,
                    "format": export_format,
                    "filters": filters or {},
                },
            )
    except IntegrityError:
        return ReportExportJob.objects.filter(idempotency_key=key).latest(
            "requested_at"
        )

    from apps.web.reporting.tasks import run_report_export

    transaction.on_commit(lambda: run_report_export.delay(job.pk))
    return job


def render_export_bytes(
    actor: User,
    report_key: str,
    *,
    filters: dict[str, str],
    export_format: str,
) -> tuple[bytes, str, dict[str, Any]]:
    definition = REPORT_BY_KEY[report_key]
    _context, result, columns = run_report(
        actor, definition, filters=filters, unbounded=True
    )
    meta = {
        "reportKey": report_key,
        "calculationVersion": definition.calculation_version,
        "generatedAt": timezone.now().isoformat(),
        "dataAsOf": result.data_as_of.isoformat() if result.data_as_of else None,
        "filters": filters,
        "requestorId": actor.pk,
        "columnKeys": [column.key for column in columns],
    }
    if export_format == "json":
        payload = {
            "meta": meta,
            "aggregates": result.aggregates,
            "rows": list(result.rows),
        }
        return (
            json.dumps(payload, indent=2, default=str).encode("utf-8"),
            "application/json",
            meta,
        )

    buffer = io.StringIO()
    fieldnames = [column.key for column in columns]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in result.rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    header = (
        f"# report={report_key}; calculationVersion={definition.calculation_version}; "
        f"generatedAt={meta['generatedAt']}; dataAsOf={meta['dataAsOf']}\n"
    )
    return (header + buffer.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", meta


def process_export_job(job_id: int) -> str:
    from apps.web.models import ReportExportJob

    job = (
        ReportExportJob.objects.select_related("requested_by").filter(pk=job_id).first()
    )
    if job is None:
        return "missing"
    if job.status in {ReportExportJob.Status.READY, ReportExportJob.Status.EXPIRED}:
        return job.status
    if job.expires_at <= timezone.now():
        job.status = ReportExportJob.Status.EXPIRED
        job.save(update_fields=["status", "updated_at"])
        return "expired"

    job.status = ReportExportJob.Status.RUNNING
    job.progress = 10
    job.save(update_fields=["status", "progress", "updated_at"])

    try:
        content, content_type, meta = render_export_bytes(
            job.requested_by,
            job.report_key,
            filters=dict(job.filters or {}),
            export_format=job.export_format,
        )
        filename = (
            f"{slugify(job.report_key) or 'report'}-"
            f"{timezone.now().strftime('%Y%m%d-%H%M%S')}.{job.export_format}"
        )
        job.file.save(filename, ContentFile(content), save=False)
        job.content_type = content_type
        job.byte_size = len(content)
        job.progress = 100
        job.status = ReportExportJob.Status.READY
        job.completed_at = timezone.now()
        if meta.get("dataAsOf"):
            job.data_as_of = datetime.fromisoformat(meta["dataAsOf"])
        else:
            job.data_as_of = timezone.now()
        job.error_message = ""
        job.save()
        log_event(
            "reporting.export.ready",
            actor=actor_from_user(job.requested_by),
            target=AuditTarget(
                target_type=ReportExportJob._meta.label_lower,
                target_id=str(job.pk),
                target_label=job.report_key,
            ),
            metadata={"byteSize": job.byte_size, "format": job.export_format},
        )
        return "ready"
    except Exception as exc:  # noqa: BLE001 - surface failure on the job
        job.status = ReportExportJob.Status.FAILED
        job.error_message = str(exc)[:500]
        job.progress = 100
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "error_message",
                "progress",
                "completed_at",
                "updated_at",
            ]
        )
        log_event(
            "reporting.export.failed",
            actor=actor_from_user(job.requested_by),
            target=AuditTarget(
                target_type=ReportExportJob._meta.label_lower,
                target_id=str(job.pk),
                target_label=job.report_key,
            ),
            outcome=AuditEvent.Outcome.FAILURE,
            reason=job.error_message,
        )
        return "failed"


def mark_expired_exports(*, at=None) -> int:
    from apps.web.models import ReportExportJob

    moment = at or timezone.now()
    expired = ReportExportJob.objects.filter(expires_at__lte=moment).exclude(
        status=ReportExportJob.Status.EXPIRED
    )
    count = 0
    for job in expired.iterator():
        if job.file:
            job.file.delete(save=False)
            job.file.name = ""
        job.status = ReportExportJob.Status.EXPIRED
        job.save(update_fields=["status", "file", "updated_at"])
        count += 1
    return count


def export_job_payload(job: Any) -> dict[str, Any]:
    return {
        "id": job.pk,
        "reportKey": job.report_key,
        "status": job.status,
        "progress": job.progress,
        "format": job.export_format,
        "filters": job.filters or {},
        "requestedAt": job.requested_at.isoformat(),
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
        "expiresAt": job.expires_at.isoformat(),
        "dataAsOf": job.data_as_of.isoformat() if job.data_as_of else None,
        "calculationVersion": job.calculation_version,
        "errorMessage": job.error_message or None,
        "downloadReady": job.status == job.Status.READY and bool(job.file),
        "byteSize": job.byte_size,
    }


def download_export(actor: User, job_id: int) -> FileResponse:
    from apps.web.models import ReportExportJob

    job = ReportExportJob.objects.filter(pk=job_id, requested_by=actor).first()
    if job is None:
        raise Http404
    if job.expires_at <= timezone.now() or job.status == ReportExportJob.Status.EXPIRED:
        if job.status != ReportExportJob.Status.EXPIRED:
            mark_expired_exports()
        raise Http404
    if job.status != ReportExportJob.Status.READY or not job.file:
        raise PermissionDenied("Export is not ready.")

    definition = REPORT_BY_KEY.get(job.report_key)
    if definition is None:
        raise Http404
    if not has_capability(actor, definition.export_policy.export_permission):
        raise PermissionDenied("Export permission required.")
    run_report(actor, definition, filters=dict(job.filters or {}))

    log_event(
        "reporting.export.downloaded",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=ReportExportJob._meta.label_lower,
            target_id=str(job.pk),
            target_label=job.report_key,
        ),
    )
    filename = job.file.name.rsplit("/", 1)[-1]
    response = FileResponse(
        job.file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type=job.content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    return response
