"""Quick Access click analytics.

Which launchers an office actually opens is useful to whoever administers the
panel, and worth almost nothing at the cost of a slower click. So the whole
feature is built around two rules:

* **It never blocks navigation.** The browser fires the beacon and follows the
  link; the endpoint answers ``204`` and the answer is never waited on. A
  failure here is invisible by design — a lost count, not a lost click.
* **It never records a destination.** The row names the link by stable key.
  No URL, no query string, no fragment, so an external tool's session token or
  tenant identifier cannot arrive here by way of a click. See
  :class:`apps.web.models.QuickAccessLinkClick`.

The key a browser posts is untrusted, so it is resolved through the reader's
*own* visible links: a click can only ever be recorded against a launcher that
reader could actually see. An unknown, hidden, or out-of-audience key records
nothing, and the caller cannot tell which — confirming that a stable key exists
is a disclosure across an audience boundary.

Recording is optional at the operator level: ``QUICK_ACCESS_CLICK_ANALYTICS``
turns it off and the endpoint keeps answering ``204``.
"""

from __future__ import annotations

from django.conf import settings

from apps.user.models import User
from apps.web.models import QuickAccessLink, QuickAccessLinkClick
from apps.web.quick_access.resolution import visible_links_for

#: A stable key is a slug of at most 64 characters. Anything longer is not a
#: key, and is refused before it reaches a query.
MAX_STABLE_KEY_LENGTH = 64


def analytics_enabled() -> bool:
    return bool(getattr(settings, "QUICK_ACCESS_CLICK_ANALYTICS", True))


def record_click(user: User, stable_key: str) -> bool:
    """Record that ``user`` opened the launcher named by ``stable_key``.

    Returns whether a row was written, for tests. Callers must not turn that
    into a response distinction: the endpoint answers the same either way.
    """
    if not analytics_enabled():
        return False
    stable_key = (stable_key or "").strip()
    if not stable_key or len(stable_key) > MAX_STABLE_KEY_LENGTH:
        return False

    link: QuickAccessLink | None = (
        visible_links_for(user).filter(stable_key=stable_key).first()
    )
    if link is None:
        return False

    QuickAccessLinkClick.objects.create(
        link=link,
        link_stable_key=link.stable_key,
        user=user,
        office=user.office,
        destination_type=link.destination_type,
    )
    return True
