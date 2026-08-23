"""Serialize report catalog and detail payloads for Inertia."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.user.models import User
from apps.user.services.role_assignments import get_effective_access
from apps.web.capability import has_capability
from apps.web.metrics import (
    SOURCE_MODULE_AVAILABILITY,
    metric_scope_payload,
    resolve_scope,
)
from apps.web.reporting.exports import export_job_payload
from apps.web.reporting.filters import parse_report_filters
from apps.web.reporting.registry import (
    REPORT_BY_KEY,
    report_meta_payload,
    run_report,
    select_reports,
)


def report_catalog_payload(user: User) -> dict[str, Any]:
    access = get_effective_access(user)
    scope = resolve_scope(user, access)
    reports = []
    for definition in select_reports(user, access=access):
        available = SOURCE_MODULE_AVAILABILITY.get(definition.source_module, False)
        reports.append(
            {
                **report_meta_payload(
                    definition, scope=scope, access=access, available=available
                ),
                "canExport": has_capability(
                    user, definition.export_policy.export_permission
                )
                and available,
            }
        )
    return {
        "reports": reports,
        "scope": metric_scope_payload(access, scope),
        "timezone": settings.TIME_ZONE,
        "currency": "USD",
        "canExport": has_capability(user, "web.export_reports"),
    }


def report_page_payload(user: User, report_key: str, *, params: Any) -> dict[str, Any]:
    definition = REPORT_BY_KEY.get(report_key)
    if definition is None:
        raise LookupError(report_key)

    access = get_effective_access(user)
    selected = {item.key for item in select_reports(user, access=access)}
    if definition.key not in selected:
        raise PermissionError("report_not_entitled")

    filters, rejected = parse_report_filters(definition.filters, params)
    context, result, columns = run_report(
        user, definition, filters=filters, access=access
    )
    available = SOURCE_MODULE_AVAILABILITY.get(definition.source_module, False)
    can_export = (
        has_capability(user, definition.export_policy.export_permission) and available
    )

    return {
        "report": {
            **report_meta_payload(
                definition,
                scope=context.scope,
                access=access,
                available=available,
            ),
            "filters": [
                {
                    "key": spec.key,
                    "label": spec.label,
                    "kind": spec.kind,
                    "options": [
                        {"value": value, "label": label}
                        for value, label in spec.options
                    ],
                }
                for spec in definition.filters
            ],
            "appliedFilters": filters,
            "rejectedFilters": list(rejected),
            "columns": [
                {
                    "key": column.key,
                    "label": column.label,
                    "numeric": column.numeric,
                    "currency": column.currency,
                }
                for column in columns
            ],
            "aggregates": result.aggregates,
            "rows": list(result.rows),
            "series": [
                {"key": point.key, "label": point.label, "value": point.value}
                for point in result.series
            ],
            "chartKind": result.chart_kind,
            "emptyReason": result.empty_reason,
            "dataAsOf": result.data_as_of.isoformat() if result.data_as_of else None,
            "comparisonNote": result.comparison_note,
            "canExport": can_export,
            "syncRowLimit": definition.export_policy.sync_row_limit,
            "timezone": settings.TIME_ZONE,
            "currency": "USD",
            "generatedAt": timezone.now().isoformat(),
        }
    }


def export_status_payload(user: User, job_id: int) -> dict[str, Any]:
    from apps.web.models import ReportExportJob

    job = ReportExportJob.objects.filter(pk=job_id, requested_by=user).first()
    if job is None:
        raise LookupError(job_id)
    return {"export": export_job_payload(job)}
