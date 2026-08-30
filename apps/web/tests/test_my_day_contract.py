"""The agenda contract, its ordering, and the timezone rules underneath it.

These are pure-Python tests on purpose: the merge, the bucketing, and the
day-boundary arithmetic are where this widget is most likely to be quietly
wrong, and they should be provable without a database in the way.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.web.my_day.contract import (
    AgendaEvent,
    EventPriority,
    EventSource,
    EventStatus,
    EventVisibility,
)
from apps.web.my_day.ordering import Bucket, build_agenda, dedupe, is_overdue
from apps.web.my_day.payloads import day_label, serialize_agenda, time_label

UTC = ZoneInfo("UTC")
NY = ZoneInfo("America/New_York")


def event(
    identifier: str = "e1",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    all_day: bool = False,
    local_date: date | None = None,
    dedupe_key: str | None = None,
    priority: int = EventPriority.NORMAL,
    **extra,
) -> AgendaEvent:
    return AgendaEvent(
        id=identifier,
        dedupe_key=dedupe_key or identifier,
        source=EventSource.MEETING,
        title=extra.pop("title", "Something"),
        start_at=start or datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        end_at=end,
        all_day=all_day,
        local_date=local_date,
        priority=priority,
        **extra,
    )


# --------------------------------------------------------------------------- #
# The contract refuses what must never reach the wire
# --------------------------------------------------------------------------- #


def test_a_cancelled_event_cannot_be_constructed():
    """Unrepresentable rather than filtered.

    Every source would otherwise have to remember to exclude one, and a
    cancelled meeting that still renders is what this widget gets blamed for.
    """
    with pytest.raises(ValueError, match="cancelled"):
        event(status=EventStatus.CANCELLED)


def test_a_private_event_cannot_be_constructed():
    with pytest.raises(ValueError, match="private"):
        event(visibility=EventVisibility.PRIVATE)


def test_a_naive_start_is_refused():
    """A naive datetime has no instant, so its position would depend on
    whichever timezone happened to be active when it was rendered."""
    with pytest.raises(ValueError, match="aware"):
        event(start=datetime(2026, 3, 2, 9, 0))


def test_an_event_ending_before_it_starts_is_refused():
    with pytest.raises(ValueError, match="ends before"):
        event(
            start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
            end=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
        )


def test_an_all_day_event_needs_the_date_it_belongs_to():
    with pytest.raises(ValueError, match="all-day"):
        event(all_day=True)


def test_an_unknown_source_is_refused():
    with pytest.raises(ValueError, match="source"):
        AgendaEvent(
            id="x",
            dedupe_key="x",
            source="astrology",
            title="Mercury retrograde",
            start_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        )


def test_a_cta_destination_needs_a_label():
    with pytest.raises(ValueError, match="label"):
        event(cta_href="/somewhere")


# --------------------------------------------------------------------------- #
# Overdue never sorts into the future
# --------------------------------------------------------------------------- #


def test_past_due_work_stays_in_its_own_bucket():
    """The rule the whole module exists for.

    Filing a missed 9am among tomorrow's appointments hides the only row that
    needed action.
    """
    now = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    missed = event("missed", start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
    later = event("later", start=datetime(2026, 3, 2, 15, 0, tzinfo=UTC))
    tomorrow = event("tomorrow", start=datetime(2026, 3, 3, 9, 0, tzinfo=UTC))

    agenda = build_agenda([tomorrow, later, missed], now=now, tz=UTC)

    assert [e.id for e in agenda.overdue] == ["missed"]
    assert [e.id for e in agenda.today] == ["later"]
    assert [e.id for e in agenda.upcoming] == ["tomorrow"]


def test_an_event_in_progress_is_not_overdue():
    """Its end has not passed, so it is happening — not missed."""
    now = datetime(2026, 3, 2, 9, 30, tzinfo=UTC)
    running = event(
        start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        end=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
    )
    assert is_overdue(running, now=now, tz=UTC) is False


def test_an_all_day_event_is_not_overdue_until_its_date_has_passed():
    """ "All day today" is not late at 9am.

    Comparing a synthesized midnight against "now" would claim otherwise.
    """
    now = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
    today = event(all_day=True, local_date=date(2026, 3, 2))
    yesterday = event("y", all_day=True, local_date=date(2026, 3, 1))

    assert is_overdue(today, now=now, tz=UTC) is False
    assert is_overdue(yesterday, now=now, tz=UTC) is True


def test_priority_never_reorders_a_chronology():
    """An agenda sorted by importance stops being an agenda."""
    now = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    low_early = event(
        "early",
        start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        priority=EventPriority.LOW,
    )
    critical_late = event(
        "late",
        start=datetime(2026, 3, 2, 17, 0, tzinfo=UTC),
        priority=EventPriority.CRITICAL,
    )

    agenda = build_agenda([critical_late, low_early], now=now, tz=UTC)
    assert [e.id for e in agenda.today] == ["early", "late"]


def test_an_all_day_event_leads_its_own_date():
    now = datetime(2026, 3, 2, 6, 0, tzinfo=UTC)
    timed = event("timed", start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
    whole = event(
        "whole",
        start=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
        all_day=True,
        local_date=date(2026, 3, 2),
    )

    agenda = build_agenda([timed, whole], now=now, tz=UTC)
    assert [e.id for e in agenda.today] == ["whole", "timed"]


# --------------------------------------------------------------------------- #
# Deduplication
# --------------------------------------------------------------------------- #


def test_the_same_appointment_from_two_sources_appears_once():
    """What stops enabling a calendar integration doubling somebody's day."""
    hub = event("hub", dedupe_key="meeting:42")
    mirror = event("outlook", dedupe_key="meeting:42")

    assert [e.id for e in dedupe([hub, mirror])] == ["hub"]


