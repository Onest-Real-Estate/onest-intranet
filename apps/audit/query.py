from __future__ import annotations

from django.core.exceptions import PermissionDenied

from apps.audit.models import AuditEvent
from apps.user.roles import ADMIN, BRANCH_MANAGER, REGION_MANAGER, ordered_role_names


def _scoped_queryset(user):
    if getattr(user, "is_superuser", False):
        return AuditEvent.objects.all()
    if not user.has_perm("audit.can_view_audit_events"):
        raise PermissionDenied("You do not have permission to view audit events.")

    roles = set(ordered_role_names(user))
    qs = AuditEvent.objects.all()
    if ADMIN in roles:
        return qs

    office = getattr(user, "office", None)
    if office is None:
        return qs.none()
    if REGION_MANAGER in roles and office.region is not None:
        return qs.filter(region_id=office.region.stable_key)
    if BRANCH_MANAGER in roles:
        return qs.filter(office_id=office.stable_key)
    return qs.filter(actor_id=str(user.pk))


def query_audit_events(user, *, limit: int = 100):
    return _scoped_queryset(user).order_by("-occurred_at", "-recorded_at")[:limit]


def export_audit_events(user, *, limit: int = 100):
    if not (
        getattr(user, "is_superuser", False)
        or user.has_perm("audit.can_export_audit_events")
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
