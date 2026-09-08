"""Timezone-aware "today" for the dashboard.

The greeting and the date used to be computed from the browser clock in
``DashboardGreeting.tsx``, which made them a property of the reader's laptop
rather than of the brokerage. An agent travelling west saw "Good evening" on a
page whose date ranges had been computed in the application timezone — the two
halves of the same screen disagreed.

Everything time-shaped now derives from :func:`user_timezone`, so the greeting,
the date label, and every provider's day boundary agree by construction.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo

from django.utils import formats, timezone

#: Hour boundaries for the salutation, in the user's timezone.
MORNING_ENDS_AT = 12
AFTERNOON_ENDS_AT = 17


def user_timezone(user) -> tzinfo:
    """The timezone this user's dashboard is expressed in.

    Today that is the application timezone for everyone: there is no per-user
    or per-office timezone field, and inventing one from an office's state code
    would be a guess. This function is the single seam — when a configured
    timezone lands on the user or their office, it changes here and every
    caller follows.
    """
    return timezone.get_current_timezone()


def local_now(user, *, at: datetime | None = None) -> datetime:
    return timezone.localtime(at or timezone.now(), user_timezone(user))


def local_today(user, *, at: datetime | None = None) -> date:
    return local_now(user, at=at).date()


def start_of_local_day(user, *, at: datetime | None = None) -> datetime:
    """Inclusive lower bound of the user's current day, as an aware datetime."""
    naive = datetime.combine(local_today(user, at=at), time.min)
    return timezone.make_aware(naive, user_timezone(user))


def end_of_local_day(user, *, at: datetime | None = None) -> datetime:
    """Exclusive upper bound of the user's current day."""
    naive = datetime.combine(local_today(user, at=at) + timedelta(days=1), time.min)
    return timezone.make_aware(naive, user_timezone(user))


def salutation(user, *, at: datetime | None = None) -> str:
    hour = local_now(user, at=at).hour
    if hour < MORNING_ENDS_AT:
        return "Good morning"
    if hour < AFTERNOON_ENDS_AT:
        return "Good afternoon"
    return "Good evening"


def first_name(user) -> str:
    """The name to greet by, never an email address.

    Falls back through display name, first name, then the local part of the
    email; greeting somebody with "Good morning, alice@onest.realestate" is
    worse than greeting them with "Good morning, alice".
    """
    display = (user.display_name or user.get_full_name() or "").strip()
    if display:
        return display.split()[0]
    return user.email.split("@")[0]


def greeting_payload(user, *, at: datetime | None = None) -> dict[str, str]:
    """Non-deferred shell prop: the salutation and date, computed server-side."""
    today = local_today(user, at=at)
    return {
        "salutation": salutation(user, at=at),
        "name": first_name(user),
        # e.g. "Wednesday, August 19" — localized through Django's formats so
        # it follows LANGUAGE_CODE rather than the browser's locale.
        "dateLabel": formats.date_format(today, "l, F j"),
        "dateIso": today.isoformat(),
        "timezone": str(user_timezone(user)),
    }
