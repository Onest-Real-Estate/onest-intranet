"""Notification categories and channels — the contract a preference edits.

A *category* is the reader-facing grouping of notifications, keyed by the same
value as :class:`~apps.notifications.contract.NotificationType` so there is one
vocabulary in the system rather than two that have to be kept in step.

A *channel* is how a delivery reaches the reader. Two exist:

* ``in_app`` — the notification centre. It is the record of what was delivered,
  so it is not configurable: a reader who could switch it off would have
  compliance acknowledgements land nowhere and no way to find out.
* ``email`` — a copy pushed outside the hub, and the channel this module exists
  to let people turn down.

Three rules decide whether a delivery may use a channel:

1. A notification marked ``is_mandatory`` always sends. Legal, compliance, and
   security acknowledgements are not preferences.
2. A category marked ``mandatory`` always sends, whatever the reader stored.
3. Everything else follows the stored preference, and an absent entry follows
   the category's ``default_email``.

Adding a category
-----------------
Add the type to :mod:`apps.notifications.contract`, add a
:class:`NotificationCategory` here, and bump :data:`PREFERENCE_POLICY_VERSION`.
Stored preference maps written before the addition simply have no entry for it,
so **a new category starts at its registry default for everyone** until each
reader chooses otherwise — no migration rewrites anybody's saved choices, and
no existing choice is reinterpreted. The house default for a new category is
``default_email=True``; a category whose stream is high-volume should ship with
``False`` so it is opt-in rather than opt-out.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.notifications.contract import NOTIFICATION_TYPES

#: Bumped whenever the category set, the channel set, or a default changes.
#: Stored alongside each reader's choices so the settings page can tell a
#: reader their saved set predates the current catalog.
PREFERENCE_POLICY_VERSION = 1

CHANNEL_IN_APP = "in_app"
CHANNEL_EMAIL = "email"


@dataclass(frozen=True)
class NotificationChannel:
    key: str
    label: str
    description: str
    #: ``False`` means the reader cannot switch it off. The settings page still
    #: shows it, disabled, with :attr:`locked_reason` — a channel that silently
    #: does not appear reads as a channel that does not exist.
    configurable: bool
    locked_reason: str = ""


CHANNEL_DEFINITIONS: tuple[NotificationChannel, ...] = (
    NotificationChannel(
        key=CHANNEL_IN_APP,
        label="In the hub",
        description=(
            "Every notification is recorded in your notification centre and "
            "counted in the header badge."
        ),
        configurable=False,
        locked_reason=(
            "The notification centre is the record of what was sent to you, so "
            "it stays on."
        ),
    ),
    NotificationChannel(
        key=CHANNEL_EMAIL,
        label="Email",
        description=(
            "A short message to your work address telling you something is "
            "waiting. The details stay in the hub."
        ),
        configurable=True,
    ),
)

CHANNEL_BY_KEY: dict[str, NotificationChannel] = {
    channel.key: channel for channel in CHANNEL_DEFINITIONS
}

CONFIGURABLE_CHANNELS: tuple[str, ...] = tuple(
    channel.key for channel in CHANNEL_DEFINITIONS if channel.configurable
)


@dataclass(frozen=True)
class NotificationCategory:
    key: str
    label: str
    #: What arrives in this category, in the reader's words.
    description: str
    #: ``True`` when the category carries notices the brokerage is obliged to
    #: deliver. Locked on in every channel, with :attr:`mandatory_reason` shown.
    mandatory: bool = False
    mandatory_reason: str = ""
    #: Whether email is on for a reader who has never chosen.
    default_email: bool = True


CATEGORY_DEFINITIONS: tuple[NotificationCategory, ...] = (
    NotificationCategory(
        key="account",
        label="Your account",
        description=(
            "Security and account-state notices about your own access — sign-in "
            "changes, reactivation, and the permissions you hold."
        ),
        mandatory=True,
        mandatory_reason=(
            "Security notices about your own account cannot be turned off. If "
            "somebody changes your access, you are told."
        ),
    ),
    NotificationCategory(
        key="administrative",
        label="Administration",
        description=(
            "Work assigned to you by the brokerage: onboarding cases, role and "
            "scope changes, and administrative follow-ups."
        ),
    ),
    NotificationCategory(
        key="contract",
        label="Contracts",
        description="Movement on brokerage agreements you are party to.",
    ),
    NotificationCategory(
        key="transaction",
        label="Transactions",
        description="Status changes on transactions you are working.",
    ),
    NotificationCategory(
        key="announcement",
        label="Announcements",
        description="Company and office announcements addressed to you.",
    ),
    NotificationCategory(
        key="training",
        label="Training",
        description="Courses assigned to you and their due dates.",
    ),
    NotificationCategory(
        key="inventory",
        label="Inventory",
        description="Listing and inventory movement in your office.",
        default_email=False,
    ),
    NotificationCategory(
        key="room",
        label="Rooms",
        description="Room and resource reservations you booked or approve.",
        default_email=False,
    ),
    NotificationCategory(
        key="lead",
        label="Leads",
        description="Leads routed to you.",
        default_email=False,
    ),
)

CATEGORY_BY_KEY: dict[str, NotificationCategory] = {
    category.key: category for category in CATEGORY_DEFINITIONS
}

CATEGORY_KEYS: frozenset[str] = frozenset(CATEGORY_BY_KEY)


def _assert_registry_matches_types() -> None:
    """Every notification type is a category and vice versa.

    A type with no category would be delivered under a heading no reader can
    find, and a category with no type would be a switch that governs nothing.
    Checked at import so the mismatch surfaces at startup, not at send time.
    """
    missing = NOTIFICATION_TYPES - CATEGORY_KEYS
    extra = CATEGORY_KEYS - NOTIFICATION_TYPES
    if missing or extra:
        raise RuntimeError(
            "Notification categories are out of step with notification types: "
            f"missing={sorted(missing)} unknown={sorted(extra)}"
        )


_assert_registry_matches_types()


def category_default(category_key: str, channel_key: str) -> bool:
    """The value that applies before a reader has chosen anything.

    Fails closed on an unknown category: a delivery whose type has no entry in
    the registry has no reviewed default, and sending it anyway would push a
    category nobody approved out to somebody's inbox.
    """
    category = CATEGORY_BY_KEY.get(category_key)
    if category is None:
        return False
    channel = CHANNEL_BY_KEY.get(channel_key)
    if channel is None:
        return False
    if not channel.configurable or category.mandatory:
        return True
    if channel.key == CHANNEL_EMAIL:
        return category.default_email
    return True


def is_locked(category_key: str, channel_key: str) -> bool:
    """Whether the reader may change this cell at all."""
    category = CATEGORY_BY_KEY.get(category_key)
    channel = CHANNEL_BY_KEY.get(channel_key)
    if category is None or channel is None:
        return True
    return category.mandatory or not channel.configurable


def lock_reason(category_key: str, channel_key: str) -> str:
    category = CATEGORY_BY_KEY.get(category_key)
    channel = CHANNEL_BY_KEY.get(channel_key)
    if channel is not None and not channel.configurable:
        return channel.locked_reason
    if category is not None and category.mandatory:
        return category.mandatory_reason
    return ""


def field_name(channel_key: str, category_key: str) -> str:
    """The form field one editable cell posts under."""
    return f"{channel_key}__{category_key}"
