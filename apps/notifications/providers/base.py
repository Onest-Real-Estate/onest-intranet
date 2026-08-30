"""Contract every outbound delivery provider must satisfy.

A provider is one push *channel*: email, Microsoft Graph, Slack, …. The
notification row is already committed; providers only push a copy and record
the outcome on the shared delivery ledger. Swapping or adding a channel means
registering another provider — producers and the preference matrix stay put.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from apps.notifications.models import Notification
from apps.user.models import User


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of one provider send attempt.

    ``address`` is whatever the channel delivered to (mailbox, Teams user id,
    Slack user id). It is recorded on the ledger for ops, never used as an
    authorization input.
    """

    address: str = ""


class DeliveryProvider(Protocol):
    """One outbound channel.

    Implementations must be side-effect free until :meth:`send` — preflight and
    send-time refusals never talk to the remote API.
    """

    #: Stable channel key stored on the delivery ledger and in preferences.
    channel: str
    label: str
    description: str
    #: Whether readers may opt out of optional categories on this channel.
    configurable: bool
    #: Default for optional categories when the reader has never chosen.
    default_opt_in: bool

    def is_enabled(self) -> bool:
        """Whether this deployment may queue work for the channel."""
        ...

    def preflight_refusal(
        self,
        notification: Notification,
        recipient: User | None,
        choices: dict[str, dict[str, bool]],
    ) -> str:
        """Cheap refusal before queueing, or ``""`` when the row may pend."""
        ...

    def send_refusal(
        self,
        notification: Notification,
        recipient: User | None,
        *,
        now: datetime,
    ) -> str:
        """Authoritative refusal immediately before :meth:`send`."""
        ...

    def send(self, notification: Notification, recipient: User) -> DeliveryResult:
        """Deliver, or raise. The ledger records success or schedules retry."""
        ...
