"""Form validation for notification mutations.

The only thing a client may say about somebody else's notification is nothing,
so these forms are deliberately small: an action from a fixed set, and the
list filters to restore afterwards. The notification itself is always looked
up through the signed-in reader's own queryset, never from posted data.
"""

from __future__ import annotations

from django import forms

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
