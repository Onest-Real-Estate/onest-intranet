"""Inertia props for the Quick Access administration pages.

Payload shaping only. Every queryset that reaches here has already been through
the actor's scope in ``administration``; nothing in this module widens one.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.user.models import Office, User
from apps.user.roles import ROLE_BY_KEY, ROLE_DEFINITIONS
from apps.web.capability import has_capability
from apps.web.contracts import empty_validation_errors, list_response
from apps.web.models import QuickAccessLink
from apps.web.quick_access.administration import (
    MANAGE_COMPANY_PERMISSION,
    ManagementContext,
    can_manage,
    link_version,
    manageable_link_queryset,
    management_context,
    targetable_office_queryset,
)
from apps.web.quick_access.catalog import icon_options, internal_destination_options
from apps.web.quick_access.resolution import explain_visibility, office_ancestor_ids

PAGE_SIZE = 10

STATUS_FILTERS = ("live", "scheduled", "inactive", "archived")


def _choice_options(choices) -> list[dict[str, str]]:
    return [{"value": value, "label": str(label)} for value, label in choices]


def lifecycle_status(link: QuickAccessLink, *, at=None) -> dict[str, str]:
    """One badge that answers "is this on the dashboard right now?".

    Deliberately not a raw field: ``is_active`` alone would show a link with a
    future publish date as live, which is the state administrators most often
    get wrong.
    """
    at = at or timezone.now()
    if link.is_archived:
        return {"value": "archived", "label": "Archived", "tone": "neutral"}
    if not link.is_active:
        return {"value": "inactive", "label": "Inactive", "tone": "neutral"}
    if link.publish_start_at and link.publish_start_at > at:
        return {"value": "scheduled", "label": "Scheduled", "tone": "info"}
    if link.publish_end_at and link.publish_end_at <= at:
        return {"value": "expired", "label": "Expired", "tone": "warning"}
    return {"value": "live", "label": "Live", "tone": "success"}


def _audience_summary(link: QuickAccessLink) -> dict[str, Any]:
    roles = [row.role_code for row in link.role_audiences.all()]
    offices = [
        {
            "id": row.office_id,
            "name": row.office.name,
            "stableKey": row.office.stable_key,
            "includeDescendants": row.include_descendants,
        }
        for row in link.office_audiences.all()
    ]
    return {
        "companyWide": link.company_wide,
        "roles": [
            {
                "code": code,
                "label": ROLE_BY_KEY[code].label if code in ROLE_BY_KEY else code,
            }
            for code in roles
        ],
        "offices": offices,
    }


def link_row(
    link: QuickAccessLink,
    *,
    actor: User,
    at=None,
    context: ManagementContext | None = None,
) -> dict[str, Any]:
    return {
        "id": link.pk,
        "stableKey": link.stable_key,
        "name": link.name,
        "description": link.description,
        "destinationType": link.destination_type,
        "destinationValue": link.destination_value,
        "href": link.href(),
        "icon": link.icon,
        "sortOrder": link.sort_order,
        "isActive": link.is_active,
        "isArchived": link.is_archived,
        "status": lifecycle_status(link, at=at),
        "publishStartAt": (
            link.publish_start_at.isoformat() if link.publish_start_at else None
        ),
        "publishEndAt": (
            link.publish_end_at.isoformat() if link.publish_end_at else None
        ),
        "ssoCapability": link.sso_capability,
        "integrationHealth": link.integration_health,
        "setupBehavior": link.setup_behavior,
        "ownerScope": link.owner_scope,
        "ownerOffice": link.owner_office.name if link.owner_office else None,
        "audience": _audience_summary(link),
        "canManage": can_manage(actor, link, context=context),
        "updatedAt": link.updated_at.isoformat() if link.updated_at else None,
        "version": link_version(link),
    }


def _filtered_queryset(
    actor: User, *, query: str, status: str, at, context: ManagementContext
):
    queryset = manageable_link_queryset(actor, context=context).prefetch_related(
        "role_audiences", "office_audiences__office"
    )
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(stable_key__icontains=query)
        )
    if status == "archived":
        queryset = queryset.filter(is_archived=True)
    else:
        queryset = queryset.filter(is_archived=False)
        if status == "inactive":
            queryset = queryset.filter(is_active=False)
        elif status == "scheduled":
            queryset = queryset.filter(is_active=True, publish_start_at__gt=at)
        elif status == "live":
            queryset = (
                queryset.filter(is_active=True)
                .exclude(publish_start_at__gt=at)
                .exclude(publish_end_at__lte=at)
            )
    return queryset.order_by("sort_order", "name", "pk")


def preview_payload(
    actor: User,
    *,
    role_code: str,
    office_id: int | None,
    at=None,
    context: ManagementContext | None = None,
) -> dict[str, Any] | None:
    """Effective visibility for one role in one office, with reasons.

    The office is supplied by the administrator, so it is resolved through
    their own targetable queryset: an id outside their scope produces no
    preview rather than a peek at somebody else's configuration.
    """
    if not role_code and office_id is None:
        return None
    at = at or timezone.now()
    resolved = management_context(actor) if context is None else context
    office: Office | None = None
    if office_id is not None:
        office = (
            targetable_office_queryset(actor, scope=resolved.scope)
            .filter(pk=office_id)
            .first()
        )
        if office is None:
            return {
                "roleCode": role_code,
                "officeId": None,
                "officeName": None,
                "outOfScope": True,
                "links": [],
            }
    roles = [role_code] if role_code else []
    ancestors = office_ancestor_ids(office)
    rows = []
    queryset = (
        manageable_link_queryset(actor, context=resolved)
        .filter(is_archived=False)
        .prefetch_related("role_audiences", "office_audiences")
        .order_by("sort_order", "name", "pk")
    )
    for link in queryset:
        reasons = explain_visibility(
            link,
            role_keys=roles,
            office=office,
            ancestor_ids=ancestors,
            at=at,
        )
        rows.append(
            {
                "id": link.pk,
                "name": link.name,
                "stableKey": link.stable_key,
                "visible": not reasons,
                "reasons": reasons,
            }
        )
    return {
        "roleCode": role_code,
        "officeId": office.pk if office else None,
        "officeName": office.name if office else None,
        "outOfScope": False,
        "links": rows,
    }


def index_props(
    actor: User,
    *,
    query: str = "",
    status: str = "",
    page: int = 1,
    preview_role: str = "",
    preview_office: int | None = None,
) -> dict[str, Any]:
    at = timezone.now()
    status = status if status in STATUS_FILTERS else ""
    # Resolved once for the page: every row would otherwise re-read the actor's
    # role assignments and re-walk the office tree.
    context = management_context(actor)
    scope = context.scope
    queryset = _filtered_queryset(
        actor, query=query, status=status, at=at, context=context
    )
    total = queryset.count()
    start = max(0, (max(page, 1) - 1) * PAGE_SIZE)
    rows = [
        link_row(link, actor=actor, at=at, context=context)
        for link in queryset[start : start + PAGE_SIZE]
    ]
    return {
        "links": list_response(
            rows,
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters={"q": query, "status": status},
            sort_key="sortOrder",
            sort_direction="asc",
        ),
        "statusOptions": [
            {"value": "live", "label": "Live"},
            {"value": "scheduled", "label": "Scheduled"},
            {"value": "inactive", "label": "Inactive"},
            {"value": "archived", "label": "Archived"},
        ],
        "roleOptions": [
            {"value": definition.code, "label": definition.label}
            for definition in ROLE_DEFINITIONS
        ],
        "officeOptions": [
            {"value": office.pk, "label": office.path_label()}
            for office in targetable_office_queryset(actor, scope=scope)[:200]
        ],
        "preview": preview_payload(
            actor,
            role_code=preview_role,
            office_id=preview_office,
            at=at,
            context=context,
        ),
        "capabilities": {
            "companyWide": has_capability(
                actor, MANAGE_COMPANY_PERMISSION, access=context.access
            ),
            "scopeLevel": "brokerage" if scope.company_wide else "scoped",
        },
    }


def form_props(
    actor: User,
    *,
    link: QuickAccessLink | None = None,
    errors: dict[str, Any] | None = None,
    posted: Any = None,
    pending_confirmation: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    context = management_context(actor)
    scope = context.scope
    return {
        "link": (
            link_row(link, actor=actor, context=context) if link is not None else None
        ),
        "errors": errors or empty_validation_errors(),
        "posted": {key: posted.getlist(key) for key in posted} if posted else None,
        "pendingConfirmation": pending_confirmation or [],
        "iconOptions": icon_options(),
        "internalDestinations": internal_destination_options(),
        "destinationTypeOptions": _choice_options(
            QuickAccessLink.DestinationType.choices
        ),
        "ssoOptions": _choice_options(QuickAccessLink.SsoCapability.choices),
        "healthOptions": _choice_options(QuickAccessLink.IntegrationHealth.choices),
        "setupOptions": _choice_options(QuickAccessLink.SetupBehavior.choices),
        "roleOptions": [
            {"value": definition.code, "label": definition.label}
            for definition in ROLE_DEFINITIONS
        ],
        "officeOptions": [
            {"value": office.pk, "label": office.path_label()}
            for office in targetable_office_queryset(actor, scope=scope)[:200]
        ],
        "capabilities": {
            "companyWide": has_capability(
                actor, MANAGE_COMPANY_PERMISSION, access=context.access
            ),
            "scopeLevel": "brokerage" if scope.company_wide else "scoped",
        },
    }
