"""Filter parsing and URL-safe validation for reports."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from apps.web.reporting.contract import ReportFilterSpec

_SAFE_TEXT = re.compile(r"^[\w\s@.\-+']{0,120}$", re.UNICODE)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_OFFICE_KEY = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,63}$")


def parse_report_filters(
    specs: tuple[ReportFilterSpec, ...],
    params: Any,
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Validate query params against the report's closed filter set.

    Unknown keys and invalid values are dropped and listed in ``rejected``.
    Nothing rejected is echoed into the ORM.
    """
    accepted: dict[str, str] = {}
    rejected: list[str] = []
    known = {spec.key: spec for spec in specs}

    for key in params:
        if key in {"page", "pageSize", "sort", "direction", "export"}:
            continue
        if key not in known:
            rejected.append(key)
            continue
        raw = params.get(key)
        if raw is None or raw == "":
            continue
        value = str(raw).strip()
        if not value:
            continue
        spec = known[key]
        if not _value_allowed(spec, value):
            rejected.append(key)
            continue
        accepted[key] = value
    return accepted, tuple(rejected)


def _value_allowed(spec: ReportFilterSpec, value: str) -> bool:
    if spec.kind == "text":
        return bool(_SAFE_TEXT.match(value))
    if spec.kind == "date":
        return bool(_DATE.match(value))
    if spec.kind == "select":
        return value in {option[0] for option in spec.options}
    if spec.kind == "office":
        return bool(_OFFICE_KEY.fullmatch(value))
    return False


def filters_query_string(filters: dict[str, str]) -> str:
    if not filters:
        return ""
    return urlencode(sorted(filters.items()))
