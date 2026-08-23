"""Celery tasks for report export generation and expiry."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("apps.web.reporting")


@shared_task(bind=True, max_retries=2, default_retry_delay=20)
def run_report_export(self, job_id: int) -> str:
    from apps.web.reporting.exports import process_export_job

    try:
        return process_export_job(job_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("report export job %s failed", job_id)
        raise self.retry(exc=exc) from exc


@shared_task
def expire_report_exports() -> int:
    from apps.web.reporting.exports import mark_expired_exports

    return mark_expired_exports()
