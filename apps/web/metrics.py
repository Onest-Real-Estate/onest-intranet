"""Permission- and scope-aware dashboard metric registry.

The dashboard shows a different set of figures to an agent, a branch manager,
a regional leader, and a superadmin. This module owns *which* figures each
signed-in user gets and *what each figure counts* — as reviewed data, not as a
conditional tree inside a view.

Three rules hold the design together:

1. **Selection is data.** ``METRIC_DEFINITIONS`` maps a metric key to its
   required permissions, supported scopes, calculator, display metadata, and
   drill-down destination. Adding a metric means adding a row, never editing a
   branch. ``_validate_registry`` runs at import and fails the process on a
   malformed row.
2. **Selection is not protection.** Every metric with a drill-down points at a
   route whose ``enforce_policy`` entry requires at least the metric's own
   permissions (asserted at import time), and every aggregate is filtered
   through the shared scope helpers in ``web.authorization``. Losing a
   permission removes the card *and* the page behind it.
3. **Effective access, not role names.** Scope and permissions come from
   ``apps.user.services.role_assignments``, so a revoked or expired assignment
   drops its metrics on the next request.

Calculation definitions — windows, denominators, timezone behaviour — are
documented per metric in ``definition`` and in ``docs/dashboard-metrics.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.urls import reverse
from django.utils import timezone

from apps.user.models import Office, User
from apps.user.services.onboarding_state import dashboard_new_agent_queryset
from apps.user.services.role_assignments import EffectiveAccess, get_effective_access
from apps.web.authorization import ROUTE_POLICIES, scope_queryset_for_user_office


class MetricScope:
    """Breadth of the records a metric aggregates over."""

    SELF = "self"
    OFFICE = "office"
    REGION = "region"
    COMPANY = "company"


#: Broadest-first, so a multi-scope user resolves to a single deterministic level.
SCOPE_ORDER: tuple[str, ...] = (
    MetricScope.COMPANY,
    MetricScope.REGION,
    MetricScope.OFFICE,
    MetricScope.SELF,
)

#: Every scope wider than ``SELF`` reads a team aggregate.
MANAGED_SCOPES: tuple[str, ...] = (
    MetricScope.OFFICE,
    MetricScope.REGION,
    MetricScope.COMPANY,
)


class SourceModule:
    """Domain module a metric reads from.

    A metric may be registered before its module exists; the registry then
    reports it as unavailable rather than inventing a number.
    """

    USER_DIRECTORY = "user_directory"
    TRANSACTIONS = "transactions"
    COMMISSIONS = "commissions"
    TASKS = "tasks"
    LEADS = "leads"
    CONTRACTS = "contracts"
    COMPLIANCE = "compliance"
    INVENTORY = "inventory"
    RESERVATIONS = "reservations"
    TRAINING = "training"


#: Flip an entry to ``True`` in the same commit that ships the module's models.
#: A ``False`` entry means the metric is real and reviewed but has no data
#: source yet — the card is marked unavailable, never filled with a placeholder
#: figure that a leader could mistake for a measurement.
SOURCE_MODULE_AVAILABILITY: dict[str, bool] = {
    SourceModule.USER_DIRECTORY: True,
    SourceModule.TRANSACTIONS: False,
    SourceModule.COMMISSIONS: False,
    SourceModule.TASKS: False,
    SourceModule.LEADS: False,
    SourceModule.CONTRACTS: False,
    SourceModule.COMPLIANCE: False,
    SourceModule.INVENTORY: False,
    SourceModule.RESERVATIONS: False,
    SourceModule.TRAINING: False,
}

#: Shown on the card in place of a figure. Written out per module rather than
#: assembled from a label, so each one reads as a sentence.
SOURCE_MODULE_UNAVAILABLE_REASON: dict[str, str] = {
    SourceModule.USER_DIRECTORY: "The user directory is not connected to the hub yet.",
    SourceModule.TRANSACTIONS: "Transactions are not connected to the hub yet.",
    SourceModule.COMMISSIONS: "Commissions are not connected to the hub yet.",
    SourceModule.TASKS: "Tasks are not connected to the hub yet.",
    SourceModule.LEADS: "Leads are not connected to the hub yet.",
    SourceModule.CONTRACTS: "Agent contracts are not connected to the hub yet.",
    SourceModule.COMPLIANCE: "Compliance tracking is not connected to the hub yet.",
    SourceModule.INVENTORY: "Inventory is not connected to the hub yet.",
    SourceModule.RESERVATIONS: "Reservations are not connected to the hub yet.",
    SourceModule.TRAINING: "Training is not connected to the hub yet.",
}


class Availability:
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class UnavailableBehavior:
    """What to do with a metric whose source module is not connected.

    ``MARK`` keeps the card and states plainly that the figure is not wired up,
    so a leader can tell the difference between "zero" and "not measured yet".
    ``OMIT`` drops the metric from the payload entirely; reserve it for figures
    that would mislead by their mere presence.
    """

    MARK = "mark"
    OMIT = "omit"


#: Trailing window for "new" people joining a scope.
NEW_AGENT_WINDOW_DAYS = 30
#: Forward window for closings and other scheduled work.
UPCOMING_WINDOW_DAYS = 30


@dataclass(frozen=True)
class MetricGroupDefinition:
    key: str
    title: str
    order: int
    description: str = ""


METRIC_GROUPS: tuple[MetricGroupDefinition, ...] = (
    MetricGroupDefinition(
        key="myPipeline",
        title="My pipeline",
        order=10,
        description="Deals I own",
    ),
    MetricGroupDefinition(
        key="myWork",
        title="My work",
        order=20,
        description="What is on me this week",
    ),
    MetricGroupDefinition(
        key="teamOperations",
        title="Team operations",
        order=30,
        description="Deals and resources in my scope",
    ),
    MetricGroupDefinition(
        key="teamOversight",
        title="Team oversight",
        order=40,
        description="People and compliance in my scope",
    ),
)

METRIC_GROUP_BY_KEY = {group.key: group for group in METRIC_GROUPS}


@dataclass(frozen=True)
class MetricValue:
    """A calculated figure, already formatted for display."""

    value: str
    hint: str = ""
    tone: str = "neutral"
    trend: str = "flat"
    #: Machine-readable figure for tests and future clients; never the display string.
    raw_value: int | float | str | None = None
    #: What ``raw_value`` counts — e.g. ``count``, ``usd``, ``ratio``.
    unit: str | None = None
    #: Signed change against the comparable prior period, e.g. ``"+15%"``.
    #: ``None`` when no honest comparison exists (no prior data, or a
    #: denominator of zero) — the card then simply has no pill.
    delta: str | None = None
    #: The figure being compared against, already formatted, e.g. ``"12"``.
    #: The card renders it as "vs. 12 last period".
    compared_to: str | None = None


@dataclass(frozen=True)
class MetricContext:
    """Everything a calculator may read. Never a client-supplied identifier."""

    user: User
    access: EffectiveAccess
    scope: str
    now: datetime


MetricCalculator = Callable[[MetricContext], MetricValue]


# --------------------------------------------------------------------------- #
# Presentation — one adapter for every format the registry allows
# --------------------------------------------------------------------------- #


def format_count(value: int) -> str:
    """Whole counts only. Never invent fractional people or deals."""
    return f"{int(value):,}"


def format_currency(amount: Decimal | int | float) -> str:
    """USD to the cent. Whole-dollar inputs still show ``.00`` so scale is honest."""
    quantized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if quantized < 0 else ""
    absolute = abs(quantized)
    dollars, cents = divmod(int(absolute * 100), 100)
    return f"{sign}${dollars:,}.{cents:02d}"


def format_percent(ratio: float, *, places: int = 0) -> str:
    """Ratio as a percentage. Default: whole percent, no fake precision."""
    pct = float(ratio) * 100
    if places <= 0:
        return f"{round(pct)}%"
    return f"{pct:.{places}f}%"


@dataclass(frozen=True)
class MetricDrillDown:
    """Where the card links, and the guard that already protects it."""

    route_name: str
    label: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    group: str
    order: int
    scopes: tuple[str, ...]
    source_module: str
    calculator: MetricCalculator
    #: Human-readable calculation definition; mirrored in docs/dashboard-metrics.md.
    definition: str
    format: str = "count"
    all_permissions: tuple[str, ...] = ()
    drill_down: MetricDrillDown | None = None
    unavailable_behavior: str = UnavailableBehavior.MARK
    #: Stable icon key from the frontend's approved metric-icon set. The card
    #: renders it top-right; an unknown key falls back to a neutral glyph there.
    icon: str = ""


# --------------------------------------------------------------------------- #
# Window helpers — every boundary is timezone-aware and derived from the
# project timezone, so "year to date" means the local calendar year rather than
# a UTC one.
# --------------------------------------------------------------------------- #


def now() -> datetime:
    return timezone.now()


def trailing_window_start(at: datetime, *, days: int) -> datetime:
    """Start of a trailing window. Duration arithmetic, so DST-safe."""
    return at - timedelta(days=days)


def upcoming_window_end(at: datetime, *, days: int) -> datetime:
    return at + timedelta(days=days)


def year_to_date_start(at: datetime) -> datetime:
    """Midnight on 1 January of the *local* year containing ``at``."""
    local = timezone.localtime(at)
    naive_start = datetime.combine(local.date().replace(month=1, day=1), time.min)
    return timezone.make_aware(naive_start, timezone.get_current_timezone())


def end_of_local_day(at: datetime) -> datetime:
    """Exclusive upper bound for "due today" in the local calendar day."""
    local = timezone.localtime(at)
    naive_next_day = datetime.combine(local.date() + timedelta(days=1), time.min)
    return timezone.make_aware(naive_next_day, timezone.get_current_timezone())


def utilization_ratio(booked_minutes: float, bookable_minutes: float) -> float | None:
    """Booked over bookable time.

    Returns ``None`` when the denominator is not positive. A window with no
    bookable minutes — every room closed, or no rooms recorded — is
    *unmeasured*, and reporting it as 0% would read as "nobody used the rooms".
    The ratio is deliberately not clamped: a value above 1.0 means rooms were
    double-booked, which is a real finding rather than a rounding artefact.
    """
    if bookable_minutes <= 0:
        return None
    return booked_minutes / bookable_minutes


# --------------------------------------------------------------------------- #
# Scope resolution
# --------------------------------------------------------------------------- #


def resolve_scope(user: User, access: EffectiveAccess) -> str:
    """The single broadest scope a user reads team aggregates at.

    Broadest wins so a user holding both a region and an office assignment is
    resolved deterministically to one level; the queryset filter still unions
    *both* key sets (see ``scope_queryset_for_user_office``), so widening the
    reported level never narrows the data and never counts a record twice.
    """
    if getattr(user, "is_superuser", False) or access.company_wide:
        return MetricScope.COMPANY
    if access.region_keys:
        return MetricScope.REGION
    if access.office_keys:
        return MetricScope.OFFICE
    return MetricScope.SELF


def _office_names(stable_keys) -> list[str]:
    return list(
        Office.objects.filter(stable_key__in=sorted(stable_keys))
        .order_by("sort_order", "name")
        .values_list("name", flat=True)
    )


def metric_scope_payload(access: EffectiveAccess, scope: str) -> dict[str, str]:
    """Name the breadth the team figures cover, so a number is never ambiguous.

    Deliberately separate from ``operations_scope_payload``: that one describes
    administrative reach and reports a superuser without assignments as having
    none, while metric scope follows ``resolve_scope``.
    """
    if scope == MetricScope.COMPANY:
        return {"level": scope, "label": "Brokerage-wide"}
    if scope == MetricScope.REGION:
        names = _office_names(access.region_keys)
        label = names[0] if len(names) == 1 else f"{len(names)} regions"
        return {"level": scope, "label": label}
    if scope == MetricScope.OFFICE:
        names = _office_names(access.office_keys)
        label = names[0] if len(names) == 1 else f"{len(names)} offices"
        return {"level": scope, "label": label}
    return {"level": MetricScope.SELF, "label": "My book of business"}


def scoped_user_queryset(context: MetricContext):
    """Active users inside the caller's effective office scope."""
    return scope_queryset_for_user_office(
        context.user,
        User.objects.filter(is_active=True),
        field_name="office",
        access=context.access,
    )


