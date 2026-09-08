"""Permission-aware activity timeline projection over append-only audit events.

User-facing timelines project :class:`~apps.audit.models.AuditEvent` rows.
Timeline access (``audit.can_view_activity_timeline``) is distinct from raw
audit-log access (``audit.can_view_audit_events``).
"""

from apps.audit.activity.contract import ActivityEntry, ActivityPage, ActivityRecordRef
from apps.audit.activity.projection import (
    project_record_activity,
    project_user_administration_history,
)

__all__ = [
    "ActivityEntry",
    "ActivityPage",
    "ActivityRecordRef",
    "project_record_activity",
    "project_user_administration_history",
]
