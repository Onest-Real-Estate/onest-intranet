"""Microsoft 365 / Graph delivery stub.

Disabled until ``NOTIFICATION_MICROSOFT_ENABLED`` is on *and* an approved
Graph app is configured. Producers and the ledger already treat ``microsoft``
as a first-class channel; turning this on does not require rewriting them.
"""

from __future__ import annotations

from datetime import datetime

from django.conf import settings

from apps.notifications.models import Notification
from apps.notifications.preferences import channel_refusal, stored_choices_map
from apps.notifications.providers.base import DeliveryResult
from apps.notifications.sources import resolve_sources
from apps.user.models import User

CHANNEL_MICROSOFT = "microsoft"

SUPPRESSED_DISABLED = "provider_disabled"
SUPPRESSED_RECIPIENT_INACTIVE = "recipient_inactive"
SUPPRESSED_NO_ADDRESS = "no_microsoft_identity"
SUPPRESSED_EXPIRED = "notification_expired"
SUPPRESSED_ARCHIVED = "notification_archived"
SUPPRESSED_ALREADY_READ = "already_read_in_app"
SUPPRESSED_SOURCE = "source_unavailable"


class MicrosoftDeliveryProvider:
    channel = CHANNEL_MICROSOFT
    label = "Microsoft 365"
    description = (
        "A short alert in your Microsoft 365 activity feed or Teams when "
        "the brokerage enables that channel."
    )
    configurable = True
    default_opt_in = False

    def is_enabled(self) -> bool:
        if not getattr(settings, "NOTIFICATION_MICROSOFT_ENABLED", False):
            return False
        client_id = (
            getattr(settings, "NOTIFICATION_MICROSOFT_CLIENT_ID", "") or ""
        ).strip()
        return bool(client_id)

    def _identity(self, recipient: User | None) -> str:
        if recipient is None:
            return ""
        return (getattr(recipient, "email", "") or "").strip()

    def preflight_refusal(
        self,
        notification: Notification,
        recipient: User | None,
        choices: dict[str, dict[str, bool]],
    ) -> str:
        if not self.is_enabled():
            return SUPPRESSED_DISABLED
        if recipient is None or not recipient.is_active:
            return SUPPRESSED_RECIPIENT_INACTIVE
        if not self._identity(recipient):
            return SUPPRESSED_NO_ADDRESS
        return channel_refusal(choices, notification, channel_key=self.channel)

    def send_refusal(
        self,
        notification: Notification,
        recipient: User | None,
        *,
        now: datetime,
    ) -> str:
        if not self.is_enabled():
            return SUPPRESSED_DISABLED
        if recipient is None or not recipient.is_active:
            return SUPPRESSED_RECIPIENT_INACTIVE
        if not self._identity(recipient):
            return SUPPRESSED_NO_ADDRESS
        if notification.is_expired(now=now):
            return SUPPRESSED_EXPIRED
        if notification.archived_at is not None:
            return SUPPRESSED_ARCHIVED
        if notification.read_at is not None:
            return SUPPRESSED_ALREADY_READ
        refusal = channel_refusal(
            stored_choices_map([recipient.pk]).get(recipient.pk, {}),
            notification,
            channel_key=self.channel,
        )
        if refusal:
            return refusal
        resolution = resolve_sources(recipient, [notification]).get(
            notification.public_id
        )
        if resolution is None or not resolution.available:
            return SUPPRESSED_SOURCE
        return ""

    def send(self, notification: Notification, recipient: User) -> DeliveryResult:
        raise RuntimeError(
            "Microsoft Graph notification delivery is not implemented yet. "
            "Disable NOTIFICATION_MICROSOFT_ENABLED or ship a Graph sender."
        )
