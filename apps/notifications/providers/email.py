"""SMTP email delivery — the default outbound channel."""

from __future__ import annotations

from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import validate_email

from apps.notifications.emails import render_notification_email
from apps.notifications.models import Notification
from apps.notifications.preferences import channel_refusal
from apps.notifications.providers.base import DeliveryResult
from apps.notifications.sources import resolve_sources
from apps.user.models import User

CHANNEL_EMAIL = "email"

SUPPRESSED_RECIPIENT_INACTIVE = "recipient_inactive"
SUPPRESSED_NO_ADDRESS = "no_email_address"
SUPPRESSED_INVALID_ADDRESS = "invalid_email_address"
SUPPRESSED_EXPIRED = "notification_expired"
SUPPRESSED_ARCHIVED = "notification_archived"
SUPPRESSED_ALREADY_READ = "already_read_in_app"
SUPPRESSED_SOURCE = "source_unavailable"


class EmailDeliveryProvider:
    channel = CHANNEL_EMAIL
    label = "Email"
    description = (
        "A short message to your work address telling you something is "
        "waiting. The details stay in the hub."
    )
    configurable = True
    default_opt_in = True

    def is_enabled(self) -> bool:
        return True

    def preflight_refusal(
        self,
        notification: Notification,
        recipient: User | None,
        choices: dict[str, dict[str, bool]],
    ) -> str:
        if recipient is None or not recipient.is_active:
            return SUPPRESSED_RECIPIENT_INACTIVE
        if not recipient.email:
            return SUPPRESSED_NO_ADDRESS
        return channel_refusal(choices, notification, channel_key=self.channel)

    def send_refusal(
        self,
        notification: Notification,
        recipient: User | None,
        *,
        now: datetime,
    ) -> str:
        if recipient is None or not recipient.is_active:
            return SUPPRESSED_RECIPIENT_INACTIVE
        if not recipient.email:
            return SUPPRESSED_NO_ADDRESS
        try:
            validate_email(recipient.email)
        except ValidationError:
            return SUPPRESSED_INVALID_ADDRESS
        if notification.is_expired(now=now):
            return SUPPRESSED_EXPIRED
        if notification.archived_at is not None:
            return SUPPRESSED_ARCHIVED
        if notification.read_at is not None:
            return SUPPRESSED_ALREADY_READ
        from apps.notifications.preferences import stored_choices_map

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
        rendered = render_notification_email(notification, recipient)
        message = EmailMultiAlternatives(
            subject=rendered.subject,
            body=rendered.text_body,
            to=[recipient.email],
            connection=get_connection(),
        )
        message.attach_alternative(rendered.html_body, "text/html")
        message.send(fail_silently=False)
        return DeliveryResult(address=recipient.email)
