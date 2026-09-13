"""Permission- and scope-aware operational report registry.

Mirrors the dashboard metric registry: selection is data, selection is not
protection, and effective access (not role names) drives entitlement.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.user.models import User
from apps.user.services.onboarding_state import OverallStatus
from apps.user.services.role_assignments import EffectiveAccess, get_effective_access
from apps.web.metrics import (
    SOURCE_MODULE_AVAILABILITY,
    MetricScope,
    SourceModule,
    resolve_scope,
)
from apps.web.reporting.calculators import (
    compliance_open_items,
    office_headcount,
    onboarding_progress,
    pending_source,
    training_completion,
)

# Calculator aliases kept explicit for registry readability.
from apps.web.reporting.contract import (
    ExportPolicy,
    ReportColumn,
    ReportContext,
    ReportFilterSpec,
    ReportResult,
    TimeGrain,
)
from apps.web.reporting.scopes import scope_label

ReportCalculator = Callable[[ReportContext], ReportResult]

CALCULATION_VERSION = 1


@dataclass(frozen=True)
class ReportDefinition:
    key: str
    title: str
    description: str
    category: str
    order: int
    scopes: tuple[str, ...]
    source_module: str
    calculator: ReportCalculator
    columns: tuple[ReportColumn, ...]
    filters: tuple[ReportFilterSpec, ...]
    time_grain: TimeGrain
    definition: str
    all_permissions: tuple[str, ...] = ()
    #: When True, any listed permission is enough (used for self-or-team grants).
    any_permission: bool = False
    export_policy: ExportPolicy = ExportPolicy()
    calculation_version: int = CALCULATION_VERSION


ONBOARDING_STATUS_OPTIONS = (
    (OverallStatus.NOT_STARTED, "Not started"),
    (OverallStatus.IN_PROGRESS, "In progress"),
    (OverallStatus.BLOCKED, "Blocked"),
    (OverallStatus.READY, "Ready"),
)


REPORT_DEFINITIONS: tuple[ReportDefinition, ...] = (
    ReportDefinition(
        key="agentBookOfBusiness",
        title="Agent book of business",
        description="My open deals, volume, and pipeline stages.",
        category="agent",
        order=10,
        scopes=(MetricScope.SELF,),
        source_module=SourceModule.TRANSACTIONS,
        calculator=pending_source,
        columns=(
            ReportColumn(key="name", label="Deal"),
            ReportColumn(key="stage", label="Stage"),
            ReportColumn(key="volume", label="Volume", numeric=True, currency=True),
        ),
        filters=(),
        time_grain="month",
        definition=(
            "Self-scope transaction pipeline. Status inclusion and close-date "
            "windows will be documented when the transactions module connects."
        ),
        all_permissions=("web.view_own_transactions",),
    ),
    ReportDefinition(
        key="officePerformance",
        title="Office performance",
        description="Office-scoped transaction and commission totals.",
        category="office",
        order=20,
        scopes=(MetricScope.OFFICE, MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.TRANSACTIONS,
        calculator=pending_source,
        columns=(
            ReportColumn(key="office", label="Office"),
            ReportColumn(key="volume", label="Volume", numeric=True, currency=True),
            ReportColumn(key="count", label="Deals", numeric=True),
        ),
        filters=(ReportFilterSpec(key="office", label="Office", kind="office"),),
        time_grain="month",
        definition=(
            "Office aggregates over transactions in scope. Currency USD; "
            "comparison semantics pending the transactions module."
        ),
        all_permissions=("web.view_transactions",),
    ),
    ReportDefinition(
        key="regionalPerformance",
        title="Regional performance",
        description="Region rollups of office transaction volume.",
        category="regional",
        order=30,
        scopes=(MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.TRANSACTIONS,
        calculator=pending_source,
        columns=(
            ReportColumn(key="region", label="Region"),
            ReportColumn(key="volume", label="Volume", numeric=True, currency=True),
        ),
        filters=(),
        time_grain="month",
        definition="Region rollup of the same inclusion rules as office performance.",
        all_permissions=("web.view_transactions",),
    ),
    ReportDefinition(
        key="brokerOverview",
        title="Broker overview",
        description="Brokerage-wide operational snapshot.",
        category="broker",
        order=40,
        scopes=(MetricScope.COMPANY,),
        source_module=SourceModule.TRANSACTIONS,
        calculator=pending_source,
        columns=(
            ReportColumn(key="metric", label="Metric"),
            ReportColumn(key="value", label="Value", numeric=True),
        ),
        filters=(),
        time_grain="month",
        definition="Company-wide broker snapshot once transactions connect.",
        all_permissions=("web.view_transactions",),
    ),
    ReportDefinition(
        key="complianceOpenItems",
        title="Compliance open items",
        description="Open compliance obligations in scope.",
        category="compliance",
        order=50,
        scopes=(MetricScope.OFFICE, MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.COMPLIANCE,
        calculator=compliance_open_items,
        columns=(
            ReportColumn(key="title", label="Item"),
            ReportColumn(key="dueDate", label="Due"),
            ReportColumn(key="status", label="Status"),
        ),
        filters=(
            ReportFilterSpec(key="office", label="Office", kind="office"),
            ReportFilterSpec(
                key="status",
                label="Status",
                kind="select",
                options=(("pending", "Pending"), ("overdue", "Overdue")),
            ),
        ),
        time_grain="week",
        definition=(
            "Open mandatory acknowledgements for audience members in effective "
            "office scope. Timezone: project TIME_ZONE; no comparison in v1."
        ),
        all_permissions=(
            "web.view_compliance",
            "web.view_policy_acknowledgements",
            "web.manage_policies",
        ),
        any_permission=True,
    ),
    ReportDefinition(
        key="onboardingProgress",
        title="Onboarding progress",
        description="New-agent onboarding status inside your office scope.",
        category="onboarding",
        order=60,
        scopes=(MetricScope.OFFICE, MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.USER_DIRECTORY,
        calculator=onboarding_progress,
        columns=(
            ReportColumn(key="name", label="Agent"),
            ReportColumn(key="email", label="Email"),
            ReportColumn(key="office", label="Office"),
            ReportColumn(key="statusLabel", label="Status"),
            ReportColumn(key="openTasks", label="Open tasks", numeric=True),
            ReportColumn(key="startDate", label="Start date"),
        ),
        filters=(
            ReportFilterSpec(key="office", label="Office", kind="office"),
            ReportFilterSpec(
                key="status",
                label="Status",
                kind="select",
                options=ONBOARDING_STATUS_OPTIONS,
            ),
        ),
        time_grain="none",
        definition=(
            "Population is the new-agent queryset (90-day join window, incomplete "
            "profile, or open operational work), scoped before filters. Aggregate "
            "status counts are Counter totals over the same filtered rows. "
            f"Timezone: {settings.TIME_ZONE}. Currency: n/a. No prior-period "
            "comparison in calculation version 1."
        ),
        all_permissions=("web.view_new_agents",),
    ),
    ReportDefinition(
        key="officeHeadcount",
        title="Office headcount",
        description="Active and disabled people by office in your scope.",
        category="office",
        order=70,
        scopes=(MetricScope.OFFICE, MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.USER_DIRECTORY,
        calculator=office_headcount,
        columns=(
            ReportColumn(key="name", label="Person"),
            ReportColumn(key="email", label="Email"),
            ReportColumn(key="office", label="Office"),
            ReportColumn(key="accountState", label="Account"),
        ),
        filters=(
            ReportFilterSpec(key="office", label="Office", kind="office"),
            ReportFilterSpec(
                key="active",
                label="Active",
                kind="select",
                options=(("yes", "Active"), ("no", "Disabled")),
            ),
        ),
        time_grain="none",
        definition=(
            "Every user in the actor's effective office tree. Active/disabled "
            "filters and per-office aggregates are computed from the same row "
            f"set. Timezone: {settings.TIME_ZONE}. Currency: n/a."
        ),
        all_permissions=("web.view_users",),
    ),
    ReportDefinition(
        key="inventoryStatus",
        title="Inventory status",
        description="Office inventory levels and exceptions.",
        category="inventory",
        order=80,
        scopes=(MetricScope.OFFICE, MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.INVENTORY,
        calculator=pending_source,
        columns=(
            ReportColumn(key="item", label="Item"),
            ReportColumn(key="quantity", label="Qty", numeric=True),
        ),
        filters=(),
        time_grain="none",
        definition="Inventory counts in office scope; pending source.",
        all_permissions=("web.view_inventory",),
    ),
    ReportDefinition(
        key="roomUtilization",
        title="Room utilization",
        description="Booked versus bookable room minutes.",
        category="room",
        order=90,
        scopes=(MetricScope.OFFICE, MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.RESERVATIONS,
        calculator=pending_source,
        columns=(
            ReportColumn(key="room", label="Room"),
            ReportColumn(key="utilization", label="Utilization", numeric=True),
        ),
        filters=(),
        time_grain="week",
        definition=(
            "Booked / bookable room-minutes; closed days excluded from the "
            "denominator. Pending reservations module."
        ),
        all_permissions=("web.view_reservations",),
    ),
    ReportDefinition(
        key="trainingCompletion",
        title="Training completion",
        description="Required training progress in scope.",
        category="training",
        order=100,
        scopes=(MetricScope.OFFICE, MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.TRAINING,
        calculator=training_completion,
        columns=(
            ReportColumn(key="name", label="Person"),
            ReportColumn(key="course", label="Course"),
            ReportColumn(key="status", label="Status"),
        ),
        filters=(),
        time_grain="month",
        definition=(
            "Required training completion by person in the actor's office "
            "tree. Out-of-scope learners are never included."
        ),
        all_permissions=("web.manage_training",),
    ),
    ReportDefinition(
        key="contractStanding",
        title="Contract standing",
        description="Agent contract status in scope.",
        category="contract",
        order=110,
        scopes=(MetricScope.OFFICE, MetricScope.REGION, MetricScope.COMPANY),
        source_module=SourceModule.CONTRACTS,
        calculator=pending_source,
        columns=(
            ReportColumn(key="name", label="Agent"),
            ReportColumn(key="status", label="Standing"),
        ),
        filters=(),
        time_grain="none",
        definition="Agent contract standing; pending contracts module.",
        all_permissions=("web.view_agent_contracts",),
    ),
    ReportDefinition(
        key="transactionVolume",
        title="Transaction volume",
        description="Closed and pending transaction volume by period.",
        category="transaction",
        order=120,
        scopes=(
            MetricScope.SELF,
            MetricScope.OFFICE,
            MetricScope.REGION,
            MetricScope.COMPANY,
        ),
        source_module=SourceModule.TRANSACTIONS,
        calculator=pending_source,
        columns=(
            ReportColumn(key="period", label="Period"),
            ReportColumn(key="volume", label="Volume", numeric=True, currency=True),
            ReportColumn(key="count", label="Count", numeric=True),
        ),
        filters=(),
        time_grain="month",
        definition=(
            "Volume by time grain in USD. Close-date inclusion pending the "
            "transactions module."
        ),
        all_permissions=("web.view_transactions", "web.view_own_transactions"),
        any_permission=True,
    ),
)

REPORT_BY_KEY = {definition.key: definition for definition in REPORT_DEFINITIONS}


def _validate_registry() -> None:
    keys: set[str] = set()
    for definition in REPORT_DEFINITIONS:
        if definition.key in keys:
            raise ValueError(f"Duplicate report key: {definition.key}")
        keys.add(definition.key)
        if definition.source_module not in SOURCE_MODULE_AVAILABILITY:
            raise ValueError(
                f"{definition.key}: unknown source module {definition.source_module}"
            )
        if not definition.definition.strip():
            raise ValueError(f"{definition.key}: missing calculation definition")
        for scope in definition.scopes:
            if scope not in {
                MetricScope.SELF,
                MetricScope.OFFICE,
                MetricScope.REGION,
                MetricScope.COMPANY,
            }:
                raise ValueError(f"{definition.key}: unknown scope {scope}")
        column_keys = [column.key for column in definition.columns]
        if len(column_keys) != len(set(column_keys)):
            raise ValueError(f"{definition.key}: duplicate column keys")


_validate_registry()


def has_report_permissions(
    user: User, definition: ReportDefinition, access: EffectiveAccess
) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if not definition.all_permissions:
        return False
    if definition.any_permission:
        return any(
            permission in access.permissions
            for permission in definition.all_permissions
        )
    return all(
        permission in access.permissions for permission in definition.all_permissions
    )


def scope_permits(definition: ReportDefinition, scope: str) -> bool:
    if definition.scopes == (MetricScope.SELF,):
        return True
    return scope in definition.scopes


def select_reports(
    user: User, *, access: EffectiveAccess | None = None
) -> tuple[ReportDefinition, ...]:
    if not getattr(user, "is_authenticated", False):
        return ()
    effective = get_effective_access(user) if access is None else access
    scope = resolve_scope(user, effective)
    return tuple(
        definition
        for definition in REPORT_DEFINITIONS
        if scope_permits(definition, scope)
        and has_report_permissions(user, definition, effective)
    )


def project_columns(
    definition: ReportDefinition, access: EffectiveAccess, *, user: User
) -> tuple[ReportColumn, ...]:
    if getattr(user, "is_superuser", False):
        return definition.columns
    visible: list[ReportColumn] = []
    for column in definition.columns:
        if column.all_permissions and not all(
            permission in access.permissions for permission in column.all_permissions
        ):
            continue
        visible.append(column)
    return tuple(visible)


def project_rows(
    rows: tuple[dict[str, Any], ...], columns: tuple[ReportColumn, ...]
) -> tuple[dict[str, Any], ...]:
    keys = [column.key for column in columns]
    return tuple({key: row.get(key) for key in keys} for row in rows)


def run_report(
    user: User,
    definition: ReportDefinition,
    *,
    filters: dict[str, str] | None = None,
    at: datetime | None = None,
    access: EffectiveAccess | None = None,
    row_limit: int | None = None,
    unbounded: bool = False,
) -> tuple[ReportContext, ReportResult, tuple[ReportColumn, ...]]:
    """Enforce permission and scope, then calculate and project fields.

    Interactive pages use ``export_policy.sync_row_limit`` (or an explicit
    ``row_limit``). Async exports pass ``unbounded=True`` so the full scoped
    result set is rendered into the protected file.
    """
    effective = get_effective_access(user) if access is None else access
    scope = resolve_scope(user, effective)
    if not has_report_permissions(user, definition, effective):
        raise PermissionError("report_permission_denied")
    if not scope_permits(definition, scope):
        raise PermissionError("report_scope_denied")

    limit: int | None
    if unbounded:
        limit = None
    elif row_limit is not None:
        limit = row_limit
    else:
        limit = definition.export_policy.sync_row_limit

    context = ReportContext(
        user=user,
        access=effective,
        scope=scope,
        now=at or timezone.now(),
        filters=filters or {},
        timezone_name=settings.TIME_ZONE,
        row_limit=limit,
    )
    columns = project_columns(definition, effective, user=user)

    if not SOURCE_MODULE_AVAILABILITY.get(definition.source_module, False):
        result = pending_source(context)
        return context, result, columns

    calculated = definition.calculator(context)
    projected = ReportResult(
        aggregates=calculated.aggregates,
        rows=project_rows(calculated.rows, columns),
        series=calculated.series,
        chart_kind=calculated.chart_kind,
        empty_reason=calculated.empty_reason,
        data_as_of=calculated.data_as_of,
        comparison_note=calculated.comparison_note,
        rejected_filters=calculated.rejected_filters,
    )
    return context, projected, columns


def report_meta_payload(
    definition: ReportDefinition,
    *,
    scope: str,
    access: EffectiveAccess,
    available: bool,
) -> dict[str, Any]:
    return {
        "key": definition.key,
        "title": definition.title,
        "description": definition.description,
        "category": definition.category,
        "order": definition.order,
        "scopes": list(definition.scopes),
        "timeGrain": definition.time_grain,
        "calculationVersion": definition.calculation_version,
        "definition": definition.definition,
        "available": available,
        "scope": {"level": scope, "label": scope_label(access, scope)},
        "export": {
            "formats": list(definition.export_policy.formats),
            "syncRowLimit": definition.export_policy.sync_row_limit,
            "ttlHours": definition.export_policy.ttl_hours,
            "requiresPermission": definition.export_policy.export_permission,
        },
    }
