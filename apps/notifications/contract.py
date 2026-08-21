"""Shared in-app notification contract.

Domain modules do not write :class:`~apps.notifications.models.Notification`
rows. They describe one delivery with a :class:`NotificationRequest` and hand
it to :mod:`apps.notifications.service`, which validates the recipient, the
source authorization, the mandatory policy, and the idempotency key before
anything is persisted.

Two rules shape every field here:

* **The row carries no sensitive detail.** ``title`` is a fixed, non-sensitive
  sentence about the *kind* of thing that happened ("An onboarding case was
  assigned to you"), never the client, property, or document it concerns.
  Everything else is resolved from the source record at view time, through
  :mod:`apps.notifications.sources`, so a revoked grant removes the detail
  from notifications that were delivered long before it was revoked.
* **The destination is a typed action, never a URL.** Producers name an action
  from the reviewed allowlist in :mod:`apps.notifications.actions`; the path is
  reversed at render time and the destination re-authorizes on arrival.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.notifications.actions import ACTION_BY_KEY, validate_action_args

#: Longest stored title. Titles are fixed producer copy, not user input.
MAX_TITLE_LENGTH = 160
#: Longest idempotency key. Producers build these from stable record identity.
MAX_DEDUPE_KEY_LENGTH = 200


class NotificationType:
    """Domain that produced the notification.

    The type is the reader's filter and the resolver's routing key; it is not
    an authorization input. Every consumer domain named in the notification
    brief has an entry so producers never have to widen this enum in a hurry.
    """

    CONTRACT = "contract"
    TRANSACTION = "transaction"
    ANNOUNCEMENT = "announcement"
    TRAINING = "training"
    INVENTORY = "inventory"
    ROOM = "room"
    LEAD = "lead"
    ADMINISTRATIVE = "administrative"
    ACCOUNT = "account"


TYPE_LABELS: dict[str, str] = {
    NotificationType.CONTRACT: "Contracts",
    NotificationType.TRANSACTION: "Transactions",
    NotificationType.ANNOUNCEMENT: "Announcements",
    NotificationType.TRAINING: "Training",
    NotificationType.INVENTORY: "Inventory",
    NotificationType.ROOM: "Rooms",
    NotificationType.LEAD: "Leads",
    NotificationType.ADMINISTRATIVE: "Administration",
    NotificationType.ACCOUNT: "Your account",
}

NOTIFICATION_TYPES: frozenset[str] = frozenset(TYPE_LABELS)


class NotificationPriority:
    """Lower number sorts first, matching the action-item contract."""

    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


PRIORITY_LABELS: dict[int, str] = {
    NotificationPriority.CRITICAL: "Critical",
    NotificationPriority.HIGH: "High priority",
    NotificationPriority.NORMAL: "Normal",
    NotificationPriority.LOW: "Low priority",
}

PRIORITY_KEYS: dict[int, str] = {
    NotificationPriority.CRITICAL: "critical",
    NotificationPriority.HIGH: "high",
    NotificationPriority.NORMAL: "normal",
    NotificationPriority.LOW: "low",
}

PRIORITY_BY_KEY: dict[str, int] = {key: value for value, key in PRIORITY_KEYS.items()}


class InvalidNotification(ValueError):
    """A producer described a delivery the service will not persist."""


def normalize_copy(value: str, *, limit: int) -> str:
    """Collapse whitespace and clip — stored copy is single-line by contract."""
    return " ".join(str(value).split())[:limit]


@dataclass(frozen=True)
class NotificationRequest:
    """One delivery for one recipient, before it becomes a row.

    ``dedupe_key`` is the idempotency key and is unique per recipient: the same
    producer, replayed, updates nothing and creates nothing. Build it from
    stable record identity (``"onboarding:owner:42"``), never from a timestamp.
    """

    recipient_id: int
    notification_type: str
    event_key: str
    title: str
    dedupe_key: str
    priority: int = NotificationPriority.NORMAL
    is_mandatory: bool = False
    source_module: str = ""
    source_record_type: str = ""
    source_record_id: str = ""
    action_key: str = ""
    action_args: tuple[str | int, ...] = ()
    available_at: datetime | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.notification_type not in NOTIFICATION_TYPES:
            raise InvalidNotification(
                f"Unknown notification type: {self.notification_type!r}"
            )
        if self.priority not in PRIORITY_LABELS:
            raise InvalidNotification(f"Unknown priority: {self.priority!r}")
        if not str(self.recipient_id).isdigit():
            raise InvalidNotification("A notification needs a recipient id")
        if not normalize_copy(self.title, limit=MAX_TITLE_LENGTH):
            raise InvalidNotification("A notification needs a title")
        if not normalize_copy(self.dedupe_key, limit=MAX_DEDUPE_KEY_LENGTH):
            raise InvalidNotification("A notification needs an idempotency key")
        if not self.event_key.strip():
            raise InvalidNotification("A notification needs an event key")
        if self.action_key and self.action_key not in ACTION_BY_KEY:
            raise InvalidNotification(f"Unknown action: {self.action_key!r}")
        if self.action_key:
            validate_action_args(self.action_key, self.action_args)
        elif self.action_args:
            raise InvalidNotification("Action arguments need an action")
        # Mandatory work has to be doable: an acknowledgement with nowhere to
        # go is a dead end the reader cannot clear.
        if self.is_mandatory and not self.action_key:
            raise InvalidNotification("A mandatory notification needs an action")
        if self.is_mandatory and self.expires_at is not None:
            raise InvalidNotification("A mandatory notification cannot expire")
        if (
            self.available_at is not None
            and self.expires_at is not None
            and self.expires_at <= self.available_at
        ):
            raise InvalidNotification("A notification must expire after it appears")

    @property
    def clean_title(self) -> str:
        return normalize_copy(self.title, limit=MAX_TITLE_LENGTH)

    @property
    def clean_dedupe_key(self) -> str:
        return normalize_copy(self.dedupe_key, limit=MAX_DEDUPE_KEY_LENGTH)