# --------------------------------------------------------------------------- #
# Calculators
# --------------------------------------------------------------------------- #


def pending_source(context: MetricContext) -> MetricValue:
    """Placeholder calculator for a metric whose module is not connected.

    Never reached while its ``source_module`` is unavailable — the payload
    builder short-circuits first. It exists so the registry row is complete and
    the metric starts calculating the moment its module flips to available and
    a real calculator replaces this one.
    """
    raise NotImplementedError(
        "Source module is not connected; the registry must not calculate this metric."
    )


def calculate_new_agents(context: MetricContext) -> MetricValue:
    """Agents who joined the caller's scope inside the trailing window.

    The comparison is the *preceding* window of the same length, so the delta
    is a real period-over-period change rather than a trend guessed from the
    level. With no joiners in the prior window there is no honest percentage —
    dividing by zero or calling it infinite growth both misdescribe the data —
    so the card keeps its figure and its "vs. 0" line and simply carries no
    pill.
    """
    current = (
        dashboard_new_agent_queryset(
            context.user,
            at=context.now,
            days=NEW_AGENT_WINDOW_DAYS,
            access=context.access,
        )
        .filter(date_joined__lte=context.now)
        .count()
    )
    prior_window_end = trailing_window_start(context.now, days=NEW_AGENT_WINDOW_DAYS)
    previous = (
        dashboard_new_agent_queryset(
            context.user,
            at=context.now,
            days=NEW_AGENT_WINDOW_DAYS * 2,
            access=context.access,
        )
        .filter(date_joined__lte=prior_window_end)
        .count()
    )

    delta: str | None = None
    tone = "neutral"
    trend = "up" if current else "flat"
    if previous > 0:
        percent = round((current - previous) / previous * 100)
        if percent > 0:
            delta = f"+{percent}%"
            tone, trend = "success", "up"
        elif percent < 0:
            delta = f"{percent}%"
            tone, trend = "destructive", "down"
        else:
            tone = "neutral"
            trend = "flat"

    return MetricValue(
        value=format_count(current),
        hint=f"Joined in the last {NEW_AGENT_WINDOW_DAYS} days",
        tone=tone,
        trend=trend,
        raw_value=current,
        unit="count",
        delta=delta,
        compared_to=format_count(previous),
    )


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #

METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="ownActiveTransactions",
        label="Active transactions",
        group="myPipeline",
        order=10,
        scopes=(MetricScope.SELF,),
        source_module=SourceModule.TRANSACTIONS,
        calculator=pending_source,
        all_permissions=("web.view_own_transactions",),
        definition=(
            "Transactions where the signed-in user is the owning agent and the "
            "stage is neither settled nor cancelled. Point in time."
        ),
        icon="transactions",
    ),
    MetricDefinition(
        key="ownUpcomingClosings",
        label="Upcoming closings",
        group="myPipeline",
        order=20,
        scopes=(MetricScope.SELF,),
        source_module=SourceModule.TRANSACTIONS,
        calculator=pending_source,
        all_permissions=("web.view_own_transactions",),
        definition=(
            f"Own transactions with a closing date from now through "
            f"{UPCOMING_WINDOW_DAYS} days ahead, excluding already-settled deals."
        ),
        icon="closings",
    ),
    MetricDefinition(
        key="ownCommissionYtd",
        label="Commission YTD",
        group="myPipeline",
        order=30,
        scopes=(MetricScope.SELF,),
        source_module=SourceModule.COMMISSIONS,
        calculator=pending_source,
        format="currency",
        all_permissions=("web.view_own_commission",),
        definition=(
            "Commission credited to the signed-in user on transactions settled "
            "from local 1 January through now. Gross of splits."
        ),
        icon="commission",
    ),
    MetricDefinition(
        key="ownPendingTasks",
        label="Pending tasks",
        group="myWork",
        order=40,
        scopes=(MetricScope.SELF,),
        source_module=SourceModule.TASKS,
        calculator=pending_source,
        all_permissions=("web.view_own_tasks",),
        definition=(
            "Tasks assigned to the signed-in user that are not complete or "
            "cancelled. Point in time."
        ),
        icon="tasks",
    ),
    MetricDefinition(
        key="ownFollowUpsDue",
        label="Follow-ups due",
        group="myWork",
        order=50,
        scopes=(MetricScope.SELF,),
        source_module=SourceModule.TASKS,
        calculator=pending_source,
        all_permissions=("web.view_own_tasks",),
        definition=(
            "Own open follow-up tasks due before the end of the local calendar "
            "day, overdue ones included."
        ),
        icon="follow-ups",
    ),
    MetricDefinition(
        key="ownNewLeads",
        label="New leads",
        group="myWork",
        order=60,
        scopes=(MetricScope.SELF,),
        source_module=SourceModule.LEADS,
        calculator=pending_source,
        all_permissions=("web.view_own_leads",),
        definition=(
            "Leads assigned to the signed-in user in the trailing 30 days, "
            "counted by assignment time rather than capture time."
        ),
        icon="leads",
    ),
    MetricDefinition(
        key="teamActiveTransactions",
        label="Active transactions",
        group="teamOperations",
        order=110,
        scopes=MANAGED_SCOPES,
        source_module=SourceModule.TRANSACTIONS,
        calculator=pending_source,
        all_permissions=("web.view_transactions",),
        drill_down=MetricDrillDown(
            route_name="admin_transactions",
            label="View transactions",
        ),
        definition=(
            "Transactions whose office falls inside the caller's effective "
            "scope and whose stage is neither settled nor cancelled."
        ),
        icon="transactions",
    ),
    MetricDefinition(
        key="teamContractsAwaitingSignature",
        label="Contracts awaiting signature",
        group="teamOperations",
        order=120,
        scopes=MANAGED_SCOPES,
        source_module=SourceModule.CONTRACTS,
        calculator=pending_source,
        all_permissions=("web.view_agent_contracts",),
        drill_down=MetricDrillDown(
            route_name="admin_agent_contracts",
            label="View agent contracts",
        ),
        definition=(
            "Agent contracts in scope sitting in a pending-signature state, "
            "counted once per contract regardless of signer count."
        ),
        icon="contracts",
    ),
    MetricDefinition(
        key="teamOverdueInventory",
        label="Overdue inventory",
        group="teamOperations",
        order=130,
        scopes=MANAGED_SCOPES,
        source_module=SourceModule.INVENTORY,
        calculator=pending_source,
        all_permissions=("web.view_inventory",),
        drill_down=MetricDrillDown(
            route_name="admin_inventory",
            label="View inventory",
        ),
        definition=(
            "Inventory items in scope checked out with a due date earlier than "
            "the start of the current local day."
        ),
        icon="inventory",
    ),
    MetricDefinition(
        key="teamRoomUtilization",
        label="Room utilization",
        group="teamOperations",
        order=140,
        scopes=MANAGED_SCOPES,
        source_module=SourceModule.RESERVATIONS,
        calculator=pending_source,
        format="percent",
        all_permissions=("web.view_reservations",),
        drill_down=MetricDrillDown(
            route_name="admin_reservations",
            label="View reservations",
        ),
        definition=(
            "Booked room-minutes over bookable room-minutes across the trailing "
            "30 days for rooms in scope. The denominator counts published open "
            "hours only, so closed days never inflate it; a window with no "
            "bookable minutes reports as unmeasured rather than 0%. See "
            "utilization_ratio."
        ),
        icon="utilization",
    ),
    MetricDefinition(
        key="teamNewAgents",
        label="New agents",
        group="teamOversight",
        order=150,
        scopes=MANAGED_SCOPES,
        source_module=SourceModule.USER_DIRECTORY,
        calculator=calculate_new_agents,
        all_permissions=("web.view_new_agents",),
        drill_down=MetricDrillDown(
            route_name="admin_new_agents",
            label="View new agents",
        ),
        definition=(
            f"Active users whose office is inside the caller's effective scope "
            f"and who joined in the trailing {NEW_AGENT_WINDOW_DAYS} days."
        ),
        icon="new-agents",
    ),
    MetricDefinition(
        key="teamOpenTasks",
        label="Open tasks",
        group="teamOversight",
        order=160,
        scopes=MANAGED_SCOPES,
        source_module=SourceModule.TASKS,
        calculator=pending_source,
        all_permissions=("web.view_office_tasks",),
        definition=(
            "Tasks in scope that are neither complete nor cancelled, counted "
            "once per task even when several people are assigned to it."
        ),
        icon="tasks",
    ),
    MetricDefinition(
        key="teamComplianceExceptions",
        label="Compliance exceptions",
        group="teamOversight",
        order=170,
        scopes=MANAGED_SCOPES,
        source_module=SourceModule.COMPLIANCE,
        calculator=pending_source,
        all_permissions=("web.view_compliance",),
        drill_down=MetricDrillDown(
            route_name="admin_compliance",
            label="View compliance",
        ),
        definition=(
            "Open compliance exceptions raised against records in scope, "
            "excluding those already waived or resolved."
        ),
        icon="compliance",
    ),
)

