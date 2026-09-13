"""Mapping domain events to in-app notifications.

Producers do not call the notification service directly. They publish the
domain event they were already publishing, and this registry turns it into
deliveries. Three things fall out of that:

* the side effect runs **after commit**, in the background, through the
  existing ``apps.audit`` dispatcher — a rolled-back transaction notifies
  nobody;
* it is **idempotent** twice over: ``EventDelivery`` skips an already-delivered
  consumer, and the ``(recipient, dedupe_key)`` constraint catches the rest;
* adding notifications to a workflow does not mean editing that workflow.

Adding a producer: register the event in ``apps/audit/catalog.py`` if it is
new, add a builder here, and ship a source resolver for its module (see
``apps/notifications/resolvers.py``) — without one the notification will list
with no detail and no action, by design.
"""

from __future__ import annotations

from collections.abc import Callable

from apps.audit.events import EventEnvelope
from apps.notifications.contract import (
    NotificationPriority,
    NotificationRequest,
    NotificationType,
)
from apps.notifications.resolvers import ONBOARDING_MODULE
from apps.onboarding_tools.models import ToolState
from apps.onboarding_tools.services import (
    INVITATION_EVENT,
    invitation_dedupe_key,
)
from apps.user.services.onboarding_office import (
    OFFICE_HANDOFF_EVENT,
    handoff_dedupe_key,
)


#: The event id is the idempotency key by default: a replay of the same event
#: is a no-op, while a genuine second occurrence (reassigned again, disabled
#: and reactivated again) is a new notification. Producers that instead want
#: repeated signals about one record to collapse into a single row should key
#: on that record's identity.
def _event_key(envelope: EventEnvelope) -> str:
    return f"{envelope.name}:{envelope.id}"


def _int_or_none(value: object) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number or None


