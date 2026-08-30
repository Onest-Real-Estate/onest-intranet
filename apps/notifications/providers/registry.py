"""Provider registry — the only place channel keys are collected.

Providers register at app startup. Queueing and the preference page ask the
registry which channels exist and which are enabled *right now*, so adding
Slack or Microsoft Graph is a registration, not a rewrite of producers.
"""

from __future__ import annotations

from apps.notifications.providers.base import DeliveryProvider

_PROVIDERS: dict[str, DeliveryProvider] = {}


def register_provider(provider: DeliveryProvider) -> None:
    """Idempotent registration keyed by ``provider.channel``."""
    existing = _PROVIDERS.get(provider.channel)
    if existing is not None and existing is not provider:
        raise RuntimeError(
            f"Delivery provider channel {provider.channel!r} is already registered"
        )
    _PROVIDERS[provider.channel] = provider


def get_provider(channel: str) -> DeliveryProvider | None:
    return _PROVIDERS.get(channel)


def registered_channels() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def enabled_providers() -> tuple[DeliveryProvider, ...]:
    """Providers this deployment is allowed to queue work for."""
    return tuple(provider for provider in _PROVIDERS.values() if provider.is_enabled())


def clear_providers() -> None:
    """Test helper — drop every registration."""
    _PROVIDERS.clear()


def register_default_providers() -> None:
    """Wire the shipped providers. Safe to call more than once."""
    from apps.notifications.providers.email import EmailDeliveryProvider
    from apps.notifications.providers.microsoft import MicrosoftDeliveryProvider
    from apps.notifications.providers.slack import SlackDeliveryProvider

    for provider in (
        EmailDeliveryProvider(),
        MicrosoftDeliveryProvider(),
        SlackDeliveryProvider(),
    ):
        if provider.channel not in _PROVIDERS:
            register_provider(provider)
