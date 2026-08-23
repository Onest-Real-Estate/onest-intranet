"""Shared constants and typed shapes for the reporting framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from apps.web.metrics import MetricScope, SourceModule

ReportScope = str
TimeGrain = Literal["day", "week", "month", "quarter", "year", "none"]
ExportFormat = Literal["csv", "json"]
ChartKind = Literal["bar", "none"]


@dataclass(frozen=True)
class ReportColumn:
    """One projected field. Hidden columns never leave the server."""

    key: str
    label: str
    all_permissions: tuple[str, ...] = ()
    numeric: bool = False
    currency: bool = False


@dataclass(frozen=True)
class ReportFilterSpec:
    key: str
    label: str
    kind: Literal["text", "select", "date", "office"]
    options: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ExportPolicy:
    formats: tuple[ExportFormat, ...] = ("csv",)
    sync_row_limit: int = 500
    ttl_hours: int = 24
    export_permission: str = "web.export_reports"


@dataclass(frozen=True)
class ReportSeriesPoint:
    key: str
    label: str
    value: float | int


@dataclass(frozen=True)
class ReportResult:
    aggregates: dict[str, Any]
    rows: tuple[dict[str, Any], ...]
    series: tuple[ReportSeriesPoint, ...] = ()
    chart_kind: ChartKind = "bar"
    empty_reason: str | None = None
    data_as_of: datetime | None = None
    comparison_note: str = ""
    rejected_filters: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportContext:
    user: Any
    access: Any
    scope: str
    now: datetime
    filters: dict[str, str] = field(default_factory=dict)
    timezone_name: str = "UTC"
    currency: str = "USD"
    # Interactive pages bound rows; ``None`` means unbounded (async exports).
    row_limit: int | None = 500


__all__ = [
    "ChartKind",
    "ExportFormat",
    "ExportPolicy",
    "MetricScope",
    "ReportColumn",
    "ReportContext",
    "ReportFilterSpec",
    "ReportResult",
    "ReportScope",
    "ReportSeriesPoint",
    "SourceModule",
    "TimeGrain",
]
