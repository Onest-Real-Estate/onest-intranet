"""Pluggable outbound notification delivery providers.

In-app rows are the domain fact. Push channels (email today; Microsoft Graph,
Slack, etc. later) are interchangeable backends behind one ledger and one
queue. Domain producers never import a concrete provider.
"""

from __future__ import annotations

from apps.notifications.providers.base import DeliveryProvider, DeliveryResult
from apps.notifications.providers.registry import (
    enabled_providers,
    get_provider,
    register_provider,
    registered_channels,
)

__all__ = [
    "DeliveryProvider",
    "DeliveryResult",
    "enabled_providers",
    "get_provider",
    "register_provider",
    "registered_channels",
]
