"""Submission, the lifecycle, and the boundaries a requester must not cross.

The rules under test are the ones a support desk gets wrong in production:
an internal note reaching the person it was written about, a requester
escalating their own ticket, and a double-clicked form raising two tickets.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.it_support import services
from apps.it_support.models import SupportTicket
from apps.it_support.services import ActorContext
from apps.it_support.taxonomy import (
    SupportCategory,
    SupportPermission,
    SupportPriority,
    SupportStatus,
)
from apps.user.models import Office
from apps.user.tests.test_profile import completed_user


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    """The submission limiter is cache-backed and the cache outlives the test
    database. Primary keys restart at 1 for every test, so without this the
    tenth ticket raised across the whole module trips the limiter in whichever
    test happens to run then — a failure that never reproduces in isolation."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def desk(user) -> ActorContext:
    """IT staff: every grant in the family."""
    return ActorContext(
        user=user,
        permissions=frozenset(
            {
                SupportPermission.VIEW,
                SupportPermission.TRIAGE,
                SupportPermission.ASSIGN,
                SupportPermission.NOTE,
            }
        ),
    )


def requester(user) -> ActorContext:
    """A normal person: no grant at all."""
    return ActorContext(user=user, permissions=frozenset())


def raise_ticket(user, *, key="k1", category=SupportCategory.PRINTER, **kwargs):
    ticket, created = services.submit(
        user=user,
        subject=kwargs.pop("subject", "Printer will not authenticate"),
        description=kwargs.pop("description", "It asks for a PIN I do not have."),
        category=category,
        submission_key=key,
        **kwargs,
    )
    return ticket, created


# --------------------------------------------------------------------------- #
# Submission
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_anybody_signed_in_may_raise_a_ticket(seeded):
    """No grant required, on purpose: gating this means the people most likely
    to hit an access bug are the ones who cannot report it."""
    agent = person("agent@example.com")
    ticket, created = raise_ticket(agent)

    assert created is True
    assert ticket.reference.startswith("ITS-")
    assert ticket.status == SupportStatus.NEW
    assert ticket.submitter_pk == agent.pk


@pytest.mark.django_db
def test_the_office_is_snapshotted_from_the_submitter(seeded):
    """Never accepted from the client: a posted office id would be a way to
    file into another branch's queue."""
    agent = person("agent@example.com", "harrisburg")
    ticket, _ = raise_ticket(agent)
    assert ticket.office == office("harrisburg")


@pytest.mark.django_db
def test_a_double_submit_raises_one_ticket(seeded):
    agent = person("agent@example.com")
    first, created_first = raise_ticket(agent, key="same-key")
    second, created_second = raise_ticket(agent, key="same-key")

    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert SupportTicket.objects.count() == 1


@pytest.mark.django_db
def test_a_submission_with_no_key_is_refused(seeded):
    agent = person("agent@example.com")
    with pytest.raises(ValidationError):
        raise_ticket(agent, key="")


@pytest.mark.django_db
def test_an_unknown_category_is_refused(seeded):
    agent = person("agent@example.com")
    with pytest.raises(ValidationError) as caught:
        raise_ticket(agent, category="astrology")
    assert "category" in caught.value.message_dict


# --------------------------------------------------------------------------- #
# The lifecycle
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_desk_moves_a_ticket_through_to_resolved(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)

    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.OPEN)
    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.IN_PROGRESS)
    resolved = services.transition(
        actor=actor,
        ticket=ticket,
        to_status=SupportStatus.RESOLVED,
        note="Reset the print queue and re-enrolled the device.",
    )

    assert resolved.status == SupportStatus.RESOLVED
    assert resolved.resolved_at is not None
    assert resolved.closed_at is None


@pytest.mark.django_db
def test_resolving_records_a_resolution_the_requester_can_read(seeded):
    """The note that closes the loop is what the requester is actually told,
    so it is recorded as a resolution rather than a line in the thread."""
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)
    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.IN_PROGRESS)
    services.transition(
        actor=actor,
        ticket=ticket,
        to_status=SupportStatus.RESOLVED,
        note="Replaced the toner cartridge.",
    )

    visible = list(services.visible_replies(ticket, requester(agent)))
    assert [reply.body for reply in visible] == ["Replaced the toner cartridge."]
    assert visible[0].is_resolution is True
    assert visible[0].internal is False


