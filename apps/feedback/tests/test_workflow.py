"""Submission idempotency, rate limiting, scope, note privacy, and conversion.

The rules under test, each one an acceptance criterion:

* one ticket per submission, however many times the request arrives;
* a submitter sees their own tickets and nobody else's;
* an internal note never reaches the submitter;
* conversion is idempotent and carries no file across the boundary.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditEvent
from apps.feedback import services
from apps.feedback.models import FeedbackNote, FeedbackTicket
from apps.feedback.services import ActorContext, ConcurrentUpdate, TransitionError
from apps.feedback.taxonomy import (
    FeedbackCategory,
    FeedbackPermission,
    FeedbackPriority,
    FeedbackStatus,
    FeedbackUrgency,
)
from apps.user.models import Office, UserRoleAssignment
from apps.user.services.role_assignments import get_effective_access
from apps.user.tests.test_profile import completed_user

TRIAGE = frozenset(
    {
        FeedbackPermission.VIEW,
        FeedbackPermission.TRIAGE,
        FeedbackPermission.ASSIGN,
        FeedbackPermission.NOTE,
    }
)
HOSTS = {"testserver", "localhost"}


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()
    cache.clear()


def office(slug: str = "fairfax-va") -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def actor(user, permissions=frozenset()) -> ActorContext:
    return ActorContext(user=user, permissions=frozenset(permissions))


def assign_role(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def send(
    user,
    key: str = "k-1",
    *,
    category: str = FeedbackCategory.BUG,
    summary: str = "Contracts page will not load",
    description: str = "It spins forever after I click Open.",
    urgency: str = FeedbackUrgency.SLOWING,
    page_url: str = "",
    browser_metadata: object = None,
):
    return services.submit(
        user=user,
        submission_key=key,
        category=category,
        summary=summary,
        description=description,
        urgency=urgency,
        page_url=page_url,
        browser_metadata=browser_metadata,
        allowed_hosts=HOSTS,
    )


# --------------------------------------------------------------------------- #
# Submission
# --------------------------------------------------------------------------- #


def test_anybody_signed_in_may_report_a_problem(seeded):
    """No grant required, deliberately.

    Putting a permission in front of the support form means the people most
    likely to hit a permission bug are the ones who cannot report it.
    """
    agent = person("agent@example.com")
    ticket, created = send(agent)
    assert created is True
    assert ticket.status == FeedbackStatus.NEW
    assert ticket.reference == f"FB-{ticket.pk:06d}"
    assert ticket.submitter_pk == agent.pk
    # Office is snapshotted, not read live: moving office later must not move
    # an old ticket between support queues.
    assert ticket.office == office()


def test_the_same_submission_key_never_makes_a_second_ticket(seeded):
    agent = person("agent@example.com")
    first, created_first = send(agent, key="dup")
    second, created_second = send(agent, key="dup", summary="Different text")

    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert FeedbackTicket.objects.count() == 1
    # The replay does not overwrite what was first said.
    assert second.summary == "Contracts page will not load"


def test_the_submitters_urgency_seeds_the_staff_priority(seeded):
    agent = person("agent@example.com")
    ticket, _ = send(agent, urgency=FeedbackUrgency.BLOCKING)
    assert ticket.priority == FeedbackPriority.HIGH
    # …and the original urgency is kept as what they actually said.
    assert ticket.urgency == FeedbackUrgency.BLOCKING


def test_diagnostics_are_scrubbed_on_the_way_in(seeded):
    agent = person("agent@example.com")
    ticket, _ = send(
        agent,
        page_url="/contracts?token=supersecretvalue&page=2#access_token=x",
        browser_metadata={"viewport": "1440x900", "cookies": "session=abc"},
    )
    assert ticket.page_url == "/contracts?page=2"
    assert "supersecretvalue" not in ticket.page_url
    assert ticket.browser_metadata == {"viewport": "1440x900"}


def test_a_page_url_from_another_host_refuses_the_submission(seeded):
    agent = person("agent@example.com")
    with pytest.raises(ValidationError):
        send(agent, page_url="https://evil.example/x")


def test_an_unknown_category_is_refused(seeded):
    with pytest.raises(ValidationError):
        send(person("agent@example.com"), category="nonsense")


def test_an_unknown_urgency_is_refused(seeded):
    with pytest.raises(ValidationError):
        send(person("agent@example.com"), urgency="whenever")


def test_a_summary_of_whitespace_is_not_a_summary(seeded):
    with pytest.raises(ValidationError):
        send(person("agent@example.com"), summary="  ")


def test_the_rate_limit_says_how_long_to_wait(seeded):
    """An error the reader cannot act on just becomes a support ticket about
    the support form."""
    agent = person("agent@example.com")
    for index in range(services.RATE_LIMIT_SUBMISSIONS):
        send(agent, key=f"k-{index}")

    with pytest.raises(services.RateLimited) as raised:
        send(agent, key="one-too-many")
    message = " ".join(raised.value.message_dict["form"])
    assert "minutes" in message
    assert str(services.RATE_LIMIT_SUBMISSIONS) in message


def test_a_replayed_submission_does_not_spend_rate_limit_budget(seeded):
    """Idempotency is checked before the limiter, so a browser retrying a POST
    cannot lock somebody out of the form."""
    agent = person("agent@example.com")
    for index in range(services.RATE_LIMIT_SUBMISSIONS):
        send(agent, key=f"k-{index}")
    # Replaying an existing key still returns its ticket rather than raising.
    ticket, created = send(agent, key="k-0")
    assert created is False
    assert ticket is not None


def test_submission_writes_an_audit_event_without_copying_the_body(
    seeded, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    agent = person("agent@example.com")
    with django_capture_on_commit_callbacks(execute=True):
        ticket, _ = send(agent, description="My client's SSN is 000-00-0000")

    event = AuditEvent.objects.filter(action="feedback.submitted").latest("pk")
    assert event.metadata["category"] == FeedbackCategory.BUG
    # An audit row states what happened; copying the body would make a second,
    # differently-scoped copy of content the ticket's own policy protects.
    assert "000-00-0000" not in str(event.metadata)
    assert "000-00-0000" not in str(event.after)


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #


def visible(user, can_triage: bool) -> set[str]:
    return set(
        FeedbackTicket.objects.for_reader(
            user, access=get_effective_access(user), can_triage=can_triage
        ).values_list("summary", flat=True)
    )


def test_a_submitter_sees_their_own_tickets_and_nobody_elses(seeded):
    mine = person("mine@example.com")
    theirs = person("theirs@example.com")
    send(mine, key="a", summary="Mine")
    send(theirs, key="b", summary="Theirs")

    assert visible(mine, can_triage=False) == {"Mine"}


def test_office_reach_alone_does_not_open_somebody_elses_ticket(seeded):
    """Reading another person's feedback is a granted capability, not a
    side effect of managing their office."""
    manager = person("branch@example.com")
    assign_role(manager, "branch_manager", "office", office("fairfax-va"))
    agent = person("agent@example.com")
    send(agent, key="a", summary="Agent report")

    assert visible(manager, can_triage=False) == set()
    assert visible(manager, can_triage=True) == {"Agent report"}


def test_a_triager_does_not_see_another_regions_tickets(seeded):
    manager = person("branch@example.com")
    assign_role(manager, "branch_manager", "office", office("fairfax-va"))
    local = person("local@example.com", "fairfax-va")
    remote = person("remote@example.com", "harrisburg")
    send(local, key="a", summary="Local")
    send(remote, key="b", summary="Remote")

    assert visible(manager, can_triage=True) == {"Local"}


def test_company_reach_sees_every_office(seeded):
    admin = person("admin@example.com", "onest-head-office")
    assign_role(admin, "system_admin", "company")
    send(person("a@example.com", "fairfax-va"), key="a", summary="Fairfax")
    send(person("b@example.com", "harrisburg"), key="b", summary="Harrisburg")

    assert {"Fairfax", "Harrisburg"} <= visible(admin, can_triage=True)


def test_scope_is_applied_before_counting(seeded):
    """A total is a disclosure too."""
    for index in range(4):
        send(person(f"p{index}@example.com", "harrisburg"), key=f"k{index}")
    outsider = person("outsider@example.com", "fairfax-va")
    queryset = FeedbackTicket.objects.for_reader(
        outsider, access=get_effective_access(outsider), can_triage=False
    )
    assert queryset.count() == 0


# --------------------------------------------------------------------------- #
# Internal notes
# --------------------------------------------------------------------------- #


def test_an_internal_note_never_reaches_the_submitter(seeded):
    agent = person("agent@example.com")
    staff = person("staff@example.com")
    ticket, _ = send(agent)

    services.add_note(
        actor=actor(staff, TRIAGE), ticket=ticket, body="We are on it.", internal=False
    )
    services.add_note(
        actor=actor(staff, TRIAGE),
        ticket=ticket,
        body="Third report from this office this week.",
        internal=True,
    )

    submitter_view = [n.body for n in services.visible_notes(ticket, actor(agent))]
    assert submitter_view == ["We are on it."]

    staff_view = [n.body for n in services.visible_notes(ticket, actor(staff, TRIAGE))]
    assert len(staff_view) == 2


def test_a_submitter_may_reply_on_their_own_ticket_without_any_grant(seeded):
    agent = person("agent@example.com")
    ticket, _ = send(agent)
    note = services.add_note(
        actor=actor(agent), ticket=ticket, body="Still happening.", internal=False
    )
    assert note.internal is False


def test_a_stranger_cannot_write_on_somebody_elses_ticket(seeded):
    agent = person("agent@example.com")
    stranger = person("stranger@example.com")
    ticket, _ = send(agent)
    with pytest.raises(PermissionDenied):
        services.add_note(
            actor=actor(stranger), ticket=ticket, body="Hello", internal=False
        )


def test_writing_an_internal_note_needs_the_note_grant(seeded):
    agent = person("agent@example.com")
    ticket, _ = send(agent)
    with pytest.raises(PermissionDenied):
        services.add_note(
            actor=actor(agent), ticket=ticket, body="secret", internal=True
        )


def test_an_empty_note_is_refused(seeded):
    agent = person("agent@example.com")
    ticket, _ = send(agent)
    with pytest.raises(ValidationError):
        services.add_note(actor=actor(agent), ticket=ticket, body="   ", internal=False)


# --------------------------------------------------------------------------- #
# Triage
# --------------------------------------------------------------------------- #


def test_triage_needs_the_grant(seeded):
    agent = person("agent@example.com")
    ticket, _ = send(agent)
    with pytest.raises(PermissionDenied):
        services.transition(
            actor=actor(agent), ticket=ticket, to_status=FeedbackStatus.TRIAGED
        )


def test_an_illegal_move_is_refused(seeded):
    staff = person("staff@example.com")
    ticket, _ = send(person("agent@example.com"))
    with pytest.raises(TransitionError):
        services.transition(
            actor=actor(staff, TRIAGE), ticket=ticket, to_status=FeedbackStatus.CLOSED
        )


def test_asking_for_information_requires_actually_asking_something(seeded):
    staff = person("staff@example.com")
    ticket, _ = send(person("agent@example.com"))
    with pytest.raises(ValidationError):
        services.transition(
            actor=actor(staff, TRIAGE),
            ticket=ticket,
            to_status=FeedbackStatus.NEEDS_INFO,
        )

    moved = services.transition(
        actor=actor(staff, TRIAGE),
        ticket=ticket,
        to_status=FeedbackStatus.NEEDS_INFO,
        reply="Which browser were you using?",
    )
    assert moved.status == FeedbackStatus.NEEDS_INFO
    # The question is for the submitter, so it is *not* an internal note.
    assert FeedbackNote.objects.get(ticket=ticket).internal is False


def test_repeating_a_transition_is_a_no_op(seeded):
    staff = person("staff@example.com")
    ticket, _ = send(person("agent@example.com"))
    services.transition(
        actor=actor(staff, TRIAGE), ticket=ticket, to_status=FeedbackStatus.TRIAGED
    )
    before = AuditEvent.objects.filter(action="feedback.status_changed").count()
    again = services.transition(
        actor=actor(staff, TRIAGE), ticket=ticket, to_status=FeedbackStatus.TRIAGED
    )
    assert again.status == FeedbackStatus.TRIAGED
    assert AuditEvent.objects.filter(action="feedback.status_changed").count() == before


def test_the_expected_state_check_stops_the_loser_of_a_race(seeded):
    staff = person("staff@example.com")
    ticket, _ = send(person("agent@example.com"))
    services.transition(
        actor=actor(staff, TRIAGE), ticket=ticket, to_status=FeedbackStatus.TRIAGED
    )

    stale = FeedbackTicket.objects.get(pk=ticket.pk)
    stale.status = FeedbackStatus.NEW
    with pytest.raises(ConcurrentUpdate):
        services.transition(
            actor=actor(staff, TRIAGE),
            ticket=stale,
            to_status=FeedbackStatus.TRIAGED,
            expected_status=FeedbackStatus.NEW,
        )


def test_closing_and_reopening_move_the_timestamps(seeded):
    staff = person("staff@example.com")
    ticket, _ = send(person("agent@example.com"))
    for target in (
        FeedbackStatus.TRIAGED,
        FeedbackStatus.RESOLVED,
        FeedbackStatus.CLOSED,
    ):
        ticket = services.transition(
            actor=actor(staff, TRIAGE), ticket=ticket, to_status=target
        )
    assert ticket.closed_at is not None

    reopened = services.transition(
        actor=actor(staff, TRIAGE),
        ticket=ticket,
        to_status=FeedbackStatus.IN_PROGRESS,
    )
    assert reopened.closed_at is None
    assert reopened.resolved_at is None


def test_priority_is_staff_owned_and_leaves_the_stated_urgency_alone(seeded):
    staff = person("staff@example.com")
    ticket, _ = send(person("agent@example.com"), urgency=FeedbackUrgency.BLOCKING)
    updated = services.set_priority(
        actor=actor(staff, TRIAGE), ticket=ticket, priority=FeedbackPriority.LOW
    )
    assert updated.priority == FeedbackPriority.LOW
    assert updated.urgency == FeedbackUrgency.BLOCKING


# --------------------------------------------------------------------------- #
# Conversion
# --------------------------------------------------------------------------- #


def test_converting_twice_yields_one_task(seeded):
    from apps.operational_tasks.models import OperationalTask
    from apps.operational_tasks.taxonomy import TaskPermission

    staff = person("staff@example.com")
    grants = TRIAGE | {TaskPermission.MANAGE, TaskPermission.VIEW}
    ticket, _ = send(person("agent@example.com"))

    first, created_first = services.convert_to_task(
        actor=actor(staff, grants), ticket=ticket
    )
    second, created_second = services.convert_to_task(
        actor=actor(staff, grants), ticket=FeedbackTicket.objects.get(pk=ticket.pk)
    )

    assert created_first is True
    assert created_second is False
    assert first == second
    assert OperationalTask.objects.count() == 1

    task = OperationalTask.objects.get()
    # Source identity survives, which is what lets each side re-authorize.
    assert task.source_reference == str(ticket.public_id)


def test_conversion_carries_no_file_across_the_boundary(seeded):
    """A screenshot stays under this module's policy.

    The task reader is not automatically entitled to it; the link is the
    reference, and each side checks its own side.
    """
    from apps.operational_tasks.models import OperationalTask, TaskAttachment
    from apps.operational_tasks.taxonomy import TaskPermission

    staff = person("staff@example.com")
    ticket, _ = send(person("agent@example.com"))
    services.convert_to_task(
        actor=actor(staff, TRIAGE | {TaskPermission.MANAGE}), ticket=ticket
    )
    task = OperationalTask.objects.get()
    assert TaskAttachment.objects.filter(task=task).count() == 0


def test_conversion_needs_the_task_modules_own_grant_too(seeded):
    """Holding feedback triage does not by itself let somebody create tasks."""
    staff = person("staff@example.com")
    ticket, _ = send(person("agent@example.com"))
    with pytest.raises(PermissionDenied):
        services.convert_to_task(actor=actor(staff, TRIAGE), ticket=ticket)
