"""Scoped office and regional administration.

Owns list/detail payloads, field-tier edits, contact assignments, impact
analysis for hierarchy/status changes, and audit. Guarding the React page is
not security — every write re-checks ``web.manage_offices`` and office-tree
scope here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import (
    Office,
    OfficeContactAssignment,
    User,
    UserOfficeMembership,
    UserRoleAssignment,
)
from apps.user.office_payloads import office_info_payload, office_selector_payload
from apps.user.services.hierarchy import descendant_queryset, transfer_office
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)
from apps.user.us import normalize_us_phone, normalize_us_zip
from apps.web.authorization import scope_queryset_for_offices
from apps.web.contracts import list_response
from apps.web.operations import OPERATIONS_FEATURES, operations_scope_payload

MANAGE_PERMISSION = "web.manage_offices"

INFO_FIELDS: tuple[str, ...] = (
    "name",
    "street_address",
    "city",
    "state",
    "zip_code",
    "main_phone",
    "public_email",
    "office_hours",
    "parking_instructions",
    "access_instructions",
    "access_instructions_internal",
)

SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {"internal_email", "access_instructions", "access_instructions_internal"}
)

# Writable with manage_offices in scope (includes sensitive operational fields).
EDITABLE_IN_SCOPE: tuple[str, ...] = INFO_FIELDS + ("internal_email",)

# Company-wide only; require impact preview + confirmed=1.
HIGH_IMPACT_FIELDS: frozenset[str] = frozenset(
    {"parent", "kind", "is_active", "is_assignable"}
)

CONTACT_TYPES: tuple[str, ...] = tuple(
    choice.value for choice in OfficeContactAssignment.AssignmentType
)

PAGE_SIZE = 50


class StaleOfficeVersion(Exception):
    """Optimistic concurrency token no longer matches the office row."""


class ConfirmationRequired(Exception):
    """High-impact change needs an explicit confirm after impact preview."""

    def __init__(self, impact: list[dict[str, str]], message: str | None = None):
        self.impact = impact
        super().__init__(
            message
            or _(
                "This change is high-impact. Confirm the impact preview before saving."
            )
        )


# ---------------------------------------------------------------------------
# Scope and authority
# ---------------------------------------------------------------------------


def can_manage_offices(actor: User) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    return has_effective_permission(actor, MANAGE_PERMISSION)


def managed_office_queryset(actor: User) -> QuerySet[Office]:
    queryset = Office.visible_queryset()
    return scope_queryset_for_offices(actor, queryset)


def ensure_manage_authority(actor: User, office: Office | None = None) -> None:
    if not can_manage_offices(actor):
        _log_denial(actor, office, reason="missing_permission")
        raise PermissionDenied(_("You do not have permission to manage offices."))
    if (
        office is not None
        and not managed_office_queryset(actor).filter(pk=office.pk).exists()
    ):
        _log_denial(actor, office, reason="out_of_scope")
        raise PermissionDenied(_("That office is outside your administrative scope."))


def company_wide(actor: User) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    return get_effective_access(actor).company_wide


def office_version(office: Office) -> str:
    updated = office.updated_at
    stamp = updated.isoformat(timespec="microseconds")
    return f"{office.pk}:{stamp}"


def _log_denial(actor: User, office: Office | None, *, reason: str) -> None:
    log_event(
        "security.office_administration.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=Office._meta.label_lower,
            target_id=str(getattr(office, "pk", "") or ""),
            target_label=getattr(office, "stable_key", "") or "",
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def _office_target(office: Office) -> AuditTarget:
    return AuditTarget(
        target_type=Office._meta.label_lower,
        target_id=str(office.pk),
        target_label=office.stable_key,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OfficeListFilters:
    q: str = ""
    kind: str = ""
    status: str = ""  # active | inactive | ""
    region: str = ""

    def as_payload(self) -> dict[str, str]:
        return {
            "q": self.q,
            "kind": self.kind,
            "status": self.status,
            "region": self.region,
        }


def parse_list_filters(params) -> OfficeListFilters:
    kind = (params.get("kind") or "").strip()
    if kind and kind not in Office.Kind.values:
        kind = ""
    status = (params.get("status") or "").strip()
    if status not in {"", "active", "inactive"}:
        status = ""
    return OfficeListFilters(
        q=(params.get("q") or "").strip()[:120],
        kind=kind,
        status=status,
        region=(params.get("region") or "").strip()[:80],
    )


def build_office_list(
    actor: User, *, filters: OfficeListFilters, page: int = 1
) -> dict[str, Any]:
    ensure_manage_authority(actor)
    queryset = managed_office_queryset(actor)
    if filters.q:
        queryset = queryset.filter(
            Q(name__icontains=filters.q)
            | Q(slug__icontains=filters.q)
            | Q(stable_key__icontains=filters.q)
            | Q(city__icontains=filters.q)
        )
    if filters.kind:
        queryset = queryset.filter(kind=filters.kind)
    if filters.status == "active":
        queryset = queryset.filter(is_active=True)
    elif filters.status == "inactive":
        queryset = queryset.filter(is_active=False)
    if filters.region:
        queryset = queryset.filter(
            Q(region__stable_key=filters.region) | Q(stable_key=filters.region)
        )

    total = queryset.count()
    page = max(1, page)
    start = (page - 1) * PAGE_SIZE
    rows = [
        {
            "id": office.pk,
            "name": office.name,
            "stableKey": office.stable_key,
            "slug": office.slug,
            "kind": office.kind,
            "kindLabel": Office.Kind(office.kind).label,
            "pathLabel": office.path_label(),
            "regionName": office.region_name(),
            "isActive": office.is_active,
            "isAssignable": office.is_assignable,
            "city": office.city,
            "state": office.state,
        }
        for office in queryset[start : start + PAGE_SIZE]
    ]
    return {
        "offices": list_response(
            rows,
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters.as_payload(),
        ),
        "filterOptions": {
            "kinds": [
                {"value": value, "label": label} for value, label in Office.Kind.choices
            ],
            "statuses": [
                {"value": "active", "label": "Active"},
                {"value": "inactive", "label": "Inactive"},
            ],
            "regions": _region_filter_options(actor),
        },
        "capabilities": {
            "companyWide": company_wide(actor),
            "canRestructure": company_wide(actor),
        },
    }


def _region_filter_options(actor: User) -> list[dict[str, str]]:
    regions = (
        managed_office_queryset(actor)
        .filter(kind=Office.Kind.REGION)
        .order_by("sort_order", "name")
    )
    return [{"value": region.stable_key, "label": region.name} for region in regions]


# ---------------------------------------------------------------------------
# Detail payload
# ---------------------------------------------------------------------------


def detail_payload(actor: User, office: Office) -> dict[str, Any]:
    ensure_manage_authority(actor, office)
    is_company = company_wide(actor)
    contacts = [
        _contact_row(assignment)
        for assignment in OfficeContactAssignment.objects.filter(office=office)
        .select_related("user")
        .order_by("assignment_type", "-is_primary", "user__email")
    ]
    return {
        "office": {
            "id": office.pk,
            "name": office.name,
            "stableKey": office.stable_key,
            "slug": office.slug,
            "kind": office.kind,
            "kindLabel": Office.Kind(office.kind).label,
            "pathLabel": office.path_label(),
            "regionName": office.region_name(),
            "parentId": office.parent.pk if office.parent else None,
            "parentPathLabel": office.parent.path_label() if office.parent else None,
            "isActive": office.is_active,
            "isAssignable": office.is_assignable,
            "streetAddress": office.street_address,
            "city": office.city,
            "state": office.state,
            "zipCode": office.zip_code,
            "mainPhone": office.main_phone,
            "publicEmail": office.public_email,
            "internalEmail": office.internal_email,
            "officeHours": office.office_hours or [],
            "officeHoursText": _hours_to_text(office.office_hours),
            "parkingInstructions": office.parking_instructions,
            "accessInstructions": office.access_instructions,
            "accessInstructionsInternal": office.access_instructions_internal,
            "updatedAt": office.updated_at.isoformat(),
        },
        "contacts": contacts,
        "contactTypes": [
            {"value": value, "label": label}
            for value, label in OfficeContactAssignment.AssignmentType.choices
        ],
        "contactCandidates": _contact_candidates(office),
        "version": office_version(office),
        "capabilities": {
            "companyWide": is_company,
            "canEditInfo": True,
            "canEditSensitive": True,
            "canRestructure": is_company,
            "highImpactFields": sorted(HIGH_IMPACT_FIELDS) if is_company else [],
        },
        "parentOptions": _parent_options(actor, office) if is_company else [],
        "kindOptions": [
            {"value": value, "label": label} for value, label in Office.Kind.choices
        ],
        "resourceLinks": resource_links(office),
        "agentPreview": office_info_payload(office, include_internal=True),
        "breadcrumbs": [
            {"name": node.name, "id": node.pk} for node in _ancestors_inclusive(office)
        ],
    }


def _ancestors_inclusive(office: Office) -> list[Office]:
    nodes: list[Office] = []
    node: Office | None = office
    seen: set[int] = set()
    while node is not None and node.pk not in seen:
        seen.add(node.pk)
        nodes.append(node)
        node = node.parent
    nodes.reverse()
    return nodes


def _contact_row(assignment: OfficeContactAssignment) -> dict[str, Any]:
    user = assignment.user
    return {
        "id": assignment.pk,
        "assignmentType": assignment.assignment_type,
        "assignmentTypeLabel": OfficeContactAssignment.AssignmentType(
            assignment.assignment_type
        ).label,
        "userId": user.pk,
        "displayName": user.get_full_name() or user.display_name or user.email,
        "email": user.email,
        "isPrimary": assignment.is_primary,
        "startsAt": assignment.starts_at.isoformat() if assignment.starts_at else "",
        "endsAt": assignment.ends_at.isoformat() if assignment.ends_at else "",
        "isCurrent": assignment.is_current(),
    }


def _contact_candidates(office: Office) -> list[dict[str, Any]]:
    users = User.objects.filter(office=office, is_active=True).order_by(
        "first_name", "last_name", "email"
    )[:200]
    return [
        {
            "id": user.pk,
            "displayName": user.get_full_name() or user.display_name or user.email,
            "email": user.email,
        }
        for user in users
    ]


def _parent_options(actor: User, office: Office) -> list[dict[str, Any]]:
    """Valid parents for a potential reparent (excludes self and descendants)."""
    blocked = set(descendant_queryset(office).values_list("pk", flat=True))
    blocked.add(office.pk)
    queryset = managed_office_queryset(actor).exclude(pk__in=blocked)
    return [
        {
            **office_selector_payload(candidate),
            "pathLabel": candidate.path_label(),
            "kind": candidate.kind,
        }
        for candidate in queryset.order_by("sort_order", "name")[:500]
    ]


def _hours_to_text(hours: Any) -> str:
    if not hours:
        return ""
    if isinstance(hours, list):
        lines: list[str] = []
        for entry in hours:
            if isinstance(entry, str):
                lines.append(entry)
            elif isinstance(entry, dict):
                lines.append(json.dumps(entry, sort_keys=True))
            else:
                lines.append(str(entry))
        return "\n".join(lines)
    return str(hours)


def _hours_from_text(text: str) -> list[Any]:
    raw = (text or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                {"office_hours": _("Enter valid JSON or one hour line per row.")}
            ) from exc
        if not isinstance(parsed, list):
            raise ValidationError(
                {"office_hours": _("Office hours JSON must be a list.")}
            )
        return parsed
    return [line.strip() for line in raw.splitlines() if line.strip()]


def resource_links(office: Office) -> list[dict[str, Any]]:
    """Scoped deep-links to related modules (live or Coming Soon)."""
    office_q = urlencode({"office": office.stable_key})
    links = [
        {
            "key": "users",
            "label": "Users",
            "description": "People assigned to this office",
            "href": f"{reverse('admin_users')}?{office_q}",
            "available": OPERATIONS_FEATURES.get("admin-users", False),
        },
        {
            "key": "new-agents",
            "label": "New Agent List",
            "description": "Onboarding cases in this office",
            "href": f"{reverse('admin_new_agents')}?{office_q}",
            "available": OPERATIONS_FEATURES.get("admin-new-agents", False),
        },
        {
            "key": "inventory",
            "label": "Inventory",
            "description": "Office-scoped inventory",
            "href": reverse("admin_inventory"),
            "available": OPERATIONS_FEATURES.get("admin-inventory", False),
        },
        {
            "key": "reservations",
            "label": "Reservations",
            "description": "Rooms and reservations",
            "href": reverse("admin_reservations"),
            "available": OPERATIONS_FEATURES.get("admin-reservations", False),
        },
        {
            "key": "announcements",
            "label": "Announcements",
            "description": "Office publications",
            "href": reverse("admin_announcements"),
            "available": OPERATIONS_FEATURES.get("admin-announcements", False),
        },
        {
            "key": "documents",
            "label": "Documents & forms",
            "description": "Document library",
            "href": reverse("admin_documents"),
            "available": OPERATIONS_FEATURES.get("admin-documents", False),
        },
        {
            "key": "office-info",
            "label": "Agent Office Info",
            "description": "Preview the agent-facing page for this office",
            "href": reverse("office_info"),
            "available": True,
            "note": (
                "Agents always see their own primary office; this link opens yours."
            ),
        },
    ]
    return links


# ---------------------------------------------------------------------------
# Impact analysis
# ---------------------------------------------------------------------------


def analyze_impact(
    office: Office,
    *,
    parent: Office | None = None,
    kind: str | None = None,
    is_active: bool | None = None,
    is_assignable: bool | None = None,
) -> list[dict[str, str]]:
    """Describe who/what a high-impact change would affect (no writes)."""
    impact: list[dict[str, str]] = []
    primary_members = User.objects.filter(office=office, is_active=True).count()
    memberships = UserOfficeMembership.objects.filter(
        office=office,
        status=UserOfficeMembership.Status.ACTIVE,
    ).count()
    role_grants = UserRoleAssignment.objects.filter(
        scope_office=office,
        status=UserRoleAssignment.Status.ACTIVE,
    ).count()
    contacts = OfficeContactAssignment.current_queryset(office).count()
    descendants = descendant_queryset(office).exclude(pk=office.pk)
    active_children = descendants.filter(is_active=True).count()

    if is_active is not None and is_active != office.is_active:
        impact.append(
            {
                "label": "Active status",
                "from": "Active" if office.is_active else "Inactive",
                "to": "Active" if is_active else "Inactive",
                "impact": (
                    f"{primary_members} primary user(s), {memberships} membership(s), "
                    f"{role_grants} role grant(s), and {contacts} current contact(s) "
                    f"reference this office. "
                    + (
                        f"{active_children} active descendant office(s) remain."
                        if not is_active and active_children
                        else ""
                    )
                ).strip(),
            }
        )
    if is_assignable is not None and is_assignable != office.is_assignable:
        impact.append(
            {
                "label": "Assignable",
                "from": "Yes" if office.is_assignable else "No",
                "to": "Yes" if is_assignable else "No",
                "impact": (
                    "Controls whether agents can pick this office as a workplace."
                ),
            }
        )
    if kind is not None and kind != office.kind:
        impact.append(
            {
                "label": "Kind",
                "from": Office.Kind(office.kind).label,
                "to": Office.Kind(kind).label if kind in Office.Kind.values else kind,
                "impact": (
                    "Changes where this node may sit in the tree and which "
                    "parent kinds are valid."
                ),
            }
        )
    if parent is not None and (office.parent is None or parent.pk != office.parent.pk):
        impact.append(
            {
                "label": "Parent",
                "from": office.parent.path_label() if office.parent else "—",
                "to": parent.path_label(),
                "impact": (
                    f"Moves this office and refreshes region denormalization on "
                    f"{descendants.count()} descendant node(s). "
                    f"{primary_members} primary user(s) stay attached to this office."
                ),
            }
        )
    return impact


def preview_high_impact(
    *,
    actor: User,
    office: Office,
    parent: Office | None = None,
    kind: str | None = None,
    is_active: bool | None = None,
    is_assignable: bool | None = None,
) -> dict[str, Any]:
    ensure_manage_authority(actor, office)
    if not company_wide(actor):
        raise PermissionDenied(
            _("Only brokerage administrators can change hierarchy or status.")
        )
    impact = analyze_impact(
        office,
        parent=parent,
        kind=kind,
        is_active=is_active,
        is_assignable=is_assignable,
    )
    return {
        "highImpact": impact,
        "requiresConfirmation": bool(impact),
        "version": office_version(office),
    }


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def normalize_info_values(cleaned: dict[str, Any]) -> dict[str, Any]:
    values = dict(cleaned)
    if "zip_code" in values and values["zip_code"]:
        values["zip_code"] = normalize_us_zip(values["zip_code"])
    if "main_phone" in values and values["main_phone"]:
        values["main_phone"] = normalize_us_phone(values["main_phone"])
    if "office_hours_text" in values:
        values["office_hours"] = _hours_from_text(values.pop("office_hours_text"))
    if "stable_key" in values:
        raise ValidationError(
            {"stable_key": _("Stable identity cannot be changed once created.")}
        )
    return values


@transaction.atomic
def update_office_info(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    expected_version: str,
) -> Office:
    ensure_manage_authority(actor, office)
    locked = (
        Office.objects.select_for_update(of=("self",))
        .select_related("parent", "region")
        .get(pk=office.pk)
    )
    if office_version(locked) != (expected_version or ""):
        raise StaleOfficeVersion()

    values = normalize_info_values(cleaned)
    before = _info_snapshot(locked)
    for field in EDITABLE_IN_SCOPE:
        if field in values:
            setattr(locked, field, values[field])
    locked.full_clean()
    locked.save()
    after = _info_snapshot(locked)
    if before != after:
        log_event(
            "office.updated",
            actor=actor_from_user(actor),
            target=_office_target(locked),
            before=before,
            after=after,
            office_id=locked.stable_key,
            region_id=locked.region.stable_key if locked.region else "",
        )
    return locked


@transaction.atomic
def update_office_structure(
    *,
    actor: User,
    office: Office,
    cleaned: dict[str, Any],
    expected_version: str,
    confirmed: bool = False,
) -> Office:
    ensure_manage_authority(actor, office)
    if not company_wide(actor):
        _log_denial(actor, office, reason="not_company_wide")
        raise PermissionDenied(
            _("Only brokerage administrators can change hierarchy or status.")
        )

    locked = (
        Office.objects.select_for_update(of=("self",))
        .select_related("parent", "region")
        .get(pk=office.pk)
    )
    if office_version(locked) != (expected_version or ""):
        raise StaleOfficeVersion()

    parent = cleaned.get("parent", locked.parent)
    kind = cleaned.get("kind", locked.kind)
    is_active = cleaned.get("is_active", locked.is_active)
    is_assignable = cleaned.get("is_assignable", locked.is_assignable)

    impact = analyze_impact(
        locked,
        parent=parent if parent is not None else locked.parent,
        kind=kind,
        is_active=is_active,
        is_assignable=is_assignable,
    )
    if impact and not confirmed:
        raise ConfirmationRequired(impact)

    parent_changed = parent is not None and (
        locked.parent is None or parent.pk != locked.parent.pk
    )
    if parent_changed:
        # transfer_office re-locks and audits the move.
        locked = transfer_office(actor=actor, office=locked, new_parent=parent)
        locked = (
            Office.objects.select_for_update(of=("self",))
            .select_related("parent", "region")
            .get(pk=locked.pk)
        )

    before = {
        "kind": locked.kind,
        "is_active": locked.is_active,
        "is_assignable": locked.is_assignable,
    }
    changed = False
    if kind != locked.kind:
        locked.kind = kind
        changed = True
    if is_active != locked.is_active:
        locked.is_active = is_active
        changed = True
    if is_assignable != locked.is_assignable:
        locked.is_assignable = is_assignable
        changed = True
    if changed:
        locked.full_clean()
        locked.save()
        after = {
            "kind": locked.kind,
            "is_active": locked.is_active,
            "is_assignable": locked.is_assignable,
        }
        action = (
            "office.deactivated"
            if before["is_active"] and not after["is_active"]
            else "office.updated"
        )
        log_event(
            action,
            actor=actor_from_user(actor),
            target=_office_target(locked),
            before=before,
            after=after,
            office_id=locked.stable_key,
            region_id=locked.region.stable_key if locked.region else "",
            metadata={"impact": impact},
        )
    return locked


def _info_snapshot(office: Office) -> dict[str, Any]:
    return {field: getattr(office, field) for field in EDITABLE_IN_SCOPE}


@transaction.atomic
def upsert_contact(
    *,
    actor: User,
    office: Office,
    user: User,
    assignment_type: str,
    is_primary: bool = False,
    starts_at: date | None = None,
    ends_at: date | None = None,
    expected_version: str,
    assignment_id: int | None = None,
) -> OfficeContactAssignment:
    ensure_manage_authority(actor, office)
    locked_office = Office.objects.select_for_update(of=("self",)).get(pk=office.pk)
    if office_version(locked_office) != (expected_version or ""):
        raise StaleOfficeVersion()

    if assignment_type not in CONTACT_TYPES:
        raise ValidationError(
            {"assignment_type": _("Unknown contact assignment type.")}
        )
    if user.office is None or user.office.pk != locked_office.pk:
        raise ValidationError(
            {"user": _("Assigned staff must belong to the same office.")}
        )

    if assignment_id:
        assignment = OfficeContactAssignment.objects.select_for_update().get(
            pk=assignment_id, office=locked_office
        )
        before = _contact_snapshot(assignment)
    else:
        existing = OfficeContactAssignment.objects.filter(
            office=locked_office, user=user, assignment_type=assignment_type
        ).first()
        if existing:
            assignment = OfficeContactAssignment.objects.select_for_update().get(
                pk=existing.pk
            )
            before = _contact_snapshot(assignment)
        else:
            assignment = OfficeContactAssignment(office=locked_office)
            before = None

    if is_primary:
        OfficeContactAssignment.objects.filter(
            office=locked_office,
            assignment_type=assignment_type,
            is_primary=True,
        ).exclude(pk=assignment.pk or 0).update(is_primary=False)

    assignment.user = user
    assignment.assignment_type = assignment_type
    assignment.is_primary = is_primary
    assignment.starts_at = starts_at
    assignment.ends_at = ends_at
    assignment.full_clean()
    assignment.save()

    after = _contact_snapshot(assignment)
    log_event(
        "office.contact.updated" if before else "office.contact.created",
        actor=actor_from_user(actor),
        target=_office_target(locked_office),
        before=before,
        after=after,
        office_id=locked_office.stable_key,
        region_id=locked_office.region.stable_key if locked_office.region else "",
    )
    # Bump office.updated_at so the concurrency token advances with contacts.
    locked_office.save(update_fields=["updated_at"])
    return assignment


@transaction.atomic
def end_contact(
    *,
    actor: User,
    office: Office,
    assignment_id: int,
    expected_version: str,
    ends_at: date | None = None,
) -> OfficeContactAssignment:
    ensure_manage_authority(actor, office)
    locked_office = Office.objects.select_for_update(of=("self",)).get(pk=office.pk)
    if office_version(locked_office) != (expected_version or ""):
        raise StaleOfficeVersion()
    assignment = OfficeContactAssignment.objects.select_for_update().get(
        pk=assignment_id, office=locked_office
    )
    before = _contact_snapshot(assignment)
    assignment.ends_at = ends_at or timezone.localdate()
    if (
        assignment.starts_at
        and assignment.ends_at
        and assignment.ends_at < assignment.starts_at
    ):
        raise ValidationError(
            {"ends_at": _("End date cannot be earlier than the start date.")}
        )
    assignment.full_clean()
    assignment.save()
    log_event(
        "office.contact.ended",
        actor=actor_from_user(actor),
        target=_office_target(locked_office),
        before=before,
        after=_contact_snapshot(assignment),
        office_id=locked_office.stable_key,
        region_id=locked_office.region.stable_key if locked_office.region else "",
    )
    locked_office.save(update_fields=["updated_at"])
    return assignment


def _contact_snapshot(assignment: OfficeContactAssignment) -> dict[str, Any]:
    return {
        "id": assignment.pk,
        "user_id": assignment.user.pk,
        "assignment_type": assignment.assignment_type,
        "is_primary": assignment.is_primary,
        "starts_at": assignment.starts_at.isoformat() if assignment.starts_at else None,
        "ends_at": assignment.ends_at.isoformat() if assignment.ends_at else None,
    }


def administration_page_props(actor: User, office: Office) -> dict[str, Any]:
    return {
        "administration": detail_payload(actor, office),
        "scope": operations_scope_payload(actor),
    }
