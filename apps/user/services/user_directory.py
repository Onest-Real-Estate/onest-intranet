"""The scoped people directory: search, filters, and what each reader may see.

This is the product-level replacement for opening Django admin to find
somebody. Three rules shape every function here.

**Scope before anything.** The queryset is narrowed to the actor's own office
and region grant *before* a search term, a filter, a count, or a sort is
applied. No filter widens it: an office or region id the actor cannot reach
intersects an already-narrowed set and yields nothing, so a crafted parameter
returns an empty page rather than a leak — and never reveals whether the id
existed.

**Fields are a second permission layer.** Holding ``web.view_users`` gets you
identity, office, and account state. Administrative facts (status, agent ID,
license verification) need ``user.view_user_administration``; contract standing
needs ``web.view_agent_contracts``; onboarding progress needs
``web.view_new_agents``. Rows *omit* the keys a reader may not have rather than
sending null: a key that is present but empty still tells you a field exists.

**Derived state is filtered where it is stored.** Onboarding and last-login
filters compile to SQL rather than to a Python pass over every scoped user, so
a directory of a few thousand people still answers in one query. Source-owned
state that the hub does not store — the contract domain — is offered as a
filter only when that domain is connected, and reports why when it is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.user.administration_fields import (
    AGENT_STATUS_LABELS,
    AGENT_STATUS_TONES,
    agent_status_options,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import ROLE_DEFINITIONS, normalize_role_code
from apps.user.services.agent_administration import (
    CHANGE_PERMISSION,
    VIEW_PERMISSION,
    administered_user_queryset,
    contract_domain,
    contract_status,
)
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)

CONTRACT_PERMISSION = "web.view_agent_contracts"
ONBOARDING_PERMISSION = "web.view_new_agents"
ACCOUNT_STATE_PERMISSION = "user.manage_account_state"

PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

LIVE_ASSIGNMENT_STATUSES = (
    UserRoleAssignment.Status.SCHEDULED,
    UserRoleAssignment.Status.ACTIVE,
)


# ---------------------------------------------------------------------------
# Field visibility
# ---------------------------------------------------------------------------


class FieldGroup:
    """Named bundles of columns, each behind one permission."""

    IDENTITY = "identity"
    ADMINISTRATION = "administration"
    CONTRACT = "contract"
    ONBOARDING = "onboarding"
    NOTES = "notes"


def visible_field_groups(actor: User) -> frozenset[str]:
    """Which bundles this actor may read, capability-only (scope is separate)."""
    groups = {FieldGroup.IDENTITY}
    if has_effective_permission(actor, VIEW_PERMISSION):
        groups.add(FieldGroup.ADMINISTRATION)
    if has_effective_permission(actor, CHANGE_PERMISSION):
        # Operational notes are withheld from readers as well as from the
        # person they are about: reading somebody's disciplinary note is not
        # implied by being allowed to look them up.
        groups.add(FieldGroup.NOTES)
    if has_effective_permission(actor, CONTRACT_PERMISSION):
        groups.add(FieldGroup.CONTRACT)
    if has_effective_permission(actor, ONBOARDING_PERMISSION):
        groups.add(FieldGroup.ONBOARDING)
    return frozenset(groups)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class AccountState:
    ACTIVE = "active"
    DISABLED = "disabled"


class OnboardingState:
    """Directory-level onboarding, derived from what the hub itself stores.

    Deliberately coarser than the source-derived state on the New Agent List:
    that one asks the contract and training domains, this one only asks whether
    the person finished the hub's own profile flow. Two names for two questions
    beats one name that means different things on two pages.
    """

    COMPLETE = "complete"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"


class LastLoginWindow:
    NEVER = "never"
    WEEK = "7d"
    MONTH = "30d"
    QUARTER = "90d"
    DORMANT = "over_90d"


_LAST_LOGIN_DAYS = {
    LastLoginWindow.WEEK: 7,
    LastLoginWindow.MONTH: 30,
    LastLoginWindow.QUARTER: 90,
}

SORT_KEYS: frozenset[str] = frozenset(
    {"name", "email", "office", "status", "lastLogin", "startDate"}
)

_SORT_FIELDS: dict[str, tuple[str, ...]] = {
    "name": ("first_name", "last_name", "email"),
    "email": ("email",),
    "office": ("office__name", "first_name", "last_name"),
    "status": ("agent_status", "first_name", "last_name"),
    "lastLogin": ("last_login", "first_name", "last_name"),
    "startDate": ("start_date", "first_name", "last_name"),
}

# Sorts that expose an administrative column, and therefore need its grant.
_ADMINISTRATIVE_SORTS = frozenset({"status", "startDate"})


@dataclass(frozen=True)
class DirectoryFilters:
    """The reader's request, already reduced to values the server recognizes.

    Every field is a plain string so the payload round-trips through the URL
    unchanged. Nothing here is trusted: an id is only ever used to *narrow* an
    already-scoped queryset.
    """

    q: str = ""
    office: str = ""
    region: str = ""
    role: str = ""
    status: str = ""
    account: str = ""
    onboarding: str = ""
    contract: str = ""
    last_login: str = ""

    def as_payload(self) -> dict[str, str]:
        return {
            "q": self.q,
            "office": self.office,
            "region": self.region,
            "role": self.role,
            "status": self.status,
            "account": self.account,
            "onboarding": self.onboarding,
            "contract": self.contract,
            "lastLogin": self.last_login,
        }

    @property
    def active_count(self) -> int:
        return sum(
            1 for key, value in self.as_payload().items() if key != "q" and value
        )


def parse_filters(params) -> DirectoryFilters:
    """Read the query string. Unknown values are dropped, never echoed back."""

    def value(key: str) -> str:
        return (params.get(key) or "").strip()

    def one_of(key: str, allowed) -> str:
        raw = value(key)
        return raw if raw in allowed else ""

    def digits(key: str) -> str:
        raw = value(key)
        return raw if raw.isdigit() else ""

    role = normalize_role_code(value("role")) or ""
    return DirectoryFilters(
        q=value("q")[:200],
        office=digits("office"),
        region=digits("region"),
        role=role,
        status=one_of("status", AGENT_STATUS_LABELS),
        account=one_of("account", {AccountState.ACTIVE, AccountState.DISABLED}),
        onboarding=one_of(
            "onboarding",
            {
                OnboardingState.COMPLETE,
                OnboardingState.IN_PROGRESS,
                OnboardingState.NOT_STARTED,
            },
        ),
        contract=value("contract")[:64],
        last_login=one_of(
            "lastLogin",
            {
                LastLoginWindow.NEVER,
                LastLoginWindow.WEEK,
                LastLoginWindow.MONTH,
                LastLoginWindow.QUARTER,
                LastLoginWindow.DORMANT,
            },
        ),
    )


def parse_sort(params) -> tuple[str, str]:
    key = (params.get("sort") or "").strip()
    if key not in SORT_KEYS:
        key = "name"
    direction = "desc" if (params.get("direction") or "").strip() == "desc" else "asc"
    return key, direction


def parse_page(params) -> int:
    try:
        return max(1, int(params.get("page", "1")))
    except (TypeError, ValueError):
        return 1


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------


def directory_queryset(actor: User) -> QuerySet[User]:
    """Every user this actor may look up. Already scoped; never widen it."""
    return administered_user_queryset(actor)


def apply_filters(
    queryset: QuerySet[User],
    filters: DirectoryFilters,
    *,
    groups: frozenset[str],
) -> QuerySet[User]:
    """Narrow an already-scoped queryset. Filters only ever remove rows."""
    if filters.q:
        term = filters.q
        search = (
            Q(email__icontains=term)
            | Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(display_name__icontains=term)
            | Q(preferred_name__icontains=term)
        )
        if FieldGroup.ADMINISTRATION in groups:
            # Matching on a value the reader may not see would leak it one
            # character at a time.
            search |= Q(agent_identifier__icontains=term.upper())
        queryset = queryset.filter(search)
    if filters.office:
        queryset = queryset.filter(office_id=int(filters.office))
    if filters.region:
        region_id = int(filters.region)
        queryset = queryset.filter(
            Q(office__region_id=region_id) | Q(office_id=region_id)
        )
    if filters.role:
        queryset = queryset.filter(
            role_assignments__role=filters.role,
            role_assignments__status__in=LIVE_ASSIGNMENT_STATUSES,
        ).distinct()
    if filters.status and FieldGroup.ADMINISTRATION in groups:
        queryset = queryset.filter(agent_status=filters.status)
    if filters.account == AccountState.ACTIVE:
        queryset = queryset.filter(is_active=True)
    elif filters.account == AccountState.DISABLED:
        queryset = queryset.filter(is_active=False)
    queryset = _apply_onboarding_filter(queryset, filters.onboarding)
    return _apply_last_login_filter(queryset, filters.last_login)


def _apply_onboarding_filter(queryset: QuerySet[User], value: str) -> QuerySet[User]:
    if value == OnboardingState.COMPLETE:
        return queryset.filter(profile_completed=True)
    if value == OnboardingState.IN_PROGRESS:
        return queryset.filter(profile_completed=False, last_login__isnull=False)
    if value == OnboardingState.NOT_STARTED:
        return queryset.filter(profile_completed=False, last_login__isnull=True)
    return queryset


def _apply_last_login_filter(queryset: QuerySet[User], value: str) -> QuerySet[User]:
    if value == LastLoginWindow.NEVER:
        return queryset.filter(last_login__isnull=True)
    days = _LAST_LOGIN_DAYS.get(value)
    if days is not None:
        return queryset.filter(last_login__gte=timezone.now() - timedelta(days=days))
    if value == LastLoginWindow.DORMANT:
        return queryset.filter(last_login__lt=timezone.now() - timedelta(days=90))
    return queryset


def apply_sort(
    queryset: QuerySet[User],
    *,
    sort: str,
    direction: str,
    groups: frozenset[str],
) -> tuple[QuerySet[User], str]:
    """Order the page, falling back to name for a column the reader cannot see."""
    if sort in _ADMINISTRATIVE_SORTS and FieldGroup.ADMINISTRATION not in groups:
        sort = "name"
    fields = _SORT_FIELDS[sort]
    prefix = "-" if direction == "desc" else ""
    # Only the leading column flips; the tie-breakers stay stable so a page
    # boundary never lands in the middle of a run of equal values.
    ordering = [f"{prefix}{fields[0]}", *fields[1:], "pk"]
    return queryset.order_by(*ordering), sort


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


def _status_payload(user: User) -> dict[str, str]:
    return {
        "value": user.agent_status,
        "label": AGENT_STATUS_LABELS.get(user.agent_status, user.agent_status),
        "tone": AGENT_STATUS_TONES.get(user.agent_status, "neutral"),
    }


def onboarding_state_of(user: User) -> str:
    if user.profile_completed:
        return OnboardingState.COMPLETE
    return (
        OnboardingState.IN_PROGRESS if user.last_login else OnboardingState.NOT_STARTED
    )


_ONBOARDING_PRESENTATION: dict[str, tuple[str, str]] = {
    OnboardingState.COMPLETE: ("Complete", "success"),
    OnboardingState.IN_PROGRESS: ("In progress", "warning"),
    OnboardingState.NOT_STARTED: ("Not started", "neutral"),
}


def onboarding_payload(user: User) -> dict[str, str]:
    value = onboarding_state_of(user)
    label, tone = _ONBOARDING_PRESENTATION[value]
    return {"value": value, "label": label, "tone": tone}


def directory_row(user: User, *, groups: frozenset[str]) -> dict[str, Any]:
    """One row, carrying only the keys this reader is allowed to have."""
    row: dict[str, Any] = {
        "id": user.pk,
        "name": str(user),
        "email": user.email,
        "officeName": user.office.name if user.office else None,
        "officePathLabel": user.office.path_label() if user.office else None,
        "regionName": user.office.region_name() if user.office else None,
        "isActive": user.is_active,
        "accountState": {
            "value": AccountState.ACTIVE if user.is_active else AccountState.DISABLED,
            "label": "Active" if user.is_active else "Disabled",
            "tone": "success" if user.is_active else "destructive",
        },
        "lastLoginAt": user.last_login.isoformat() if user.last_login else None,
        "onboarding": onboarding_payload(user),
    }
    if FieldGroup.ADMINISTRATION in groups:
        row["agentStatus"] = _status_payload(user)
        row["agentIdentifier"] = user.agent_identifier
        row["startDate"] = user.start_date.isoformat() if user.start_date else None
    if FieldGroup.CONTRACT in groups:
        status = contract_status(user)
        row["contract"] = {
            "value": status["status"],
            "label": status["label"],
            "tone": status["tone"],
            "available": status["available"],
        }
    return row


def directory_summary(queryset: QuerySet[User]) -> dict[str, int]:
    """Counts over the *scoped* queryset — never over ``User.objects``.

    A total that includes people the reader cannot open is an enumeration
    oracle, so the summary is computed from the same queryset the rows are.
    """
    total = queryset.count()
    disabled = queryset.filter(is_active=False).count()
    return {
        "total": total,
        "active": total - disabled,
        "disabled": disabled,
        "pendingOnboarding": queryset.filter(profile_completed=False).count(),
    }


def contract_filter_options(actor: User) -> dict[str, Any]:
    """Contract states to filter by, or the reason there are none.

    The contract domain owns these values. Until it is connected the filter is
    rendered disabled with this reason rather than silently absent, so nobody
    reads "no contract filter" as "no contracts".
    """
    if not has_effective_permission(actor, CONTRACT_PERMISSION):
        return {"available": False, "reason": "", "options": []}
    module = contract_domain()
    if module is None:
        return {
            "available": False,
            "reason": "Agent contracts are not connected to the hub yet.",
            "options": [],
        }
    return {  # pragma: no cover - exercised once the contract app exists
        "available": True,
        "reason": "",
        "options": list(module.contract_status_options()),
    }


def _scoped_offices(actor: User) -> QuerySet[Office]:
    """Offices and regions the actor may name, drawn from their own grant."""
    access = get_effective_access(actor)
    queryset = Office.visible_queryset().filter(is_active=True)
    if getattr(actor, "is_superuser", False) or access.company_wide:
        return queryset
    filters = Q()
    if access.office_keys:
        filters |= Q(stable_key__in=sorted(access.office_keys))
    if access.region_keys:
        keys = sorted(access.region_keys)
        filters |= Q(stable_key__in=keys) | Q(region__stable_key__in=keys)
    if not filters:
        return queryset.none()
    return queryset.filter(filters)


def filter_options(actor: User, *, groups: frozenset[str]) -> dict[str, Any]:
    """Every choice the filter bar offers, built from the actor's own scope."""
    offices = _scoped_offices(actor)
    options: dict[str, Any] = {
        "offices": [
            {"value": str(office.pk), "label": office.path_label()}
            for office in offices.filter(is_assignable=True)
        ],
        "regions": [
            {"value": str(office.pk), "label": office.name}
            for office in offices.filter(kind=Office.Kind.REGION)
        ],
        "roles": [
            {"value": definition.key, "label": definition.label}
            for definition in ROLE_DEFINITIONS
            if definition.assignable
        ],
        "accountStates": [
            {"value": AccountState.ACTIVE, "label": "Active"},
            {"value": AccountState.DISABLED, "label": "Disabled"},
        ],
        "onboardingStates": [
            {"value": value, "label": label}
            for value, (label, _tone) in _ONBOARDING_PRESENTATION.items()
        ],
        "lastLoginWindows": [
            {"value": LastLoginWindow.WEEK, "label": "In the last 7 days"},
            {"value": LastLoginWindow.MONTH, "label": "In the last 30 days"},
            {"value": LastLoginWindow.QUARTER, "label": "In the last 90 days"},
            {"value": LastLoginWindow.DORMANT, "label": "Over 90 days ago"},
            {"value": LastLoginWindow.NEVER, "label": "Never signed in"},
        ],
        "contract": contract_filter_options(actor),
    }
    if FieldGroup.ADMINISTRATION in groups:
        options["agentStatuses"] = agent_status_options()
    return options


@dataclass(frozen=True)
class DirectoryPage:
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = PAGE_SIZE
    sort: str = "name"
    direction: str = "asc"


def build_directory_page(
    actor: User,
    *,
    filters: DirectoryFilters,
    sort: str,
    direction: str,
    page: int,
    page_size: int = PAGE_SIZE,
) -> tuple[DirectoryPage, dict[str, int], frozenset[str]]:
    """Scope, filter, sort, count, and slice — in that order, every time."""
    groups = visible_field_groups(actor)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    scoped = directory_queryset(actor)
    filtered = apply_filters(scoped, filters, groups=groups)
    ordered, sort = apply_sort(filtered, sort=sort, direction=direction, groups=groups)
    total = filtered.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(page, 1), total_pages)
    start = (page - 1) * page_size
    rows = [
        directory_row(user, groups=groups)
        for user in ordered[start : start + page_size]
    ]
    return (
        DirectoryPage(
            rows=rows,
            total=total,
            page=page,
            page_size=page_size,
            sort=sort,
            direction=direction,
        ),
        directory_summary(scoped),
        groups,
    )
