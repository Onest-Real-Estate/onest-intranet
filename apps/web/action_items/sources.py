"""Profile-backed action items.

Completion is derived from the user record: missing optional professional
fields and an expired or soon-to-expire licence surface here; filling them on
``/profile`` (which re-checks authentication) clears the item on the next
load. The dashboard never stores a second completion flag.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.urls import reverse
from django.utils import timezone

from apps.user.services.profile import profile_completeness
from apps.web.action_items.contract import (
    ActionItem,
    ActionPriority,
    ActionSourceContext,
    ActionType,
)

#: Surface a licence that expires inside this window as actionable, not just
#: one that has already lapsed.
LICENSE_WARNING_DAYS = 30


def _at_start_of_day(day, *, tz) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min), tz)


def _at_end_of_day(day, *, tz) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.max), tz)


def collect_profile_actions(context: ActionSourceContext) -> list[ActionItem]:
    user = context.user
    tz = timezone.get_current_timezone()
    items: list[ActionItem] = []
    completeness = profile_completeness(user)
    missing = completeness["missing"]
    if missing:
        labels = [field["label"] for field in missing[:3]]
        remainder = len(missing) - len(labels)
        if remainder > 0:
            labels.append(f"and {remainder} more")
        items.append(
            ActionItem(
                id=f"profile:incomplete:{user.pk}",
                dedupe_key=f"profile:incomplete:{user.pk}",
                title="Complete your profile",
                type=ActionType.PROFILE,
                priority=ActionPriority.NORMAL,
                due_at=None,
                source_module="profile",
                source_record_type="user",
                source_record_id=str(user.pk),
                context=", ".join(labels),
                cta_label="Update profile",
                cta_href=reverse("profile"),
                assignee_id=user.pk,
            )
        )

    expires_on = user.license_expires_on
    if expires_on is not None:
        today = timezone.localtime(context.now, tz).date()
        warning_end = today + timedelta(days=LICENSE_WARNING_DAYS)
        if expires_on < today:
            items.append(
                ActionItem(
                    id=f"profile:license_expired:{user.pk}",
                    dedupe_key=f"profile:license:{user.pk}",
                    title="Real-estate license expired",
                    type=ActionType.COMPLIANCE,
                    priority=ActionPriority.CRITICAL,
                    due_at=_at_start_of_day(expires_on, tz=tz),
                    source_module="profile",
                    source_record_type="user",
                    source_record_id=str(user.pk),
                    context=f"Expired {expires_on.isoformat()}",
                    cta_label="Update credentials",
                    cta_href=reverse("profile"),
                    assignee_id=user.pk,
                )
            )
        elif expires_on <= warning_end:
            items.append(
                ActionItem(
                    id=f"profile:license_expiring:{user.pk}",
                    dedupe_key=f"profile:license:{user.pk}",
                    title="Real-estate license expiring soon",
                    type=ActionType.COMPLIANCE,
                    priority=ActionPriority.HIGH,
                    due_at=_at_end_of_day(expires_on, tz=tz),
                    source_module="profile",
                    source_record_type="user",
                    source_record_id=str(user.pk),
                    context=f"Expires {expires_on.isoformat()}",
                    cta_label="Update credentials",
                    cta_href=reverse("profile"),
                    assignee_id=user.pk,
                )
            )
    return items