def _nonnegative_int_or_none(value: object) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def onboarding_owner_assigned(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Tell the new owner that a case is now theirs.

    The agent's name is deliberately absent from the title: it is resolved
    from the onboarding record at read time, and disappears again if the
    owner's scope or grant changes.
    """
    owner_id = _int_or_none(envelope.payload.get("owner_id"))
    subject_id = _int_or_none(envelope.payload.get("user_id"))
    if owner_id is None or subject_id is None:
        return []
    return [
        NotificationRequest(
            recipient_id=owner_id,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key=envelope.name,
            title="An onboarding case was assigned to you",
            dedupe_key=_event_key(envelope),
            priority=NotificationPriority.HIGH,
            source_module=ONBOARDING_MODULE,
            source_record_type="user_onboarding_case",
            source_record_id=str(subject_id),
            action_key="open_onboarding_case",
            action_args=(subject_id,),
        )
    ]


def onboarding_office_handoff(
    envelope: EventEnvelope,
) -> list[NotificationRequest]:
    """Tell the resolved, scoped office administrator an agent is ready."""
    recipient_id = _int_or_none(envelope.payload.get("recipient_id"))
    user_id = _int_or_none(envelope.payload.get("user_id"))
    office_id = _int_or_none(envelope.payload.get("office_id"))
    onboarding_version = _nonnegative_int_or_none(
        envelope.payload.get("onboarding_version")
    )
    if (
        recipient_id is None
        or user_id is None
        or office_id is None
        or onboarding_version is None
    ):
        return []
    return [
        NotificationRequest(
            recipient_id=recipient_id,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key=OFFICE_HANDOFF_EVENT,
            title="A new agent is ready for office onboarding",
            dedupe_key=handoff_dedupe_key(
                user_id=user_id,
                onboarding_version=onboarding_version,
                office_id=office_id,
            ),
            priority=NotificationPriority.HIGH,
            is_mandatory=True,
            source_module=ONBOARDING_MODULE,
            source_record_type="user_onboarding_case",
            source_record_id=str(user_id),
            action_key="open_onboarding_case",
            action_args=(user_id,),
        )
    ]


def onboarding_tool_invitation_sent(
    envelope: EventEnvelope,
) -> list[NotificationRequest]:
    """Tell only the target agent that a catalog-tool invitation was recorded."""
    if envelope.payload.get("to") != ToolState.INVITATION_SENT:
        return []
    agent_id = _int_or_none(envelope.payload.get("agent_id"))
    onboarding_version = _nonnegative_int_or_none(
        envelope.payload.get("onboarding_version")
    )
    tool_slug = str(envelope.payload.get("tool") or "").strip()
    tool_name = str(envelope.payload.get("tool_name") or "").strip()
    if agent_id is None or onboarding_version is None or not tool_slug or not tool_name:
        return []
    return [
        NotificationRequest(
            recipient_id=agent_id,
            notification_type=NotificationType.ACCOUNT,
            event_key=INVITATION_EVENT,
            title=f"Your {tool_name} invitation was sent",
            dedupe_key=invitation_dedupe_key(
                agent_id=agent_id,
                onboarding_version=onboarding_version,
                tool_slug=tool_slug,
            ),
            priority=NotificationPriority.HIGH,
            is_mandatory=True,
            source_module="onboarding_tool",
            source_record_type="agent_tool_invitation",
            source_record_id=f"{agent_id}:{tool_slug}",
            action_key="open_onboarding_status",
        )
    ]


def account_reactivated(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Tell somebody their account is usable again.

    Deactivation notifies nobody: the account it concerns can no longer sign
    in to read it, and the people who need to know are told by the workflow
    that disabled it.
    """
    if not envelope.payload.get("is_active"):
        return []
    user_id = _int_or_none(envelope.payload.get("user_id"))
    if user_id is None:
        return []
    return [
        NotificationRequest(
            recipient_id=user_id,
            notification_type=NotificationType.ACCOUNT,
            event_key=envelope.name,
            title="Your ONEST account was reactivated",
            dedupe_key=_event_key(envelope),
            priority=NotificationPriority.NORMAL,
            action_key="open_dashboard",
        )
    ]


def _contract_id(envelope: EventEnvelope) -> str:
    return str(envelope.payload.get("contract_id") or "").strip()


def _agent_contract_change(
    envelope: EventEnvelope,
    *,
    title: str,
    recipient_payload_key: str = "agent_id",
    action_key: str = "open_my_contract",
    priority: int = NotificationPriority.HIGH,
    is_mandatory: bool = True,
    dedupe_suffix: str = "",
) -> list[NotificationRequest]:
    """Shared builder for recipient-facing contract lifecycle notifications."""
    recipient_id = _int_or_none(envelope.payload.get(recipient_payload_key))
    contract_id = _contract_id(envelope)
    if recipient_id is None or not contract_id:
        return []
    dedupe = f"{envelope.name}:{contract_id}"
    if dedupe_suffix:
        dedupe = f"{dedupe}:{dedupe_suffix}"
    return [
        NotificationRequest(
            recipient_id=recipient_id,
            notification_type=NotificationType.CONTRACT,
            event_key=envelope.name,
            title=title,
            dedupe_key=dedupe,
            priority=priority,
            is_mandatory=is_mandatory,
            source_module="contract",
            source_record_type="agent_contract",
            source_record_id=contract_id,
            action_key=action_key,
            action_args=(),
        )
    ]


def _staff_contract_notices(
    envelope: EventEnvelope,
    *,
    title: str,
    action_key: str = "open_agent_contract",
    priority: int = NotificationPriority.NORMAL,
    is_mandatory: bool = False,
    dedupe_suffix: str = "",
    staff_ids: list[int] | None = None,
) -> list[NotificationRequest]:
    """Notices for authorized operational staff about one contract."""
    contract_id = _contract_id(envelope)
    if not contract_id:
        return []
    recipients = staff_ids
    if recipients is None:
        raw = envelope.payload.get("staff_ids") or []
        recipients = []
        for value in raw:
            parsed = _int_or_none(value)
            if parsed is not None:
                recipients.append(parsed)
    if not recipients:
        return []
    dedupe_base = f"{envelope.name}:{contract_id}"
    if dedupe_suffix:
        dedupe_base = f"{dedupe_base}:{dedupe_suffix}"
    return [
        NotificationRequest(
            recipient_id=staff_id,
            notification_type=NotificationType.CONTRACT,
            event_key=envelope.name,
            title=title,
            dedupe_key=f"{dedupe_base}:staff:{staff_id}",
            priority=priority,
            is_mandatory=is_mandatory,
            source_module="contract",
            source_record_type="agent_contract",
            source_record_id=contract_id,
            action_key=action_key,
            action_args=(contract_id,),
        )
        for staff_id in recipients
    ]


def _load_staff_ids(envelope: EventEnvelope) -> list[int]:
    """Resolve staff from payload or from the live contract + roles."""
    if "staff_ids" in envelope.payload:
        raw = envelope.payload.get("staff_ids") or []
        if not isinstance(raw, list):
            return []
        resolved = [_int_or_none(value) for value in raw]
        return [value for value in resolved if value is not None]
    contract_id = _contract_id(envelope)
    if not contract_id:
        return []
    from apps.contract.models import AgentContract
    from apps.contract.notification_recipients import operational_staff_ids

    contract = (
        AgentContract.objects.select_related("office", "office__region")
        .filter(public_id=contract_id)
        .first()
    )
    if contract is None:
        return []
    return operational_staff_ids(contract)


def contract_awaiting_company_signature(
    envelope: EventEnvelope,
) -> list[NotificationRequest]:
    """Tell the named company officer a contract needs their signature."""
    signatory_id = _int_or_none(envelope.payload.get("company_signatory_id"))
    if signatory_id is None:
        return []
    return _staff_contract_notices(
        envelope,
        title="An agent contract needs your company signature",
        action_key="open_company_contract_sign",
        priority=NotificationPriority.HIGH,
        is_mandatory=True,
        staff_ids=[signatory_id],
    )


def contract_pdf_ready(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Tell the recipient agent their review PDF is ready.

    PDF may generate while the contract still awaits company signature; the
    agent invite is deferred until status is ``sent``.
    """
    if str(envelope.payload.get("status") or "") != "sent":
        return []
    return _agent_contract_change(
        envelope,
        title="Your agent contract is ready to sign",
        action_key="open_my_contract_sign",
        is_mandatory=True,
    )


def contract_issued(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract was issued",
        is_mandatory=True,
    )


def contract_viewed(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Optional staff notice when the agent opens an issued contract."""
    return _staff_contract_notices(
        envelope,
        title="An agent viewed their contract",
        priority=NotificationPriority.LOW,
        is_mandatory=False,
        staff_ids=_load_staff_ids(envelope),
    )


def contract_signed(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Confirm to the signing agent that the agreement was recorded."""
    agent = _agent_contract_change(
        envelope,
        title="Your agent contract is signed",
        recipient_payload_key="signer_id",
        is_mandatory=True,
    )
    staff = _staff_contract_notices(
        envelope,
        title="An agent contract was signed",
        priority=NotificationPriority.NORMAL,
        is_mandatory=False,
        staff_ids=_load_staff_ids(envelope),
    )
    return agent + staff


def contract_activated(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract is now active",
        is_mandatory=True,
    )


def contract_superseded(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract was superseded",
        is_mandatory=True,
    )


def contract_terminated(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract was terminated",
        is_mandatory=True,
    )


def contract_expired(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract has expired",
        is_mandatory=True,
    )


def contract_generation_error(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Route PDF/finalization failure to ops staff — no contract contents."""
    return _staff_contract_notices(
        envelope,
        title="Contract PDF preparation failed",
        priority=NotificationPriority.HIGH,
        is_mandatory=True,
        staff_ids=_load_staff_ids(envelope),
    )


def contract_signature_reminder(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Cadenced reminder while the contract is still signable."""
    day = str(envelope.payload.get("reminder_day") or "").strip() or "n"
    return _agent_contract_change(
        envelope,
        title="Reminder: your agent contract is waiting for signature",
        action_key="open_my_contract_sign",
        priority=NotificationPriority.HIGH,
        is_mandatory=True,
        dedupe_suffix=f"day:{day}",
    )


def contract_expiration_warning(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Warn the agent (and optionally staff) that expiry is approaching."""
    day = str(envelope.payload.get("warning_day") or "").strip() or "n"
    agent = _agent_contract_change(
        envelope,
        title="Your agent contract is approaching expiration",
        priority=NotificationPriority.HIGH,
        is_mandatory=True,
        dedupe_suffix=f"day:{day}",
    )
    staff = _staff_contract_notices(
        envelope,
        title="An agent contract is approaching expiration",
        priority=NotificationPriority.NORMAL,
        is_mandatory=False,
        dedupe_suffix=f"day:{day}",
        staff_ids=_load_staff_ids(envelope),
    )
    return agent + staff


def _reservation_public_id(envelope: EventEnvelope) -> str:
    return str(envelope.payload.get("reservation_public_id") or "").strip()


def _inventory_policy_suffix(envelope: EventEnvelope) -> str:
    version = str(envelope.payload.get("policy_version") or "1").strip() or "1"
    return f"v:{version}"


def _inventory_owner_notice(
    envelope: EventEnvelope,
    *,
    title: str,
    action_key: str = "open_inventory_reservation",
    priority: int = NotificationPriority.HIGH,
    is_mandatory: bool = False,
    threshold_key: str,
    threshold_value: str,
) -> list[NotificationRequest]:
    owner_id = _int_or_none(envelope.payload.get("owner_id"))
    reservation_id = _reservation_public_id(envelope)
    if owner_id is None or not reservation_id:
        return []
    policy = _inventory_policy_suffix(envelope)
    return [
        NotificationRequest(
            recipient_id=owner_id,
            notification_type=NotificationType.INVENTORY,
            event_key=envelope.name,
            title=title,
            dedupe_key=(
                f"{envelope.name}:{reservation_id}:{policy}:{threshold_key}:"
                f"{threshold_value}"
            ),
            priority=priority,
            is_mandatory=is_mandatory,
            source_module="inventory",
            source_record_type="inventory_reservation",
            source_record_id=reservation_id,
            action_key=action_key,
            action_args=(reservation_id,),
        )
    ]


def _inventory_staff_notices(
    envelope: EventEnvelope,
    *,
    title: str,
    threshold_key: str,
    threshold_value: str,
    priority: int = NotificationPriority.NORMAL,
    is_mandatory: bool = False,
    staff_ids: list[int] | None = None,
) -> list[NotificationRequest]:
    reservation_id = _reservation_public_id(envelope)
    if not reservation_id:
        return []
    recipients = staff_ids
    if recipients is None:
        raw = envelope.payload.get("staff_ids") or []
        recipients = []
        for value in raw:
            parsed = _int_or_none(value)
            if parsed is not None:
                recipients.append(parsed)
    if not recipients:
        return []
    policy = _inventory_policy_suffix(envelope)
    dedupe_base = (
        f"{envelope.name}:{reservation_id}:{policy}:{threshold_key}:{threshold_value}"
    )
    return [
        NotificationRequest(
            recipient_id=staff_id,
            notification_type=NotificationType.INVENTORY,
            event_key=envelope.name,
            title=title,
            dedupe_key=f"{dedupe_base}:staff:{staff_id}",
            priority=priority,
            is_mandatory=is_mandatory,
            source_module="inventory",
            source_record_type="inventory_reservation",
            source_record_id=reservation_id,
            action_key="open_admin_reservation",
            action_args=(reservation_id,),
        )
        for staff_id in recipients
    ]


def inventory_return_due_soon(envelope: EventEnvelope) -> list[NotificationRequest]:
    day = str(envelope.payload.get("lead_day") or "").strip() or "n"
    return _inventory_owner_notice(
        envelope,
        title="Reminder: an inventory return is due soon",
        priority=NotificationPriority.NORMAL,
        threshold_key="lead",
        threshold_value=f"day:{day}",
    )


def inventory_return_overdue(envelope: EventEnvelope) -> list[NotificationRequest]:
    day = str(envelope.payload.get("overdue_day") or "").strip() or "n"
    return _inventory_owner_notice(
        envelope,
        title="Reminder: an inventory return is overdue",
        priority=NotificationPriority.HIGH,
        is_mandatory=True,
        threshold_key="overdue",
        threshold_value=f"day:{day}",
    )


def inventory_return_overdue_staff(
    envelope: EventEnvelope,
) -> list[NotificationRequest]:
    day = str(envelope.payload.get("overdue_day") or "").strip() or "n"
    return _inventory_staff_notices(
        envelope,
        title="An inventory return is overdue in your office",
        threshold_key="overdue",
        threshold_value=f"day:{day}",
        priority=NotificationPriority.HIGH,
    )


def inventory_lost_damaged_escalation(
    envelope: EventEnvelope,
) -> list[NotificationRequest]:
    day = str(envelope.payload.get("escalation_day") or "").strip() or "n"
    return _inventory_staff_notices(
        envelope,
        title="A lost or damaged inventory return needs follow-up",
        threshold_key="escalation",
        threshold_value=f"day:{day}",
        priority=NotificationPriority.HIGH,
        is_mandatory=True,
    )


def training_published(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Fan out required training that is live now. Scheduled stays silent."""
    from apps.training.notifications import requests_for_event

    return requests_for_event(envelope)


def training_required_changed(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Notify when an already-live row is marked required."""
    from apps.training.notifications import requests_for_event

    return requests_for_event(envelope)


def policy_published(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Fan out a mandatory policy the moment it is visible."""
    from apps.compliance.notifications import requests_for_event

    return requests_for_event(envelope)


def policy_ack_reminder(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Overdue mandatory policy acknowledgement — collapses per user+version."""
    recipient_id = _int_or_none(envelope.payload.get("recipient_id"))
    policy_id = _int_or_none(envelope.payload.get("policy_id"))
    if recipient_id is None or policy_id is None:
        return []
    return [
        NotificationRequest(
            recipient_id=recipient_id,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key=envelope.name,
            title="A required policy acknowledgement is overdue",
            dedupe_key=f"policy-ack-reminder:{policy_id}:{recipient_id}",
            priority=NotificationPriority.HIGH,
            is_mandatory=True,
            source_module="compliance",
            source_record_type="policy_version",
            source_record_id=str(policy_id),
            action_key="open_policy_detail",
            action_args=(policy_id,),
        )
    ]


EventBuilder = Callable[[EventEnvelope], list[NotificationRequest]]

EVENT_PRODUCERS: dict[str, EventBuilder] = {
    "user.onboarding.owner_assigned": onboarding_owner_assigned,
    OFFICE_HANDOFF_EVENT: onboarding_office_handoff,
    INVITATION_EVENT: onboarding_tool_invitation_sent,
    "user.account.state_changed": account_reactivated,
    "contract.awaiting_company_signature": contract_awaiting_company_signature,
    "contract.pdf_ready": contract_pdf_ready,
    "contract.issued": contract_issued,
    "contract.viewed": contract_viewed,
    "contract.signed": contract_signed,
    "contract.activated": contract_activated,
    "contract.superseded": contract_superseded,
    "contract.terminated": contract_terminated,
    "contract.expired": contract_expired,
    "contract.generation_error": contract_generation_error,
    "contract.signature_reminder": contract_signature_reminder,
    "contract.expiration_warning": contract_expiration_warning,
    "inventory.reservation.return_due_soon": inventory_return_due_soon,
    "inventory.reservation.return_overdue": inventory_return_overdue,
    "inventory.reservation.return_overdue_staff": inventory_return_overdue_staff,
    "inventory.reservation.lost_damaged_escalation": inventory_lost_damaged_escalation,
    "training.published": training_published,
    "training.required_changed": training_required_changed,
    "policy.published": policy_published,
    "policy.ack_reminder": policy_ack_reminder,
}


def notifications_for_event(envelope: EventEnvelope) -> list[NotificationRequest]:
    builder = EVENT_PRODUCERS.get(envelope.name)
    if builder is None:
        return []
    return builder(envelope)