METRIC_BY_KEY = {definition.key: definition for definition in METRIC_DEFINITIONS}


def _validate_registry() -> None:
    """Fail fast on a malformed registry row rather than at request time."""
    seen: set[str] = set()
    for definition in METRIC_DEFINITIONS:
        if definition.key in seen:
            raise ValueError(f"Duplicate metric key: {definition.key}")
        seen.add(definition.key)
        if definition.group not in METRIC_GROUP_BY_KEY:
            raise ValueError(f"{definition.key}: unknown group {definition.group!r}")
        if definition.source_module not in SOURCE_MODULE_AVAILABILITY:
            raise ValueError(
                f"{definition.key}: unknown source module {definition.source_module!r}"
            )
        if definition.source_module not in SOURCE_MODULE_UNAVAILABLE_REASON:
            raise ValueError(
                f"{definition.key}: source module {definition.source_module!r} "
                "has no unavailable reason"
            )
        if not definition.scopes:
            raise ValueError(f"{definition.key}: at least one scope is required")
        for scope in definition.scopes:
            if scope not in SCOPE_ORDER:
                raise ValueError(f"{definition.key}: unknown scope {scope!r}")
        if definition.unavailable_behavior not in {
            UnavailableBehavior.MARK,
            UnavailableBehavior.OMIT,
        }:
            raise ValueError(
                f"{definition.key}: unknown unavailable behavior "
                f"{definition.unavailable_behavior!r}"
            )
        if not definition.definition:
            raise ValueError(f"{definition.key}: a calculation definition is required")
        if not definition.icon:
            raise ValueError(f"{definition.key}: an icon key is required")
        assert_drill_down_is_guarded(definition)


