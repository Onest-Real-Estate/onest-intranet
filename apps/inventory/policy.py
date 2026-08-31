"""Reservation policy: horizon, duration, open days, cancel cutoff.

Office hours come from ``Office.office_hours`` when configured. An empty hours
list means the office has not published a schedule — date validation still
runs, but open-day checks are skipped.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

#: Pickup must fall within this many calendar days from "today" in the
#: active timezone.
MAX_HORIZON_DAYS = 90

#: Inclusive calendar length of the hold (pickup day through return day).
MAX_DURATION_DAYS = 14

#: Agents may cancel until this many hours before ``starts_at``.
CANCEL_CUTOFF_HOURS = 24

WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def local_today() -> date:
    return timezone.localdate()


def calendar_duration_days(pickup: date, return_day: date) -> int:
    """Inclusive day count for a pickup/return pair."""
    return (return_day - pickup).days + 1


def validate_horizon_and_duration(
    pickup: date, return_day: date, *, today: date | None = None
) -> list[str]:
    errors: list[str] = []
    now = today or local_today()
    if pickup < now:
        errors.append(str(_("Pickup must be today or a future date.")))
    if pickup > now + timedelta(days=MAX_HORIZON_DAYS):
        errors.append(
            str(_("Pickup must be within %(days)s days.") % {"days": MAX_HORIZON_DAYS})
        )
    duration = calendar_duration_days(pickup, return_day)
    if duration > MAX_DURATION_DAYS:
        errors.append(
            str(
                _("Reservations may not exceed %(days)s days.")
                % {"days": MAX_DURATION_DAYS}
            )
        )
    return errors


def _open_weekdays(office_hours: list[dict[str, Any]] | None) -> frozenset[str] | None:
    if not office_hours:
        return None
    open_days: set[str] = set()
    for entry in office_hours:
        day = str(entry.get("day") or "").strip().lower()
        if day in WEEKDAY_KEYS:
            open_days.add(day)
    return frozenset(open_days) if open_days else None


def validate_office_open_days(
    office_hours: list[dict[str, Any]] | None,
    pickup: date,
    return_day: date,
) -> list[str]:
    """Reject when pickup or return falls on a configured closed day.

    Intermediate closed days inside a multi-day hold are allowed — the item
    stays reserved across the weekend; only the handoff days must be open.
    """
    open_days = _open_weekdays(office_hours)
    if open_days is None:
        return []

    errors: list[str] = []
    pickup_key = WEEKDAY_KEYS[pickup.weekday()]
    return_key = WEEKDAY_KEYS[return_day.weekday()]
    if pickup_key not in open_days:
        errors.append(str(_("The office is closed on the pickup date.")))
    if return_key not in open_days:
        errors.append(str(_("The office is closed on the return date.")))
    return errors


def cancel_cutoff_at(starts_at: datetime) -> datetime:
    return starts_at - timedelta(hours=CANCEL_CUTOFF_HOURS)


def agent_may_cancel(
    *, status: str, starts_at: datetime, now: datetime | None = None
) -> bool:
    from apps.inventory.reservation_taxonomy import AGENT_CANCELABLE_STATES

    if status not in AGENT_CANCELABLE_STATES:
        return False
    moment = now or timezone.now()
    return moment < cancel_cutoff_at(starts_at)


def initial_status(*, requires_approval: bool) -> str:
    from apps.inventory.reservation_taxonomy import ReservationStatus

    if requires_approval:
        return ReservationStatus.REQUESTED
    return ReservationStatus.CONFIRMED


def terms_summary(*, requires_approval: bool) -> dict[str, object]:
    """Authoritative terms returned with availability previews."""
    return {
        "requiresApproval": requires_approval,
        "autoConfirm": not requires_approval,
        "maxHorizonDays": MAX_HORIZON_DAYS,
        "maxDurationDays": MAX_DURATION_DAYS,
        "cancelCutoffHours": CANCEL_CUTOFF_HOURS,
        "approvalLabel": (
            str(_("Office approval required before pickup."))
            if requires_approval
            else str(_("This item confirms automatically when available."))
        ),
        "cancelPolicyLabel": str(
            _("You can cancel until %(hours)s hours before pickup.")
            % {"hours": CANCEL_CUTOFF_HOURS}
        ),
    }
