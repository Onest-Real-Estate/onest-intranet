"""Slack delivery stub.

Disabled until ``NOTIFICATION_SLACK_ENABLED`` is on and a bot token is set.
Same seam as Microsoft: producers stay channel-agnostic.
"""

from __future__ import annotations

from datetime import datetime

from django.conf import settings

from apps.notifications.models import Notification
from apps.notifications.preferences import channel_refusal, stored_choices_map
from apps.notifications.providers.base import DeliveryResult
from apps.notifications.sources import resolve_sources
from apps.user.models import User

CHANNEL_SLACK = "slack"

SUPPRESSED_DISABLED = "provider_disabled"
SUPPRESSED_RECIPIENT_INACTIVE = "recipient_inactive"
SUPPRESSED_NO_ADDRESS = "no_slack_identity"
SUPPRESSED_EXPIRED = "notification_expired"
SUPPRESSED_ARCHIVED = "notification_archived"
SUPPRESSED_ALREADY_READ = "already_read_in_app"
SUPPRESSED_SOURCE = "source_unavailable"


class SlackDeliveryProvider:
    channel = CHANNEL_SLACK
    label = "Slack"
    description = "A short DM or channel mention when the brokerage connects Slack."
    configurable = True
    default_opt_in = False

    def is_enabled(self) -> bool:
        if not getattr(settings, "NOTIFICATION_SLACK_ENABLED", False):
            return False
        token = (getattr(settings, "NOTIFICATION_SLACK_BOT_TOKEN", "") or "").strip()
        return bool(token)

    def _identity(self, recipient: User | None) -> str:
        if recipient is None:
            return ""
        # Future: map Hub users to Slack user ids. Email is the interim key.
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
            "Slack notification delivery is not implemented yet. "
            "Disable NOTIFICATION_SLACK_ENABLED or ship a Slack sender."
        )