def assert_drill_down_is_guarded(definition: MetricDefinition) -> None:
    """A card may only link where the metric's own permissions already reach.

    Hiding a card is a courtesy; this is the part that makes revoking a
    permission remove the underlying data too.
    """
    if definition.drill_down is None:
        return
    policies = [
        policy
        for policy in ROUTE_POLICIES.values()
        if definition.drill_down.route_name in policy.route_names
    ]
    if not policies:
        raise ValueError(
            f"{definition.key}: drill-down route "
            f"{definition.drill_down.route_name!r} has no authorization policy"
        )
    guarded = set(policies[0].all_permissions)
    missing = set(definition.all_permissions) - guarded
    if missing:
        raise ValueError(
            f"{definition.key}: drill-down {definition.drill_down.route_name!r} "
            f"does not require {sorted(missing)}"
        )


_validate_registry()


# --------------------------------------------------------------------------- #
# Selection and payload
# --------------------------------------------------------------------------- #


def has_metric_permissions(
    user: User, definition: MetricDefinition, access: EffectiveAccess
) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return all(
        permission in access.permissions for permission in definition.all_permissions
    )


def is_self_metric(definition: MetricDefinition) -> bool:
    return definition.scopes == (MetricScope.SELF,)


def scope_permits(definition: MetricDefinition, scope: str) -> bool:
    """Self-scope metrics are never gated on breadth.

    Everyone reads their own book of business, so gaining a management role
    adds team cards without ever removing the agent ones — the "no downgrade"
    half of multi-role resolution.
    """
    return is_self_metric(definition) or scope in definition.scopes


