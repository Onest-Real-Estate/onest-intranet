"""Privacy-aware peer Agent Directory.

Company-wide among authenticated readers. Visibility and field projection are
the security boundary — there is no separate capability permission.

Rules
-----
* Only ``is_active`` users with ``agent_status`` in {active, on_leave} appear.
* Search, filters, counts, detail, and headshot streaming all run inside that
  queryset so inactive or hidden people cannot be enumerated.
* Rows omit private/admin keys rather than sending null.
* Headshot URLs are gated routes, never raw media paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import connection
from django.db.models import Q, QuerySet
from django.urls import reverse

from apps.user.administration_fields import ACTIVE, ON_LEAVE
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.profile_fields import (
    LANGUAGE_NAMES,
    SPECIALTY_NAMES,
    language_options,
    specialty_options,
)
from apps.user.roles import ROLE_DEFINITIONS, ROLE_LABELS, normalize_role_code
from apps.user.services.role_assignments import get_effective_role_keys
from apps.user.us import US_STATE_CHOICES, US_STATE_CODES
from apps.web.contracts import list_response

PAGE_SIZE = 24
MAX_PAGE_SIZE = 100
MAX_QUERY_LENGTH = 120

DIRECTORY_VISIBLE_STATUSES = frozenset({ACTIVE, ON_LEAVE})

LIVE_ASSIGNMENT_STATUSES = (
    UserRoleAssignment.Status.SCHEDULED,
    UserRoleAssignment.Status.ACTIVE,
)

VIEW_MODES = frozenset({"grid", "list"})

# Keys that must never appear on a directory person payload.
FORBIDDEN_PERSON_KEYS = frozenset(
    {
        "streetAddress",
        "city",
        "state",
        "zipCode",
        "internalNotes",
        "agentIdentifier",
        "agentId",
        "agentStatus",
        "permissions",
        "contract",
        "onboarding",
        "accountState",
        "accountStatus",
        "mlsNumber",
        "nrdsNumber",
        "licenseNumber",
        "licenseExpiresOn",
        "licenseVerification",
        "bio",
        "websiteUrl",
        "linkedinUrl",
        "facebookUrl",
        "instagramUrl",
        "xUrl",
        "isStaff",
        "isSuperuser",
        "isActive",
        "startDate",
        "lastLogin",
        "emailVerified",
        "preferredContactMethod",
        "headshotUrl",  # raw media — only headshotPath (gated) is allowed
    }
)


@dataclass(frozen=True)
class AgentDirectoryFilters:
    q: str = ""
    office: str = ""
    region: str = ""
    role: str = ""
    license_state: str = ""
    specialty: str = ""
    language: str = ""
    view: str = "grid"

    def as_payload(self) -> dict[str, str]:
        return {
            "q": self.q,
            "office": self.office,
            "region": self.region,
            "role": self.role,
            "licenseState": self.license_state,
            "specialty": self.specialty,
            "language": self.language,
            "view": self.view,
        }


def directory_visible_queryset() -> QuerySet[User]:
    """Every person the peer directory may acknowledge."""
    return User.objects.filter(
        is_active=True,
        agent_status__in=sorted(DIRECTORY_VISIBLE_STATUSES),
    ).select_related("office", "office__region")


def is_directory_visible(user: User | None) -> bool:
    if user is None:
        return False
    return bool(user.is_active and user.agent_status in DIRECTORY_VISIBLE_STATUSES)


def get_visible_user(user_id: int) -> User | None:
    return directory_visible_queryset().filter(pk=user_id).first()


def parse_filters(params) -> AgentDirectoryFilters:
    office = (params.get("office") or "").strip()
    office = office if office.isdigit() else ""

    region = (params.get("region") or "").strip()
    if not region.isdigit():
        region = ""

    role_raw = (params.get("role") or "").strip()
    role = normalize_role_code(role_raw) or ""
    if role and role not in {definition.code for definition in ROLE_DEFINITIONS}:
        role = ""

    license_state = params.get("licenseState") or params.get("license_state") or ""
    license_state = license_state.strip().upper()
    if license_state not in US_STATE_CODES:
        license_state = ""

    specialty = (params.get("specialty") or "").strip().lower()
    if specialty not in SPECIALTY_NAMES:
        specialty = ""

    language = (params.get("language") or "").strip().lower()
    if language not in LANGUAGE_NAMES:
        language = ""

    view = (params.get("view") or "").strip()
    if view not in VIEW_MODES:
        view = "grid"

    return AgentDirectoryFilters(
        q=(params.get("q") or "").strip()[:MAX_QUERY_LENGTH],
        office=office,
        region=region,
        role=role,
        license_state=license_state,
        specialty=specialty,
        language=language,
        view=view,
    )


def parse_page(params, *, default: int = 1) -> int:
    try:
        return max(1, int(params.get("page", default)))
    except (TypeError, ValueError):
        return 1


def _json_list_has(queryset: QuerySet[User], field: str, code: str) -> QuerySet[User]:
    """Filter rows whose JSON list field includes ``code``.

    PostgreSQL supports ``__contains`` on JSON lists. SQLite (test default)
    does not, so fall back to a quoted-token ``icontains`` on the stored text.
    Codes are closed-set ASCII, so the token match is unambiguous.
    """
    if connection.vendor == "postgresql":
        return queryset.filter(**{f"{field}__contains": [code]})
    return queryset.filter(**{f"{field}__icontains": f'"{code}"'})


def apply_filters(
    queryset: QuerySet[User], filters: AgentDirectoryFilters
) -> QuerySet[User]:
    """Narrow an already-visible queryset. Filters only ever remove rows."""
    if filters.q:
        term = filters.q
        queryset = queryset.filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(display_name__icontains=term)
            | Q(preferred_name__icontains=term)
            | Q(office__name__icontains=term)
        )
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
    if filters.license_state:
        queryset = queryset.filter(license_state=filters.license_state)
    if filters.specialty:
        queryset = _json_list_has(queryset, "specialties", filters.specialty)
    if filters.language:
        queryset = _json_list_has(queryset, "languages", filters.language)
    return queryset


def _directory_role_labels(user: User) -> list[str]:
    return [ROLE_LABELS.get(key, key) for key in get_effective_role_keys(user)]


def _labeled_codes(
    codes: list[str] | None, names: dict[str, str]
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for code in codes or []:
        if code in names:
            result.append({"code": code, "name": names[code]})
    return result


def project_directory_person(user: User) -> dict[str, Any]:
    """Allowlisted peer-directory projection. Omits private/admin keys."""
    office = user.office
    headshot_path = (
        reverse("agent_directory_headshot", args=[user.pk]) if user.headshot else None
    )
    person = {
        "id": user.pk,
        "preferredName": user.preferred_display_name(),
        "roles": _directory_role_labels(user),
        "office": (
            {
                "id": office.pk,
                "name": office.name,
                "pathLabel": office.path_label(),
                "regionName": office.region_name(),
            }
            if office is not None
            else None
        ),
        "workPhone": user.phone_number or "",
        "workEmail": user.email,
        "specialties": _labeled_codes(user.specialties, SPECIALTY_NAMES),
        "languages": _labeled_codes(user.languages, LANGUAGE_NAMES),
        "licenseState": user.license_state or "",
        "licenseStateName": (
            dict(US_STATE_CHOICES).get(user.license_state, user.license_state)
            if user.license_state
            else ""
        ),
        "headshotPath": headshot_path,
    }
    leaked = FORBIDDEN_PERSON_KEYS & person.keys()
    if leaked:  # pragma: no cover - defensive invariant
        raise RuntimeError(f"Directory projection leaked keys: {sorted(leaked)}")
    return person


def filter_options() -> dict[str, Any]:
    """Company-wide filter choices for the peer directory."""
    offices = (
        Office.visible_queryset()
        .filter(is_active=True, is_assignable=True)
        .order_by("name")
    )
    regions = (
        Office.visible_queryset()
        .filter(is_active=True, kind=Office.Kind.REGION)
        .order_by("name")
    )
    return {
        "offices": [
            {"value": str(office.pk), "label": office.path_label()}
            for office in offices
        ],
        "regions": [
            {"value": str(office.pk), "label": office.name} for office in regions
        ],
        "roles": [
            {"value": definition.code, "label": definition.label}
            for definition in ROLE_DEFINITIONS
            if definition.assignable
        ],
        "licenseStates": [
            {"value": code, "label": name} for code, name in US_STATE_CHOICES
        ],
        "specialties": [
            {"value": item["code"], "label": item["name"]}
            for item in specialty_options()
        ],
        "languages": [
            {"value": item["code"], "label": item["name"]}
            for item in language_options()
        ],
    }


def empty_state(
    *,
    total_visible: int,
    filtered_total: int,
    filters: AgentDirectoryFilters,
) -> dict[str, str] | None:
    if total_visible == 0:
        return {
            "kind": "no-people",
            "title": "No people in the directory yet",
            "description": (
                "Active agents will appear here once their accounts are ready."
            ),
        }
    if filtered_total == 0:
        has_filters = any(
            [
                filters.q,
                filters.office,
                filters.region,
                filters.role,
                filters.license_state,
                filters.specialty,
                filters.language,
            ]
        )
        if has_filters:
            return {
                "kind": "no-results",
                "title": "No matching people",
                "description": "Try a different name or clear one of the filters.",
            }
        return {
            "kind": "no-results",
            "title": "No matching people",
            "description": "Nobody matches this view right now.",
        }
    return None


@dataclass(frozen=True)
class AgentDirectoryPage:
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = PAGE_SIZE
    filters: AgentDirectoryFilters = field(default_factory=AgentDirectoryFilters)


def build_agent_directory_page(
    *,
    filters: AgentDirectoryFilters,
    page: int,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """Visibility → filter → count → page → project."""
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    visible = directory_visible_queryset()
    total_visible = visible.count()
    filtered = apply_filters(visible, filters)
    ordered = filtered.order_by("first_name", "last_name", "pk")
    total = filtered.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(page, 1), total_pages)
    start = (page - 1) * page_size
    page_users = ordered[start : start + page_size]
    rows = [project_directory_person(user) for user in page_users]
    return {
        "people": list_response(
            items=rows,
            total_items=total,
            page=page,
            page_size=page_size,
            filters=filters.as_payload(),
            sort_key="name",
            sort_direction="asc",
        ),
        "filterOptions": filter_options(),
        "empty": empty_state(
            total_visible=total_visible,
            filtered_total=total,
            filters=filters,
        ),
    }


def build_agent_directory_detail(user_id: int) -> dict[str, Any] | None:
    user = get_visible_user(user_id)
    if user is None:
        return None
    return {"person": project_directory_person(user)}