@pytest.mark.django_db
def test_a_move_that_needs_an_explanation_cannot_be_silent(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)
    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.IN_PROGRESS)

    with pytest.raises(ValidationError) as caught:
        services.transition(
            actor=actor, ticket=ticket, to_status=SupportStatus.WAITING_USER
        )
    assert "note" in caught.value.message_dict


@pytest.mark.django_db
def test_a_requester_may_resume_their_own_waiting_ticket(seeded):
    """Answering the question IT asked is the one move the person waiting can
    make, and it needs no grant."""
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)
    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.IN_PROGRESS)
    services.transition(
        actor=actor,
        ticket=ticket,
        to_status=SupportStatus.WAITING_USER,
        note="Which printer is it?",
    )

    resumed = services.transition(
        actor=requester(agent), ticket=ticket, to_status=SupportStatus.IN_PROGRESS
    )
    assert resumed.status == SupportStatus.IN_PROGRESS


@pytest.mark.django_db
def test_a_requester_cannot_close_their_own_ticket(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)
    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.IN_PROGRESS)
    services.transition(
        actor=actor, ticket=ticket, to_status=SupportStatus.RESOLVED, note="Fixed."
    )

    with pytest.raises(PermissionDenied):
        services.transition(
            actor=requester(agent), ticket=ticket, to_status=SupportStatus.CLOSED
        )


@pytest.mark.django_db
def test_a_requester_may_reopen_a_ticket_that_is_still_broken(seeded):
    """ "It is still broken" is the whole point of telling somebody it was
    fixed, so reopening needs no grant."""
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)
    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.IN_PROGRESS)
    services.transition(
        actor=actor, ticket=ticket, to_status=SupportStatus.RESOLVED, note="Fixed."
    )

    reopened = services.transition(
        actor=requester(agent), ticket=ticket, to_status=SupportStatus.IN_PROGRESS
    )
    assert reopened.status == SupportStatus.IN_PROGRESS
    # The old resolution timestamp is cleared: it is no longer resolved.
    assert reopened.resolved_at is None


@pytest.mark.django_db
def test_closing_stamps_the_timestamp_the_constraint_requires(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)
    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.IN_PROGRESS)
    services.transition(
        actor=actor, ticket=ticket, to_status=SupportStatus.RESOLVED, note="Fixed."
    )
    closed = services.transition(
        actor=actor, ticket=ticket, to_status=SupportStatus.CLOSED
    )
    assert closed.closed_at is not None


@pytest.mark.django_db
def test_an_illegal_move_is_refused(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)

    with pytest.raises(ValidationError):
        services.transition(
            actor=desk(staff), ticket=ticket, to_status=SupportStatus.CLOSED
        )


@pytest.mark.django_db
def test_repeating_a_move_is_a_no_op(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)
    first = services.transition(
        actor=actor, ticket=ticket, to_status=SupportStatus.OPEN
    )
    second = services.transition(
        actor=actor, ticket=ticket, to_status=SupportStatus.OPEN
    )
    assert first.status == second.status == SupportStatus.OPEN


@pytest.mark.django_db
def test_a_stale_writer_is_told_it_lost_the_race(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    actor = desk(staff)
    services.transition(actor=actor, ticket=ticket, to_status=SupportStatus.OPEN)

    with pytest.raises(services.ConcurrentUpdate):
        services.transition(
            actor=actor,
            ticket=ticket,
            to_status=SupportStatus.IN_PROGRESS,
            expected_status=SupportStatus.NEW,
        )


# --------------------------------------------------------------------------- #
# Priority and assignment
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_requester_cannot_raise_their_own_priority(seeded):
    """Otherwise the field means nothing within a week."""
    agent = person("agent@example.com")
    ticket, _ = raise_ticket(agent)

    with pytest.raises(PermissionDenied):
        services.set_priority(
            actor=requester(agent), ticket=ticket, priority=SupportPriority.URGENT
        )


@pytest.mark.django_db
def test_assignment_needs_the_assign_grant(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)

    with pytest.raises(PermissionDenied):
        services.assign(actor=requester(agent), ticket=ticket, assignee=staff)

    assigned = services.assign(actor=desk(staff), ticket=ticket, assignee=staff)
    assert assigned.assignee_pk == staff.pk


@pytest.mark.django_db
def test_a_stale_reassignment_loses_the_race(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    other = person("it2@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    services.assign(actor=desk(staff), ticket=ticket, assignee=other)

    with pytest.raises(services.ConcurrentUpdate):
        services.assign(
            actor=desk(staff),
            ticket=ticket,
            assignee=staff,
            expected_assignee_id=None,
        )
