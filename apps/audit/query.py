from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from apps.audit.models import AuditEvent
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)


def _scoped_queryset(user):
    if getattr(user, "is_superuser", False):
        return AuditEvent.objects.all()
    if not has_effective_permission(user, "audit.can_view_audit_events"):
        raise PermissionDenied("You do not have permission to view audit events.")

    access = get_effective_access(user)
    qs = AuditEvent.objects.all()
    if access.company_wide:
        return qs
    filters = Q()
    if access.region_keys:
        filters |= Q(region_id__in=sorted(access.region_keys))
    if access.office_keys:
        filters |= Q(office_id__in=sorted(access.office_keys))
    if not filters:
        filters = Q(actor_id=str(user.pk))
    return qs.filter(filters)


def query_audit_events(user, *, limit: int = 100):
    return _scoped_queryset(user).order_by("-occurred_at", "-recorded_at")[:limit]


def export_audit_events(user, *, limit: int = 100):
    if not (
        getattr(user, "is_superuser", False)
        or has_effective_permission(user, "audit.can_export_audit_events")
    ):
        raise PermissionDenied("You do not have permission to export audit events.")
    return [
        {
            "id": str(event.id),
            "occurredAt": event.occurred_at.isoformat(),
            "recordedAt": event.recorded_at.isoformat(),
            "action": event.action,
            "outcome": event.outcome,
            "actor": {
                "type": event.actor_type,
                "id": event.actor_id,
                "label": event.actor_label,
            },
            "target": {
                "type": event.target_type,
                "id": event.target_id,
                "label": event.target_label,
            },
            "source": event.source,
            "channel": event.channel,
            "requestId": event.request_id,
            "organizationId": event.organization_id,
            "officeId": event.office_id,
            "regionId": event.region_id,
            "reason": event.reason,
            "changes": event.changes,
        }
        for event in query_audit_events(user, limit=limit)
    ]
