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


def _agent_contract_change(
    envelope: EventEnvelope,
    *,
    title: str,
    recipient_payload_key: str = "agent_id",
    action_key: str = "open_my_contract",
    priority: int = NotificationPriority.HIGH,
) -> list[NotificationRequest]:
    """Shared builder for recipient-facing contract lifecycle notifications."""
    recipient_id = _int_or_none(envelope.payload.get(recipient_payload_key))
    contract_id = str(envelope.payload.get("contract_id") or "").strip()
    if recipient_id is None or not contract_id:
        return []
    return [
        NotificationRequest(
            recipient_id=recipient_id,
            notification_type=NotificationType.CONTRACT,
            event_key=envelope.name,
            title=title,
            dedupe_key=f"{envelope.name}:{contract_id}",
            priority=priority,
            source_module="contract",
            source_record_type="agent_contract",
            source_record_id=contract_id,
            action_key=action_key,
            action_args=(),
        )
    ]


def contract_pdf_ready(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Tell the recipient agent their review PDF is ready."""
    return _agent_contract_change(
        envelope,
        title="Your agent contract is ready to sign",
        action_key="open_my_contract_sign",
    )


def contract_issued(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract was issued",
    )


def contract_signed(envelope: EventEnvelope) -> list[NotificationRequest]:
    """Confirm to the signing agent that the agreement was recorded."""
    return _agent_contract_change(
        envelope,
        title="Your agent contract is signed",
        recipient_payload_key="signer_id",
    )


def contract_activated(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract is now active",
    )


def contract_superseded(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract was superseded",
    )


def contract_terminated(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract was terminated",
    )


def contract_expired(envelope: EventEnvelope) -> list[NotificationRequest]:
    return _agent_contract_change(
        envelope,
        title="Your agent contract has expired",
    )


EventBuilder = Callable[[EventEnvelope], list[NotificationRequest]]

EVENT_PRODUCERS: dict[str, EventBuilder] = {
    "user.onboarding.owner_assigned": onboarding_owner_assigned,
    "user.account.state_changed": account_reactivated,
    "contract.pdf_ready": contract_pdf_ready,
    "contract.issued": contract_issued,
    "contract.signed": contract_signed,
    "contract.activated": contract_activated,
    "contract.superseded": contract_superseded,
    "contract.terminated": contract_terminated,
    "contract.expired": contract_expired,
}


def notifications_for_event(envelope: EventEnvelope) -> list[NotificationRequest]:
    builder = EVENT_PRODUCERS.get(envelope.name)
    if builder is None:
        return []
    return builder(envelope)
