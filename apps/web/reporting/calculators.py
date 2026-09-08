"""Report calculators — one function per connected source domain."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from django.utils import timezone

from apps.user.services.onboarding_state import (
    OverallStatus,
    build_onboarding_states,
    new_agent_queryset,
)
from apps.web.reporting.contract import ReportContext, ReportResult, ReportSeriesPoint
from apps.web.reporting.scopes import scoped_users


def _apply_row_limit(queryset, row_limit: int | None):
    """Fetch at most ``row_limit`` rows (+1 to detect truncation)."""
    if row_limit is None:
        return list(queryset), False
    users = list(queryset[: row_limit + 1])
    truncated = len(users) > row_limit
    if truncated:
        users = users[:row_limit]
    return users, truncated


def pending_source(_context: ReportContext) -> ReportResult:
    return ReportResult(
        aggregates={},
        rows=(),
        series=(),
        chart_kind="none",
        empty_reason="This report's source domain is not connected to the hub yet.",
        data_as_of=timezone.now(),
    )


def onboarding_progress(context: ReportContext) -> ReportResult:
    """New-agent onboarding status within effective scope.

    Inclusion rules (for reconciliation):
    - Population is ``new_agent_queryset`` (90-day window **or** incomplete
      profile **or** open operational work), already office-scoped.
    - Optional ``office`` intersects; out-of-scope keys empty the set.
    - Optional ``status`` keeps rows whose overall status matches.
    - Aggregates are ``Counter`` over the same filtered rows.
    - Timezone: project ``TIME_ZONE`` for “as of”; currency n/a; no comparison in v1.
    """
    queryset = new_agent_queryset(context.user, at=context.now, access=context.access)
    office_key = context.filters.get("office")
    if office_key:
        in_scope = scoped_users(
            context.user, access=context.access, office_stable_key=office_key
        )
        queryset = queryset.filter(pk__in=in_scope.values("pk"))

    users, truncated = _apply_row_limit(
        queryset.select_related("office", "office__region", "onboarding_case"),
        context.row_limit,
    )

    states = build_onboarding_states(users)
    status_filter = context.filters.get("status")
    rows: list[dict[str, Any]] = []
    for state in states:
        if status_filter and state.overall_status != status_filter:
            continue
        office = state.user.office
        rows.append(
            {
                "userId": state.user.pk,
                "name": state.user.get_full_name() or state.user.email,
                "email": state.user.email,
                "office": office.name if office else "",
                "officeKey": office.stable_key if office else "",
                "status": state.overall_status,
                "statusLabel": _status_label(state.overall_status),
                "openTasks": len(state.open_tasks),
                "startDate": (
                    state.user.start_date.isoformat() if state.user.start_date else None
                ),
            }
        )

    counts = Counter(row["status"] for row in rows)
    status_order = (
        OverallStatus.NOT_STARTED,
        OverallStatus.IN_PROGRESS,
        OverallStatus.BLOCKED,
        OverallStatus.READY,
    )
    series = tuple(
        ReportSeriesPoint(key=key, label=_status_label(key), value=counts.get(key, 0))
        for key in status_order
    )
    empty = None
    if not rows:
        empty = (
            "No new agents match these filters in your scope."
            if context.filters
            else "No new agents are in your scope right now."
        )
    return ReportResult(
        aggregates={
            "total": len(rows),
            "notStarted": counts.get(OverallStatus.NOT_STARTED, 0),
            "inProgress": counts.get(OverallStatus.IN_PROGRESS, 0),
            "blocked": counts.get(OverallStatus.BLOCKED, 0),
            "ready": counts.get(OverallStatus.READY, 0),
            "truncated": truncated,
            "syncRowLimit": context.row_limit,
        },
        rows=tuple(rows),
        series=series,
        chart_kind="bar",
        empty_reason=empty,
        data_as_of=context.now,
        comparison_note=(
            "Counts are a point-in-time snapshot; they are not compared to a "
            "prior period in calculation version 1."
        ),
    )


def office_headcount(context: ReportContext) -> ReportResult:
    """Active vs disabled people by office inside effective scope.

    Inclusion rules:
    - Base set is every user in ``scoped_users`` (office tree).
    - ``active`` filter: ``yes`` / ``no`` for ``is_active``.
    - Optional ``office`` intersects; out-of-scope keys empty the set.
    - Aggregates sum the same rows. Timezone/currency n/a; no comparison in v1.
    """
    office_key = context.filters.get("office")
    queryset = scoped_users(
        context.user, access=context.access, office_stable_key=office_key
    )
    active_filter = context.filters.get("active")
    if active_filter == "yes":
        queryset = queryset.filter(is_active=True)
    elif active_filter == "no":
        queryset = queryset.filter(is_active=False)

    users, truncated = _apply_row_limit(
        queryset.select_related("office", "office__region"),
        context.row_limit,
    )

    by_office: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for person in users:
        office = person.office
        office_name = office.name if office else "Unassigned"
        office_stable = office.stable_key if office else ""
        bucket = by_office.setdefault(
            office_stable or "__none__",
            {
                "officeKey": office_stable,
                "office": office_name,
                "active": 0,
                "disabled": 0,
                "total": 0,
            },
        )
        if person.is_active:
            bucket["active"] += 1
        else:
            bucket["disabled"] += 1
        bucket["total"] += 1
        rows.append(
            {
                "userId": person.pk,
                "name": person.get_full_name() or person.email,
                "email": person.email,
                "office": office_name,
                "officeKey": office_stable,
                "active": person.is_active,
                "accountState": "active" if person.is_active else "disabled",
            }
        )

    office_rows = sorted(by_office.values(), key=lambda item: item["office"].lower())
    series = tuple(
        ReportSeriesPoint(
            key=item["officeKey"] or "unassigned",
            label=item["office"],
            value=item["total"],
        )
        for item in office_rows
    )
    total_active = sum(item["active"] for item in office_rows)
    total_disabled = sum(item["disabled"] for item in office_rows)
    empty = None
    if not rows:
        empty = (
            "No people match these filters in your scope."
            if context.filters
            else "No people are in your scope right now."
        )
    return ReportResult(
        aggregates={
            "total": total_active + total_disabled,
            "active": total_active,
            "disabled": total_disabled,
            "offices": len(office_rows),
            "truncated": truncated,
            "syncRowLimit": context.row_limit,
            "byOffice": office_rows,
        },
        rows=tuple(rows),
        series=series,
        chart_kind="bar",
        empty_reason=empty,
        data_as_of=context.now,
        comparison_note=(
            "Headcount is a live roster snapshot with no prior-period comparison "
            "in calculation version 1."
        ),
    )


def training_completion(context: ReportContext) -> ReportResult:
    """Required training progress for people in effective scope.

    Inclusion rules:
    - Population is ``scoped_users`` (office tree / company).
    - Optional ``office`` intersects; out-of-scope keys empty the set.
    - Rows are one per person with required-count / completed-count / status.
    - Aggregates use the same filtered rows. No prior-period comparison in v1.
    """
    from apps.training.required_status import bulk_required_training_states

    office_key = context.filters.get("office")
    queryset = scoped_users(
        context.user, access=context.access, office_stable_key=office_key or None
    ).filter(is_active=True)
    users, truncated = _apply_row_limit(
        queryset.select_related("office", "office__region").order_by(
            "last_name", "first_name", "pk"
        ),
        context.row_limit,
    )
    states = bulk_required_training_states(users)
    rows: list[dict[str, Any]] = []
    for user in users:
        state = states.get(user.pk)
        if state is None:
            continue
        required = state.required_count or 0
        completed = state.completed_count or 0
        if required == 0:
            status = "not_assigned"
            status_label = "Not assigned"
        elif completed >= required:
            status = "completed"
            status_label = "Completed"
        elif completed > 0:
            status = "in_progress"
            status_label = "In progress"
        else:
            status = "not_started"
            status_label = "Not started"
        office = user.office
        rows.append(
            {
                "userId": user.pk,
                "name": user.get_full_name() or user.email,
                "course": "Required training",
                "status": status,
                "statusLabel": status_label,
                "requiredCount": required,
                "completedCount": completed,
                "office": office.name if office else "",
                "officeKey": office.stable_key if office else "",
            }
        )

    counts = Counter(row["status"] for row in rows)
    series = tuple(
        ReportSeriesPoint(key=key, label=label, value=counts.get(key, 0))
        for key, label in (
            ("completed", "Completed"),
            ("in_progress", "In progress"),
            ("not_started", "Not started"),
            ("not_assigned", "Not assigned"),
        )
    )
    empty = None
    if not rows:
        empty = (
            "No people match these filters in your scope."
            if context.filters
            else "No people are in your scope right now."
        )
    return ReportResult(
        aggregates={
            "total": len(rows),
            "completed": counts.get("completed", 0),
            "inProgress": counts.get("in_progress", 0),
            "notStarted": counts.get("not_started", 0),
            "notAssigned": counts.get("not_assigned", 0),
            "truncated": truncated,
            "syncRowLimit": context.row_limit,
        },
        rows=tuple(rows),
        series=series,
        chart_kind="bar",
        empty_reason=empty,
        data_as_of=context.now,
        comparison_note=(
            "Counts are a point-in-time snapshot of required-training status."
        ),
    )


def _status_label(status: str) -> str:
    return {
        OverallStatus.NOT_STARTED: "Not started",
        OverallStatus.IN_PROGRESS: "In progress",
        OverallStatus.BLOCKED: "Blocked",
        OverallStatus.READY: "Ready",
    }.get(status, status)


def as_of_iso(at: datetime | None) -> str | None:
    if at is None:
        return None
    return timezone.localtime(at).isoformat()
