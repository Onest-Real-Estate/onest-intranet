"""Project authorized activity timelines from append-only audit events."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.audit.activity.access import (
    RecordTypeConfig,
    assert_can_view_record_activity,
)
from apps.audit.activity.contract import ActivityEntry, ActivityPage
from apps.audit.activity.cursor import ActivityCursorError, decode_cursor, encode_cursor
from apps.audit.activity.mappers import (
    USER_MAPPER,
    application_timezone,
    map_event,
    mapper_for,
)
from apps.audit.models import AuditEvent
from apps.user.models import User
from apps.user.services.role_assignments import get_effective_access

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class ActivityProjectionError(ValueError):
    """Invalid projection request (cursor, limit, etc.)."""


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise ActivityProjectionError("Limit must be an integer.") from exc
    if value < 1:
        raise ActivityProjectionError("Limit must be at least 1.")
    return min(value, MAX_LIMIT)


def _base_queryset(config: RecordTypeConfig, record_id: str) -> QuerySet[AuditEvent]:
    """Events whose primary target is exactly this record — no cross-record bleed."""
    return AuditEvent.objects.filter(
        target_type__in=config.target_types,
        target_id=str(record_id),
    )


def _apply_viewer_scope(qs: QuerySet[AuditEvent], viewer: User) -> QuerySet[AuditEvent]:
    if getattr(viewer, "is_superuser", False):
        return qs
    access = get_effective_access(viewer)
    if access.company_wide:
        return qs
    filters = Q()
    if access.region_keys:
        filters |= Q(region_id__in=sorted(access.region_keys))
    if access.office_keys:
        filters |= Q(office_id__in=sorted(access.office_keys))
    if filters:
        filters |= Q(office_id="", region_id="")
        qs = qs.filter(filters)
    return qs


def _apply_cursor(qs: QuerySet[AuditEvent], cursor: str | None) -> QuerySet[AuditEvent]:
    if not cursor:
        return qs
    try:
        occurred_at, event_id = decode_cursor(cursor)
    except ActivityCursorError as exc:
        raise ActivityProjectionError(str(exc)) from exc
    return qs.filter(
        Q(occurred_at__lt=occurred_at) | Q(occurred_at=occurred_at, id__lt=event_id)
    )


def project_record_activity(
    viewer: User,
    record_type: str,
    record_id: str,
    *,
    cursor: str | None = None,
    limit: int | None = None,
    require_timeline_permission: bool = True,
) -> ActivityPage:
    """Return a cursor page of authorized, deduplicated timeline entries.

    Dedup is by audit event PK: domain-event replay does not insert a second
    ``AuditEvent``, so the timeline cannot double-list the same row. Order is
    ``-occurred_at, -id``.
    """
    config = assert_can_view_record_activity(
        viewer,
        record_type,
        record_id,
        require_timeline_permission=require_timeline_permission,
    )
    page_size = _clamp_limit(limit)
    mapper = mapper_for(record_type)

    qs = _base_queryset(config, record_id)
    qs = _apply_viewer_scope(qs, viewer)
    qs = _apply_cursor(qs, cursor)
    qs = qs.order_by("-occurred_at", "-id")

    rows = list(qs[: page_size + 1])
    has_more = len(rows) > page_size
    rows = rows[:page_size]

    entries: list[ActivityEntry] = []
    seen_ids: set[str] = set()
    for event in rows:
        event_id = str(event.id)
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        entries.append(
            map_event(
                event,
                viewer=viewer,
                record_type=record_type,
                record_id=str(record_id),
                mapper=mapper,
            )
        )

    next_cursor = None
    if has_more and rows:
        last_event = rows[-1]
        next_cursor = encode_cursor(
            occurred_at=last_event.occurred_at,
            event_id=last_event.id,
        )

    return ActivityPage(
        entries=tuple(entries),
        next_cursor=next_cursor,
        has_more=has_more,
        timezone=application_timezone(),
    )


def project_user_administration_history(
    viewer: User,
    target: User,
    *,
    limit: int = 8,
) -> list[dict]:
    """Compact history for the user-administration panel.

    Callers already enforced record access. Timeline permission is not
    re-checked so existing embeds keep working; the dedicated activity API
    still requires ``audit.can_view_activity_timeline``.
    """
    # Closed list historically rendered by administration_history.
    admin_actions = frozenset(USER_MAPPER.action_labels) & frozenset(
        {
            "user.administration.updated",
            "user.license_verification.reset",
            "user.account.disabled",
            "user.account.reactivated",
        }
    )
    page = project_record_activity(
        viewer,
        "user",
        str(target.pk),
        limit=max(limit * 3, 24),
        require_timeline_permission=False,
    )
    payload = []
    for entry in page.entries:
        if entry.event_type not in admin_actions:
            continue
        payload.append(
            {
                "id": entry.id,
                "action": entry.event_type,
                "label": entry.summary.split(" (")[0],
                "occurredAt": entry.occurred_at.isoformat(),
                "actor": entry.actor_label,
                "outcome": entry.outcome,
                "fields": list(entry.change_summary),
                "reason": entry.reason,
            }
        )
        if len(payload) >= limit:
            break
    return payload
