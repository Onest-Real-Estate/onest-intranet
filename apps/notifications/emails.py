"""Rendering one notification into an email that carries as little as possible.

The message body is the *fixed producer title*, the category it belongs to, and
a link back into the hub. It is deliberately not a copy of the notification:

* **No source detail.** What the notification is about is resolved from the
  owning domain for a signed-in reader (:mod:`apps.notifications.sources`).
  Mail leaves the perimeter, is retained by mail providers, and is readable by
  anyone holding the mailbox — so the client, property, document, or person the
  notification concerns never appears in it.
* **No file links.** Sensitive files are served from protected storage behind
  short-lived, authorized access. A URL in an email outlives the authorization
  that produced it, so mail links only ever point at an in-app path, which
  re-authenticates and re-authorizes on arrival.
* **No off-site destinations.** :func:`absolute_url` refuses anything that is
  not a rooted path on this deployment, so a stored action that somehow stopped
  reversing degrades to the notification centre rather than to a guessed host.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse

from apps.notifications.actions import resolve_action_href
from apps.notifications.categories import CATEGORY_BY_KEY
from apps.notifications.models import Notification

SUBJECT_TEMPLATE = "notifications/email/notification_subject.txt"
TEXT_TEMPLATE = "notifications/email/notification_body.txt"
HTML_TEMPLATE = "notifications/email/notification_body.html"


def absolute_url(path: str) -> str:
    """Make an in-app path absolute, or return ``""``.

    Only a single-slash-rooted path is accepted. ``//host/x`` is a
    protocol-relative URL to somebody else's server and is refused, as is any
    absolute URL a caller tries to pass straight through.
    """
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return ""
    base = str(getattr(settings, "SITE_BASE_URL", "")).rstrip("/")
    return f"{base}{path}"


def _reverse_or_empty(route_name: str) -> str:
    try:
        return reverse(route_name)
    except NoReverseMatch:  # pragma: no cover - route removal is a deploy bug
        return ""


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text_body: str
    html_body: str
    action_url: str
    centre_url: str


def render_notification_email(notification: Notification, recipient) -> RenderedEmail:
    """Build the message for one notification and one recipient."""
    centre_url = absolute_url(_reverse_or_empty("notifications"))
    preferences_url = absolute_url(_reverse_or_empty("notification_preferences"))
    action_url = ""
    if notification.action_key:
        action_url = absolute_url(
            resolve_action_href(notification.action_key, notification.action_args)
        )
    # A destination that no longer reverses is not a reason to withhold the
    # message; the centre always exists and the row is waiting in it.
    action_url = action_url or centre_url

    category = CATEGORY_BY_KEY.get(notification.notification_type)
    context = {
        "greeting": f"Hi {recipient.preferred_display_name()},",
        "title": notification.title,
        "category_label": category.label if category else "Notifications",
        "mandatory": notification.is_mandatory,
        # Mandatory work is mandatory whatever the category says, so the footer
        # follows the delivery rather than the category.
        "can_unsubscribe": not notification.is_mandatory
        and not (category.mandatory if category else True),
        "action_url": action_url,
        "centre_url": centre_url,
        "preferences_url": preferences_url,
    }
    return RenderedEmail(
        # Subjects are single-line by definition; a header with a newline in it
        # is a header-injection bug, and producer copy is not trusted to be
        # single-line just because it usually is.
        subject=" ".join(render_to_string(SUBJECT_TEMPLATE, context).split()),
        text_body=render_to_string(TEXT_TEMPLATE, context),
        html_body=render_to_string(HTML_TEMPLATE, context),
        action_url=action_url,
        centre_url=centre_url,
    )
