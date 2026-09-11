"""Dashboard action items for overdue mandatory policy acknowledgements."""

from __future__ import annotations

from django.urls import reverse

from apps.compliance.acknowledgements import overdue_requirements_for
from apps.web.action_items.contract import (
    ActionItem,
    ActionPriority,
    ActionSourceContext,
    ActionType,
)

_MAX_ROWS = 50


def collect_compliance_actions(context: ActionSourceContext) -> list[ActionItem]:
    user = context.user
    if getattr(user, "is_anonymous", False):
        return []
    items: list[ActionItem] = []
    for requirement in overdue_requirements_for(user, now=context.now)[:_MAX_ROWS]:
        version = requirement.policy_version
        items.append(
            ActionItem(
                id=f"policy_ack:{version.pk}:{user.pk}",
                dedupe_key=f"policy_ack:{version.pk}:{user.pk}",
                title=f"Acknowledge: {version.title}",
                type=ActionType.COMPLIANCE,
                priority=ActionPriority.HIGH,
                due_at=requirement.due_at,
                source_module="compliance",
                source_record_type="policy_version",
                source_record_id=str(version.pk),
                context="Mandatory policy acknowledgement is overdue",
                cta_label="Open policy",
                cta_href=reverse("policy_detail", args=[version.pk]),
                assignee_id=user.pk,
            )
        )
    return items
