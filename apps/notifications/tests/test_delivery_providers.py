"""Pluggable notification delivery providers."""

from __future__ import annotations

import pytest

from apps.notifications.categories import (
    CHANNEL_EMAIL,
    CHANNEL_MICROSOFT,
    CHANNEL_SLACK,
    visible_channels,
)
from apps.notifications.providers.microsoft import MicrosoftDeliveryProvider
from apps.notifications.providers.registry import (
    enabled_providers,
    get_provider,
    register_default_providers,
)
from apps.notifications.providers.slack import SlackDeliveryProvider


@pytest.fixture(autouse=True)
def _providers():
    register_default_providers()


def test_email_provider_always_enabled():
    provider = get_provider(CHANNEL_EMAIL)
    assert provider is not None
    assert provider.is_enabled()
    assert provider.channel in {p.channel for p in enabled_providers()}


def test_microsoft_and_slack_disabled_by_default(settings):
    settings.NOTIFICATION_MICROSOFT_ENABLED = False
    settings.NOTIFICATION_SLACK_ENABLED = False
    assert MicrosoftDeliveryProvider().is_enabled() is False
    assert SlackDeliveryProvider().is_enabled() is False
    assert CHANNEL_MICROSOFT not in {p.channel for p in enabled_providers()}
    assert CHANNEL_SLACK not in {p.channel for p in enabled_providers()}


def test_microsoft_requires_client_id(settings):
    settings.NOTIFICATION_MICROSOFT_ENABLED = True
    settings.NOTIFICATION_MICROSOFT_CLIENT_ID = ""
    assert MicrosoftDeliveryProvider().is_enabled() is False
    settings.NOTIFICATION_MICROSOFT_CLIENT_ID = "app-id"
    assert MicrosoftDeliveryProvider().is_enabled() is True


def test_slack_requires_bot_token(settings):
    settings.NOTIFICATION_SLACK_ENABLED = True
    settings.NOTIFICATION_SLACK_BOT_TOKEN = ""
    assert SlackDeliveryProvider().is_enabled() is False
    settings.NOTIFICATION_SLACK_BOT_TOKEN = "xoxb-test"
    assert SlackDeliveryProvider().is_enabled() is True


def test_visible_channels_hide_dormant_providers(settings):
    settings.NOTIFICATION_MICROSOFT_ENABLED = False
    settings.NOTIFICATION_SLACK_ENABLED = False
    keys = {channel.key for channel in visible_channels()}
    assert CHANNEL_EMAIL in keys
    assert CHANNEL_MICROSOFT not in keys
    assert CHANNEL_SLACK not in keys


def test_visible_channels_include_enabled_microsoft(settings):
    settings.NOTIFICATION_MICROSOFT_ENABLED = True
    settings.NOTIFICATION_MICROSOFT_CLIENT_ID = "app-id"
    keys = {channel.key for channel in visible_channels()}
    assert CHANNEL_MICROSOFT in keys


def test_microsoft_send_raises_until_implemented(settings):
    settings.NOTIFICATION_MICROSOFT_ENABLED = True
    settings.NOTIFICATION_MICROSOFT_CLIENT_ID = "app-id"
    provider = MicrosoftDeliveryProvider()
    from unittest.mock import MagicMock

    with pytest.raises(RuntimeError, match="not implemented"):
        provider.send(MagicMock(), MagicMock())