def select_metrics(
    user: User, *, access: EffectiveAccess | None = None
) -> tuple[MetricDefinition, ...]:
    """The metrics this user is entitled to, in registry order.

    Deterministic for multi-role users: the registry is a fixed ordered tuple
    and each key appears in it once, so a union of role entitlements can never
    duplicate a card or reorder the dashboard between requests.
    """
    if not getattr(user, "is_authenticated", False):
        return ()
    effective = get_effective_access(user) if access is None else access
    scope = resolve_scope(user, effective)
    return tuple(
        definition
        for definition in METRIC_DEFINITIONS
        if scope_permits(definition, scope)
        and has_metric_permissions(user, definition, effective)
    )


def _metric_scope_level(definition: MetricDefinition, scope: str) -> str:
    return MetricScope.SELF if is_self_metric(definition) else scope


def _unavailable_reason(definition: MetricDefinition) -> str:
    return SOURCE_MODULE_UNAVAILABLE_REASON[definition.source_module]


def _drill_down_payload(definition: MetricDefinition) -> dict[str, str] | None:
    """Server-reversed href.

    Reversing here rather than in the page keeps the destination in step with
    ``urls.py`` without the component holding a route name it would have to
    widen ``routes`` typing to call.
    """
    if definition.drill_down is None:
        return None
    return {
        "href": reverse(
            definition.drill_down.route_name, args=definition.drill_down.args
        ),
        "label": definition.drill_down.label,
    }


