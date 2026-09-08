"""Source isolation, scope, and the query cost of the agenda.

The behaviours under test are the ones a dashboard widget gets wrong in
production rather than in review: one module breaking and taking the card with
it, another reader's work leaking in, and a feed that quietly costs a query per
row.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.operational_tasks import services
from apps.operational_tasks.taxonomy import TaskCategory, TaskPriority, TaskStatus
from apps.operational_tasks.tests.test_scope import admin_actor, office, person
from apps.user.services.role_assignments import get_effective_access
from apps.web.dashboard.envelope import WidgetStatus
from apps.web.my_day import day_for_user
from apps.web.my_day.contract import (
    AgendaEvent,
    EventSource,
    EventSourceContext,
)
from apps.web.my_day.registry import (
    EVENT_SOURCE_DEFINITIONS,
    EventSourceDefinition,
    collect_events,
)

UTC = ZoneInfo("UTC")


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def context_for(user, *, now=None):
    now = now or timezone.now()
    return EventSourceContext(
        user=user,
        access=get_effective_access(user),
        now=now,
        window_start=now - timedelta(days=1),
        window_end=now + timedelta(days=7),
        timezone=UTC,
    )


def sample_event(identifier: str) -> AgendaEvent:
    return AgendaEvent(
        id=identifier,
        dedupe_key=identifier,
        source=EventSource.MEETING,
        title="Sample",
        start_at=timezone.now(),
    )


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_no_unbuilt_source_claims_to_be_available():
    """An available source with no collector would be a promise nothing keeps."""
    for definition in EVENT_SOURCE_DEFINITIONS:
        if definition.available:
            assert definition.collector is not None, definition.key


def test_source_keys_are_unique():
    keys = [definition.key for definition in EVENT_SOURCE_DEFINITIONS]
    assert len(keys) == len(set(keys))


def test_the_microsoft_calendar_source_is_registered_but_dark():
    """Listing it is not a claim that anything synchronizes.

    An empty agenda must never be readable as "Outlook says you are free".
    """
    outlook = next(
        d for d in EVENT_SOURCE_DEFINITIONS if d.key == EventSource.MICROSOFT_CALENDAR
    )
    assert outlook.available is False
    assert outlook.collector is None


# --------------------------------------------------------------------------- #
# Failure isolation
# --------------------------------------------------------------------------- #


def test_a_failing_source_does_not_erase_a_working_one(seeded, monkeypatch):
    """The acceptance criterion, tested at the seam that decides it."""

    def explode(context):
        raise RuntimeError("calendar service is down")

    def works(context):
        return [sample_event("survivor")]

    monkeypatch.setattr(
        "apps.web.my_day.registry.EVENT_SOURCE_DEFINITIONS",
        (
            EventSourceDefinition(key="broken", collector=explode, available=True),
            EventSourceDefinition(key="fine", collector=works, available=True),
        ),
    )

    events, partial_failure = collect_events(
        context_for(person("a@e.com", "fairfax-va"))
    )

    assert [e.id for e in events] == ["survivor"]
    assert partial_failure is True


def test_an_unavailable_source_is_never_called(seeded, monkeypatch):
    called: list[str] = []

    def collector(context):
        called.append("yes")
        return []

    monkeypatch.setattr(
        "apps.web.my_day.registry.EVENT_SOURCE_DEFINITIONS",
        (EventSourceDefinition(key="dark", collector=collector, available=False),),
    )

    collect_events(context_for(person("a@e.com", "fairfax-va")))
    assert called == []


def test_a_total_failure_says_so_rather_than_claiming_the_day_is_clear(
    seeded, monkeypatch
):
    """ "Nothing scheduled" and "we could not look" are different sentences."""

    def explode(context):
        raise RuntimeError("down")

    monkeypatch.setattr(
        "apps.web.my_day.registry.EVENT_SOURCE_DEFINITIONS",
        (EventSourceDefinition(key="broken", collector=explode, available=True),),
    )
    user = person("a@e.com", "fairfax-va")
    now = timezone.now()

    result = day_for_user(
        user,
        get_effective_access(user),
        now=now,
        tz=UTC,
        window_start=now,
    )

    assert result.status == WidgetStatus.UNAVAILABLE
    assert result.unavailable is not None
    assert result.unavailable.retryable is True


def test_a_partial_failure_is_flagged_but_keeps_the_rows(seeded, monkeypatch):
    def explode(context):
        raise RuntimeError("down")

    def works(context):
        return [sample_event("kept")]

    monkeypatch.setattr(
        "apps.web.my_day.registry.EVENT_SOURCE_DEFINITIONS",
        (
            EventSourceDefinition(key="broken", collector=explode, available=True),
            EventSourceDefinition(key="fine", collector=works, available=True),
        ),
    )
    user = person("a@e.com", "fairfax-va")
    now = timezone.now()

    result = day_for_user(
        user, get_effective_access(user), now=now, tz=UTC, window_start=now
    )

    assert result.status == WidgetStatus.READY
    assert result.meta["partialFailure"] is True
    assert result.data is not None
    assert result.data["total"] == 1


def test_the_failure_note_never_names_the_source(seeded, monkeypatch):
    """Naming it would tell the reader which calendars they are subject to."""

    def explode(context):
        raise RuntimeError("outlook credentials rejected for alice@example.com")

    def works(context):
        return [sample_event("kept")]

    monkeypatch.setattr(
        "apps.web.my_day.registry.EVENT_SOURCE_DEFINITIONS",
        (
            EventSourceDefinition(key="secret", collector=explode, available=True),
            EventSourceDefinition(key="fine", collector=works, available=True),
        ),
    )
    user = person("a@e.com", "fairfax-va")
    now = timezone.now()

    result = day_for_user(
        user, get_effective_access(user), now=now, tz=UTC, window_start=now
    )

    serialized = str(result.meta) + str(result.data)
    assert "secret" not in serialized
    assert "alice@example.com" not in serialized


# --------------------------------------------------------------------------- #
# Scope: only this reader's own obligations
# --------------------------------------------------------------------------- #


def make_task(creator, assignee, *, title, due_at, status=TaskStatus.OPEN):
    task = services.create_task(
        actor=admin_actor(creator),
        office=office("fairfax-va"),
        category=TaskCategory.TOOL_SETUP,
        title=title,
        priority=TaskPriority.NORMAL,
        assignee=assignee,
        due_at=due_at,
    )
    if status != TaskStatus.OPEN:
        services.transition(
            actor=admin_actor(creator), task=task, to_status=TaskStatus.IN_PROGRESS
        )
        if status != TaskStatus.IN_PROGRESS:
            services.transition(actor=admin_actor(creator), task=task, to_status=status)
    return task


def titles(user, *, now=None):
    from apps.operational_tasks.agenda import collect_task_events

    return [e.title for e in collect_task_events(context_for(user, now=now))]


def test_only_work_assigned_to_this_reader_reaches_their_day(seeded):
    """A manager who can *see* forty tasks does not have forty appointments."""
    from apps.operational_tasks.tests.test_scope import assign_role

    creator = person("creator@e.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    mine = person("mine@e.com", "fairfax-va")
    theirs = person("theirs@e.com", "fairfax-va")
    soon = timezone.now() + timedelta(hours=2)

    make_task(creator, mine, title="Mine", due_at=soon)
    make_task(creator, theirs, title="Theirs", due_at=soon)

    assert titles(mine) == ["Mine"]


def test_an_undated_task_is_a_queue_item_not_an_appointment(seeded):
    from apps.operational_tasks.tests.test_scope import assign_role

    creator = person("creator@e.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    mine = person("mine@e.com", "fairfax-va")

    make_task(creator, mine, title="Dated", due_at=timezone.now() + timedelta(hours=2))
    make_task(creator, mine, title="Undated", due_at=None)

    assert titles(mine) == ["Dated"]


def test_blocked_and_terminal_work_leaves_the_agenda(seeded):
    """A blocked task is not something its assignee can act on today."""
    from apps.operational_tasks.tests.test_scope import assign_role

    creator = person("creator@e.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    mine = person("mine@e.com", "fairfax-va")
    soon = timezone.now() + timedelta(hours=2)

    make_task(creator, mine, title="Open", due_at=soon)
    blocked = make_task(creator, mine, title="Blocked", due_at=soon)
    services.transition(
        actor=admin_actor(creator),
        task=blocked,
        to_status=TaskStatus.IN_PROGRESS,
    )
    services.transition(
        actor=admin_actor(creator),
        task=blocked,
        to_status=TaskStatus.BLOCKED,
        note="Waiting on the vendor.",
    )

    assert titles(mine) == ["Open"]


def test_the_cta_points_at_the_record_that_re_authorizes(seeded):
    from apps.operational_tasks.agenda import collect_task_events
    from apps.operational_tasks.tests.test_scope import assign_role

    creator = person("creator@e.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    mine = person("mine@e.com", "fairfax-va")
    task = make_task(
        creator, mine, title="Mine", due_at=timezone.now() + timedelta(hours=2)
    )

    [row] = collect_task_events(context_for(mine))
    assert row.cta_href == f"/operations/tasks/{task.public_id}"


def test_the_agenda_costs_one_query_however_many_rows(
    seeded, django_assert_num_queries
):
    """A per-row office lookup would make a busy day quietly expensive."""
    from apps.operational_tasks.agenda import collect_task_events
    from apps.operational_tasks.tests.test_scope import assign_role

    creator = person("creator@e.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    mine = person("mine@e.com", "fairfax-va")
    for index in range(6):
        make_task(
            creator,
            mine,
            title=f"Task {index}",
            due_at=timezone.now() + timedelta(hours=index + 1),
        )

    context = context_for(mine)
    with django_assert_num_queries(1):
        rows = collect_task_events(context)
        # The office name is read here; `select_related` is what keeps it free.
        [row.location for row in rows]
    assert len(rows) == 6


# --------------------------------------------------------------------------- #
# The timezone seam, end to end through the real provider
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_provider_buckets_against_the_application_timezone(seeded):
    """The whole seam: settings → `user_timezone` → day boundary → labels.

    A task at 21:00 New York time is 02:00 UTC the next day. Under a
    New York application timezone it belongs to *today*; the same instant read
    in UTC belongs to tomorrow. Getting this wrong is invisible in a UTC-only
    test suite and obvious to anybody east or west of the server.
    """
    from django.test import override_settings

    from apps.operational_tasks.tests.test_scope import assign_role
    from apps.web.dashboard.providers import DashboardContext, my_day

    creator = person("creator@e.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    mine = person("mine@e.com", "fairfax-va")

    # 2026-03-02 21:00 in New York — still the 2nd there, already the 3rd in UTC.
    evening_ny = datetime(2026, 3, 3, 2, 0, tzinfo=UTC)
    now = datetime(2026, 3, 2, 20, 0, tzinfo=UTC)  # 15:00 in New York
    make_task(creator, mine, title="This evening", due_at=evening_ny)

    context = DashboardContext(
        user=mine, access=get_effective_access(mine), now=now, feed_limit=6
    )

    with override_settings(TIME_ZONE="America/New_York"):
        result = my_day(context)
    assert result.data is not None
    assert [row["title"] for row in result.data["today"]] == ["This evening"]
    assert result.data["timezone"] == "America/New_York"
    assert result.data["today"][0]["timeLabel"] == "9:00 p.m."

    with override_settings(TIME_ZONE="UTC"):
        result = my_day(context)
    assert result.data is not None
    # Same instant, different reader timezone: now it is tomorrow's problem.
    assert result.data["today"] == []
    assert [row["title"] for row in result.data["upcoming"]] == ["This evening"]


@pytest.mark.django_db
def test_the_provider_caps_the_feed_but_keeps_the_total_honest(seeded):
    from apps.operational_tasks.tests.test_scope import assign_role
    from apps.web.dashboard.providers import DashboardContext, my_day

    creator = person("creator@e.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    mine = person("mine@e.com", "fairfax-va")
    now = timezone.now()
    for index in range(9):
        make_task(
            creator,
            mine,
            title=f"Task {index}",
            due_at=now + timedelta(hours=index + 1),
        )

    result = my_day(
        DashboardContext(
            user=mine, access=get_effective_access(mine), now=now, feed_limit=6
        )
    )

    assert result.data is not None
    shown = sum(len(result.data[bucket]) for bucket in ("overdue", "today", "upcoming"))
    assert shown == 6
    assert result.data["total"] == 9
    assert result.meta["truncated"] is True


@pytest.mark.django_db
def test_a_clear_day_is_empty_not_unavailable(seeded):
    """ "Nothing scheduled" and "this module does not exist" are different
    sentences. The placeholder used to say the second one to everybody."""
    from apps.web.dashboard.providers import DashboardContext, my_day

    mine = person("mine@e.com", "fairfax-va")
    result = my_day(
        DashboardContext(
            user=mine,
            access=get_effective_access(mine),
            now=timezone.now(),
            feed_limit=6,
        )
    )

    assert result.status == WidgetStatus.EMPTY
    assert result.empty_state is not None
    assert result.empty_state.title == "Nothing scheduled"
