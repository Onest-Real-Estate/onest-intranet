"""Dashboard action items for mandatory policy acknowledgements."""

from __future__ import annotations

from django.urls import reverse

from apps.compliance.acknowledgements import open_requirements_for

_MAX_ROWS = 50


def collect_compliance_actions(context):
    from apps.web.action_items.contract import (
        ActionItem,
        ActionPriority,
        ActionType,
    )

    user = context.user
    if getattr(user, "is_anonymous", False):
        return []
    items: list[ActionItem] = []
    moment = context.now
    for requirement in open_requirements_for(user, now=moment)[:_MAX_ROWS]:
        version = requirement.policy_version
        overdue = bool(requirement.due_at and requirement.due_at < moment)
        items.append(
            ActionItem(
                id=f"policy_ack:{version.pk}:{user.pk}",
                dedupe_key=f"policy_ack:{version.pk}:{user.pk}",
                title=f"Acknowledge: {version.title}",
                type=ActionType.COMPLIANCE,
                priority=ActionPriority.CRITICAL if overdue else ActionPriority.HIGH,
                due_at=requirement.due_at,
                source_module="compliance",
                source_record_type="policy_version",
                source_record_id=str(version.pk),
                context=(
                    "Mandatory policy acknowledgement is overdue"
                    if overdue
                    else "Mandatory policy acknowledgement is due"
                ),
                cta_label="Open policy",
                cta_href=reverse("policy_detail", args=[version.pk]),
                assignee_id=user.pk,
            )
        )
    return items