def _metric_payload(definition: MetricDefinition, context: MetricContext) -> dict:
    payload: dict[str, Any] = {
        "key": definition.key,
        "label": definition.label,
        "format": definition.format,
        "scopeLevel": _metric_scope_level(definition, context.scope),
        "definition": definition.definition,
        "asOf": context.now.isoformat(),
        "drillDown": _drill_down_payload(definition),
        "icon": definition.icon,
    }
    if not SOURCE_MODULE_AVAILABILITY[definition.source_module]:
        return {
            **payload,
            "availability": Availability.UNAVAILABLE,
            "unavailableReason": _unavailable_reason(definition),
            "value": None,
            "hint": "",
            "tone": "neutral",
            "trend": "flat",
        }
    calculated = definition.calculator(context)
    measured: dict[str, Any] = {
        **payload,
        "availability": Availability.AVAILABLE,
        "value": calculated.value,
        "hint": calculated.hint,
        "tone": calculated.tone,
        "trend": calculated.trend,
    }
    if calculated.raw_value is not None:
        measured["rawValue"] = calculated.raw_value
    if calculated.unit:
        measured["unit"] = calculated.unit
    if calculated.delta is not None:
        measured["delta"] = calculated.delta
    if calculated.compared_to is not None:
        measured["comparedTo"] = calculated.compared_to
    return measured


def dashboard_metrics(
    user: User,
    *,
    at: datetime | None = None,
    access: EffectiveAccess | None = None,
) -> dict[str, Any]:
    """Grouped metric payload for the Inertia dashboard page."""
    effective = get_effective_access(user) if access is None else access
    scope = resolve_scope(user, effective)
    context = MetricContext(
        user=user,
        access=effective,
        scope=scope,
        now=at or now(),
    )
    selected = [
        definition
        for definition in select_metrics(user, access=effective)
        if SOURCE_MODULE_AVAILABILITY[definition.source_module]
        or definition.unavailable_behavior == UnavailableBehavior.MARK
    ]
    groups = []
    for group in sorted(METRIC_GROUPS, key=lambda item: item.order):
        metrics = [
            _metric_payload(definition, context)
            for definition in selected
            if definition.group == group.key
        ]
        if not metrics:
            continue
        groups.append(
            {
                "key": group.key,
                "title": group.title,
                "description": group.description,
                "metrics": metrics,
            }
        )
    # An agent's own office-scoped assignment gives them office *reach*, but
    # they hold no team permission, so no team figure is on the page. Reporting
    # their branch as the scope of a dashboard that only shows their own book
    # would misdescribe every number on it.
    reported_scope = (
        scope
        if any(not is_self_metric(definition) for definition in selected)
        else MetricScope.SELF
    )
    return {
        "scope": metric_scope_payload(effective, reported_scope),
        "groups": groups,
    }