def test_deduplication_survives_the_bucket_split():
    now = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    a = event("a", dedupe_key="same", start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
    b = event("b", dedupe_key="same", start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC))

    agenda = build_agenda([a, b], now=now, tz=UTC)
    assert agenda.total == 1


# --------------------------------------------------------------------------- #
# Timezone, DST, and midnight boundaries
# --------------------------------------------------------------------------- #


def test_the_reader_timezone_decides_which_day_a_row_belongs_to():
    """22:00 UTC on the 2nd is 17:00 on the 2nd in New York — same day there,
    but an event at 02:00 UTC on the 3rd is still the 2nd for that reader."""
    now = datetime(2026, 3, 2, 20, 0, tzinfo=UTC)  # 15:00 in New York
    late = event("late", start=datetime(2026, 3, 3, 2, 0, tzinfo=UTC))

    in_ny = build_agenda([late], now=now, tz=NY)
    in_utc = build_agenda([late], now=now, tz=UTC)

    assert [e.id for e in in_ny.today] == ["late"]
    assert [e.id for e in in_utc.upcoming] == ["late"]


def test_a_spring_forward_day_keeps_its_chronology():
    """2026-03-08 loses 02:00–03:00 in New York.

    The hour that does not exist must not reorder the rows around it.
    """
    now = datetime(2026, 3, 8, 6, 0, tzinfo=UTC)  # 01:00 EST
    before = event("before", start=datetime(2026, 3, 8, 6, 30, tzinfo=UTC))
    after = event("after", start=datetime(2026, 3, 8, 7, 30, tzinfo=UTC))

    agenda = build_agenda([after, before], now=now, tz=NY)
    assert [e.id for e in agenda.today] == ["before", "after"]
    # 01:30 EST then 03:30 EDT — the wall clock skips, the order does not.
    assert time_label(before, tz=NY) == "1:30 a.m."
    assert time_label(after, tz=NY) == "3:30 a.m."


def test_a_fall_back_day_does_not_duplicate_or_reorder():
    """2026-11-01 repeats 01:00–02:00 in New York."""
    now = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    first = event("first", start=datetime(2026, 11, 1, 5, 30, tzinfo=UTC))
    second = event("second", start=datetime(2026, 11, 1, 6, 30, tzinfo=UTC))

    agenda = build_agenda([second, first], now=now, tz=NY)
    assert [e.id for e in agenda.today] == ["first", "second"]
    # Both render 1:30 am — the same wall clock, an hour apart in real time.
    assert time_label(first, tz=NY) == "1:30 a.m."
    assert time_label(second, tz=NY) == "1:30 a.m."


