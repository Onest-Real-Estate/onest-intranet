"""Form validation for notification mutations.

The only thing a client may say about somebody else's notification is nothing,
so these forms are deliberately small: an action from a fixed set, and the
list filters to restore afterwards. The notification itself is always looked
up through the signed-in reader's own queryset, never from posted data.
"""

from __future__ import annotations

from django import forms

from apps.notifications.categories import (
    CATEGORY_DEFINITIONS,
    CHANNEL_BY_KEY,
    CONFIGURABLE_CHANNELS,
    field_name,
    is_locked,
)

ACTION_READ = "read"
ACTION_UNREAD = "unread"
ACTION_ARCHIVE = "archive"

ACTION_CHOICES = (
    (ACTION_READ, "Mark as read"),
    (ACTION_UNREAD, "Mark as unread"),
    (ACTION_ARCHIVE, "Archive"),
)


class NotificationStateForm(forms.Form):
    action = forms.ChoiceField(choices=ACTION_CHOICES)


class NotificationPreferencesForm(forms.Form):
    """One checkbox per cell the reader is actually allowed to decide.

    The fields are built from the category registry, so a locked cell — a
    mandatory category, or a channel that is the system of record — simply has
    no field on this form. A crafted post naming one is not rejected with an
    error message; it is not a field, so it changes nothing. That is the whole
    enforcement of "mandatory notices cannot be disabled" on the write path,
    and it holds however the request was composed.
    """

    def __init__(self, data=None) -> None:
        super().__init__(data)
        for channel_key in CONFIGURABLE_CHANNELS:
            for category in CATEGORY_DEFINITIONS:
                if is_locked(category.key, channel_key):
                    continue
                self.fields[field_name(channel_key, category.key)] = forms.BooleanField(
                    required=False,
                    label=f"{category.label} — {CHANNEL_BY_KEY[channel_key].label}",
                )

    def choices(self) -> dict[str, dict[str, bool]]:
        """The submitted set, shaped the way the preference store expects."""
        chosen: dict[str, dict[str, bool]] = {}
        for channel_key in CONFIGURABLE_CHANNELS:
            for category in CATEGORY_DEFINITIONS:
                name = field_name(channel_key, category.key)
                if name not in self.fields:
                    continue
                chosen.setdefault(channel_key, {})[category.key] = bool(
                    self.cleaned_data.get(name, False)
                )
        return chosen
