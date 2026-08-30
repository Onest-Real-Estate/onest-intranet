"""Reading, resolving, and saving one reader's notification preferences.

Nothing outside this module interprets the stored JSON. Callers ask two
questions — *what should the settings page show?* and *may this delivery use
this channel?* — and both answers apply the same three rules from
:mod:`apps.notifications.categories`: a mandatory notification always sends, a
mandatory category always sends, and everything else follows the stored choice
with the registry default standing in for silence.

Every function here is self-scoped: the only identity input is the user object
the caller already holds, and there is no path that reads or writes somebody
else's row.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.notifications.categories import (
    CATEGORY_BY_KEY,
    CATEGORY_DEFINITIONS,
    CHANNEL_BY_KEY,
    CHANNEL_EMAIL,
    PREFERENCE_POLICY_VERSION,
    category_default,
    field_name,
    is_locked,
    lock_reason,
    visible_channels,
)
from apps.notifications.models import Notification, NotificationPreference

logger = logging.getLogger("apps.notifications")


def normalize_stored(raw: Any) -> dict[str, dict[str, bool]]:
    """Keep only choices this deployment still recognises.

    A stored map can name a channel or a category that has since been renamed
    or removed — by an older release, by a hand edit, or by a restored backup.
    Unknown keys are dropped rather than raising: a settings page that 500s
    because of an old row is a settings page nobody can use to fix the row.
    Locked cells are dropped too, so a hand-edited ``{"email": {"account":
    false}}`` cannot switch off a mandatory notice.
    """
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict[str, bool]] = {}
    for channel_key, categories in raw.items():
        if channel_key not in CHANNEL_BY_KEY or not isinstance(categories, dict):
            continue
        for category_key, value in categories.items():
            if category_key not in CATEGORY_BY_KEY:
                continue
            if is_locked(category_key, channel_key):
                continue
            if not isinstance(value, bool):
                continue
            cleaned.setdefault(channel_key, {})[category_key] = value
    return cleaned


def get_preference(user) -> NotificationPreference:
    """The reader's row, created on first read with no choices recorded.

    An empty row means "has never chosen", which is exactly what the defaults
    are for — it is not the same as having chosen everything off.
    """
    preference, _created = NotificationPreference.objects.get_or_create(user=user)
    return preference


def stored_choices(user) -> dict[str, dict[str, bool]]:
    """The reader's explicit choices, without creating a row.

    Delivery reads preferences on every send; making that read write a row
    would turn a background sweep into a write storm and would create rows for
    readers who never opened the settings page.
    """
    row = NotificationPreference.objects.filter(user=user).only("channels").first()
    return normalize_stored(row.channels) if row is not None else {}


def stored_choices_map(user_ids) -> dict[int, dict[str, dict[str, bool]]]:
    """Explicit choices for a batch of readers, in one query.

    Readers with no row map to ``{}`` — "has never chosen" — so a fan-out of a
    thousand recipients costs one query rather than a thousand.
    """
    unique = {int(value) for value in user_ids}
    if not unique:
        return {}
    rows = NotificationPreference.objects.filter(user_id__in=unique).values_list(
        "user_id", "channels"
    )
    resolved = {user_id: normalize_stored(channels) for user_id, channels in rows}
    return {user_id: resolved.get(user_id, {}) for user_id in unique}


def channel_allows(
    stored: dict[str, dict[str, bool]], *, channel_key: str, category_key: str
) -> bool:
    """Resolve one cell: an explicit choice, or the documented default."""
    if is_locked(category_key, channel_key):
        return category_default(category_key, channel_key)
    choice = stored.get(channel_key, {}).get(category_key)
    if isinstance(choice, bool):
        return choice
    return category_default(category_key, channel_key)


def resolved_matrix(user) -> dict[str, dict[str, bool]]:
    """Every visible channel × category cell, with defaults and locks applied."""
    stored = stored_choices(user)
    return {
        channel.key: {
            category.key: channel_allows(
                stored, channel_key=channel.key, category_key=category.key
            )
            for category in CATEGORY_DEFINITIONS
        }
        for channel in visible_channels()
    }


def channel_refusal(
    stored: dict[str, dict[str, bool]],
    notification: Notification,
    *,
    channel_key: str,
) -> str:
    """Why this delivery may not use this channel, or ``""`` when it may.

    Returns a coarse machine-readable reason rather than a bool so the delivery
    ledger can record *why* something was never sent without storing anything
    about the record it concerned.
    """
    if channel_key not in CHANNEL_BY_KEY:
        return "unknown_channel"
    # A required acknowledgement outranks every preference, in every category.
    if notification.is_mandatory:
        return ""
    category = CATEGORY_BY_KEY.get(notification.notification_type)
    if category is None:
        # Fails closed: a type with no reviewed category has no reviewed
        # default either, and guessing one pushes unapproved mail.
        return "unknown_category"
    if category.mandatory:
        return ""
    allowed = channel_allows(stored, channel_key=channel_key, category_key=category.key)
    return "" if allowed else "preference_opted_out"


def email_refusal(user, notification: Notification) -> str:
    """Single-reader convenience over :func:`channel_refusal`."""
    return channel_refusal(
        stored_choices(user), notification, channel_key=CHANNEL_EMAIL
    )


# --------------------------------------------------------------------------- #
# Saving
# --------------------------------------------------------------------------- #


def save_choices(user, submitted: dict[str, dict[str, bool]]) -> NotificationPreference:
    """Persist the reader's own choices and record the change.

    ``submitted`` is normalized first, so a locked cell posted by a crafted
    form is discarded rather than honoured, and the stored map only ever
    contains cells the reader is actually allowed to decide.
    """
    cleaned = normalize_stored(submitted)
    preference = get_preference(user)
    before = normalize_stored(preference.channels)
    if before == cleaned and preference.policy_version == PREFERENCE_POLICY_VERSION:
        return preference

    preference.channels = cleaned
    preference.policy_version = PREFERENCE_POLICY_VERSION
    preference.save(update_fields=["channels", "policy_version", "updated_at"])

    def _log() -> None:
        log_event(
            "user.notification_preferences.updated",
            actor=actor_from_user(user),
            target=AuditTarget(
                target_type="notification.preference",
                target_id=str(user.pk),
                target_label="notification preferences",
            ),
            before={"channels": before},
            after={"channels": cleaned, "policyVersion": PREFERENCE_POLICY_VERSION},
            outcome=AuditEvent.Outcome.SUCCESS,
            source="view",
            channel="notifications",
        )

    transaction.on_commit(_log)
    return preference


# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #


def preference_payload(user) -> dict[str, Any]:
    """The settings page's props: the catalog, the reader's answers, the locks.

    The whole matrix is sent, locked cells included, because a switch that is
    simply missing reads as a channel that does not exist. Locked cells arrive
    on, disabled, and carrying the sentence that says why. Push providers that
    are not enabled for this deployment are omitted entirely.
    """
    preference = get_preference(user)
    matrix = resolved_matrix(user)
    channels = visible_channels()
    configurable = tuple(channel.key for channel in channels if channel.configurable)
    return {
        "channels": [
            {
                "key": channel.key,
                "label": channel.label,
                "description": channel.description,
                "configurable": channel.configurable,
                "lockedReason": channel.locked_reason,
            }
            for channel in channels
        ],
        "categories": [
            {
                "key": category.key,
                "label": category.label,
                "description": category.description,
                "mandatory": category.mandatory,
                "mandatoryReason": category.mandatory_reason,
                "channels": [
                    {
                        "key": channel.key,
                        "field": field_name(channel.key, category.key),
                        "enabled": matrix[channel.key][category.key],
                        "locked": is_locked(category.key, channel.key),
                        "lockedReason": lock_reason(category.key, channel.key),
                        "defaultEnabled": category_default(category.key, channel.key),
                    }
                    for channel in channels
                ],
            }
            for category in CATEGORY_DEFINITIONS
        ],
        "policy": {
            "version": PREFERENCE_POLICY_VERSION,
            "savedVersion": preference.policy_version,
            # True when the catalog moved on since this reader last saved:
            # categories were added, or a default changed. Nothing has been
            # reset — the page simply says the list is longer than it was.
            "outdated": preference.policy_version < PREFERENCE_POLICY_VERSION,
            "updatedAt": preference.updated_at.isoformat()
            if preference.updated_at
            else None,
            "configurableChannels": list(configurable),
        },
    }