def test_just_before_midnight_is_today_and_just_after_is_tomorrow():
    now = datetime(2026, 3, 2, 23, 0, tzinfo=UTC)
    tonight = event("tonight", start=datetime(2026, 3, 2, 23, 59, tzinfo=UTC))
    midnight = event("midnight", start=datetime(2026, 3, 3, 0, 0, tzinfo=UTC))

    agenda = build_agenda([tonight, midnight], now=now, tz=UTC)
    assert [e.id for e in agenda.today] == ["tonight"]
    assert [e.id for e in agenda.upcoming] == ["midnight"]


def test_an_all_day_row_keeps_its_date_for_a_reader_in_another_zone():
    """The bug this contract's ``local_date`` exists to prevent: an all-day
    Friday stored as midnight and converted west becomes Thursday night."""
    now = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    friday = event(
        all_day=True,
        local_date=date(2026, 3, 6),
        start=datetime(2026, 3, 6, 0, 0, tzinfo=UTC),
    )

    agenda = build_agenda([friday], now=now, tz=NY)
    assert [e.id for e in agenda.upcoming] == ["e1"]
    assert day_label(friday, now=now, tz=NY) == "Fri, Mar 6"


# --------------------------------------------------------------------------- #
# Caps and labels
# --------------------------------------------------------------------------- #


def test_a_cap_drops_distant_rows_before_missed_ones():
    now = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    events = [
        event("missed", start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC)),
        event("today", start=datetime(2026, 3, 2, 15, 0, tzinfo=UTC)),
        event("soon", start=datetime(2026, 3, 3, 9, 0, tzinfo=UTC)),
        event("later", start=datetime(2026, 3, 4, 9, 0, tzinfo=UTC)),
    ]

    capped = build_agenda(events, now=now, tz=UTC).capped(2)

    assert [e.id for e in capped.overdue] == ["missed"]
    assert [e.id for e in capped.today] == ["today"]
    assert capped.upcoming == []


def test_the_total_stays_uncapped_so_the_more_count_is_honest():
    now = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    events = [
        event(f"e{i}", start=datetime(2026, 3, 2, 13 + i, 0, tzinfo=UTC))
        for i in range(5)
    ]
    agenda = build_agenda(events, now=now, tz=UTC)

    payload = serialize_agenda(
        agenda.capped(2),
        now=now,
        tz=UTC,
        total=agenda.total,
        view_all_href="/calendar",
        view_all_label="View full calendar",
    )
    assert payload["total"] == 5
    assert len(payload["today"]) == 2


def test_an_all_day_row_says_so_rather_than_showing_midnight():
    whole = event(all_day=True, local_date=date(2026, 3, 2))
    assert time_label(whole, tz=UTC) == "All day"


def test_a_span_renders_both_ends_and_an_instant_renders_one():
    span = event(
        start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        end=datetime(2026, 3, 2, 10, 30, tzinfo=UTC),
    )
    instant = event(start=datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
    assert time_label(span, tz=UTC) == "9:00 a.m. – 10:30 a.m."
    assert time_label(instant, tz=UTC) == "9:00 a.m."


def test_day_labels_are_relative_near_today_and_dated_further_out():
    now = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    assert day_label(event(start=now), now=now, tz=UTC) == "Today"
    assert (
        day_label(event(start=now + timedelta(days=1)), now=now, tz=UTC) == "Tomorrow"
    )
    assert (
        day_label(event(start=now - timedelta(days=1)), now=now, tz=UTC) == "Yesterday"
    )
    assert (
        day_label(event(start=now + timedelta(days=4)), now=now, tz=UTC) == "Fri, Mar 6"
    )


def test_bucket_names_are_the_documented_three():
    assert (Bucket.OVERDUE, Bucket.TODAY, Bucket.UPCOMING) == (
        "overdue",
        "today",
        "upcoming",
    )
