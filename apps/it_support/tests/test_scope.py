"""Who can see which ticket, and what an internal note is worth keeping internal.

Both rules are enforced in the *queryset*: a later Python-side check would leak
existence through counts and pagination totals even when it hid the row.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied

from apps.it_support import services
from apps.it_support.models import SupportTicket
from apps.it_support.taxonomy import SupportPermission
from apps.it_support.tests.test_lifecycle import (
    desk,
    office,
    person,
    raise_ticket,
    requester,
)
from apps.user.models import UserRoleAssignment
from apps.user.services.role_assignments import get_effective_access


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    """The submission limiter is cache-backed and the cache outlives the test
    database. Primary keys restart at 1 for every test, so without this a run
    trips the limiter in whichever test happens to be tenth."""
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


def assign_role(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def visible_to(user, *, can_triage: bool) -> set[str]:
    return set(
        SupportTicket.objects.for_reader(
            user, access=get_effective_access(user), can_triage=can_triage
        ).values_list("subject", flat=True)
    )


# --------------------------------------------------------------------------- #
# Reach
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_requester_sees_only_their_own_tickets(seeded):
    mine = person("mine@example.com")
    theirs = person("theirs@example.com")
    raise_ticket(mine, key="a", subject="Mine")
    raise_ticket(theirs, key="b", subject="Theirs")

    assert visible_to(mine, can_triage=False) == {"Mine"}


@pytest.mark.django_db
def test_the_agent_a_ticket_is_about_can_watch_it(seeded):
    """A new agent should be able to follow their own account setup without
    holding an IT grant, even though somebody else raised the request."""
    admin = person("admin@example.com", "onest-head-office")
    newcomer = person("newcomer@example.com")
    services.submit(
        user=admin,
        subject="Set up Jane's accounts",
        description="Lofty, SkySlope, and email.",
        category="agent_onboarding",
        submission_key="onboard-1",
        about_user=newcomer,
    )

    assert visible_to(newcomer, can_triage=False) == {"Set up Jane's accounts"}


@pytest.mark.django_db
def test_office_reach_buys_nothing_without_the_triage_grant(seeded):
    """Being a branch manager is not a reason to read a colleague's password
    problem. Reach only applies once somebody holds the grant."""
    colleague = person("colleague@example.com")
    raise_ticket(colleague, key="a", subject="Locked out")

    manager = person("branch@example.com")
    assign_role(manager, "branch_manager", "office", office("fairfax-va"))

    assert visible_to(manager, can_triage=False) == set()


@pytest.mark.django_db
def test_a_triager_sees_their_office_and_not_a_sibling(seeded):
    fairfax = person("fx@example.com", "fairfax-va")
    harrisburg = person("hb@example.com", "harrisburg")
    raise_ticket(fairfax, key="a", subject="Fairfax problem")
    raise_ticket(harrisburg, key="b", subject="Harrisburg problem")

    staff = person("it@example.com", "fairfax-va")
    assign_role(staff, "branch_manager", "office", office("fairfax-va"))

    assert visible_to(staff, can_triage=True) == {"Fairfax problem"}


@pytest.mark.django_db
def test_company_reach_sees_every_office(seeded):
    fairfax = person("fx@example.com", "fairfax-va")
    harrisburg = person("hb@example.com", "harrisburg")
    raise_ticket(fairfax, key="a", subject="Fairfax problem")
    raise_ticket(harrisburg, key="b", subject="Harrisburg problem")

    staff = person("it@example.com", "onest-head-office")
    assign_role(staff, "system_admin", "company")

    assert {"Fairfax problem", "Harrisburg problem"} <= visible_to(
        staff, can_triage=True
    )


@pytest.mark.django_db
def test_scope_is_applied_before_counting_not_after(seeded):
    """A count is a disclosure too."""
    colleague = person("colleague@example.com", "harrisburg")
    for index in range(4):
        raise_ticket(colleague, key=f"k{index}", subject=f"Hidden {index}")

    outsider = person("outsider@example.com", "fairfax-va")
    assert (
        SupportTicket.objects.for_reader(
            outsider, access=get_effective_access(outsider), can_triage=False
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_an_anonymous_reader_sees_nothing(seeded):
    from django.contrib.auth.models import AnonymousUser

    agent = person("agent@example.com")
    raise_ticket(agent, key="a", subject="Something")

    assert (
        SupportTicket.objects.for_reader(
            AnonymousUser(), access=get_effective_access(agent), can_triage=True
        ).count()
        == 0
    )


# --------------------------------------------------------------------------- #
# Internal notes
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_an_internal_note_never_reaches_the_requester(seeded):
    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)

    services.add_reply(
        actor=desk(staff), ticket=ticket, body="We have ordered the part."
    )
    services.add_reply(
        actor=desk(staff),
        ticket=ticket,
        body="Third time this month; the hardware is failing.",
        internal=True,
    )

    theirs = [r.body for r in services.visible_replies(ticket, requester(agent))]
    assert theirs == ["We have ordered the part."]

    ours = [r.body for r in services.visible_replies(ticket, desk(staff))]
    assert len(ours) == 2


@pytest.mark.django_db
def test_writing_an_internal_note_needs_the_note_grant(seeded):
    agent = person("agent@example.com")
    ticket, _ = raise_ticket(agent)

    # The requester may reply on their own ticket...
    services.add_reply(actor=requester(agent), ticket=ticket, body="Any update?")

    # ...but the staff-only channel is not theirs to write in.
    with pytest.raises(PermissionDenied):
        services.add_reply(
            actor=requester(agent), ticket=ticket, body="Staff only", internal=True
        )


@pytest.mark.django_db
def test_a_stranger_cannot_reply_on_somebody_elses_ticket(seeded):
    agent = person("agent@example.com")
    stranger = person("stranger@example.com")
    ticket, _ = raise_ticket(agent)

    with pytest.raises(PermissionDenied):
        services.add_reply(actor=requester(stranger), ticket=ticket, body="Hello")


@pytest.mark.django_db
def test_the_payload_hides_diagnostics_from_the_requester(seeded):
    """Device details are of no use to the requester and describe their own
    machine, which is not something to echo onto a page they may screen-share."""
    from apps.it_support.payloads import ticket_detail

    agent = person("agent@example.com")
    ticket, _ = raise_ticket(agent, device_info="MacBook Pro 14, Chrome 152")

    theirs = ticket_detail(
        ticket, replies=[], attachments=[], transitions=[], can_triage=False
    )
    ours = ticket_detail(
        ticket, replies=[], attachments=[], transitions=[], can_triage=True
    )

    assert theirs["deviceInfo"] == ""
    assert ours["deviceInfo"] == "MacBook Pro 14, Chrome 152"


@pytest.mark.django_db
def test_an_internal_attachment_is_not_resolvable_by_the_requester(seeded):
    """Not "raises 403": the lookup runs inside the visible set, so the file is
    indistinguishable from one that never existed."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    agent = person("agent@example.com")
    staff = person("it@example.com", "onest-head-office")
    ticket, _ = raise_ticket(agent)
    secret = services.attach_file(
        actor=desk(staff),
        ticket=ticket,
        uploaded=SimpleUploadedFile("audit.log", b"internal"),
        internal=True,
    )

    assert (
        services.load_attachment(
            ticket=ticket, actor=requester(agent), public_id=secret.public_id
        )
        is None
    )
    assert (
        services.load_attachment(
            ticket=ticket, actor=desk(staff), public_id=secret.public_id
        )
        == secret
    )


@pytest.mark.django_db
def test_a_requester_may_attach_evidence_to_their_own_ticket(seeded):
    from django.core.files.uploadedfile import SimpleUploadedFile

    agent = person("agent@example.com")
    ticket, _ = raise_ticket(agent)

    attachment = services.attach_file(
        actor=requester(agent),
        ticket=ticket,
        uploaded=SimpleUploadedFile("error.png", b"\x89PNG"),
    )
    assert attachment.internal is False
    assert attachment.media_type == "image/png"


@pytest.mark.django_db
def test_the_media_type_does_not_depend_on_the_host():
    """`mimetypes` reads the operating system's own MIME database: macOS maps
    `.log` to `text/plain` and a bare Linux container returns nothing. A stored
    type that varies by machine is a header this hub would later serve back."""
    assert set(services.ATTACHMENT_MEDIA_TYPES) == set(
        services.ALLOWED_ATTACHMENT_EXTENSIONS
    )
    assert services.ATTACHMENT_MEDIA_TYPES[".log"] == "text/plain"


@pytest.mark.django_db
def test_a_refused_extension_never_reaches_storage(seeded):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.it_support.models import TicketAttachment

    agent = person("agent@example.com")
    ticket, _ = raise_ticket(agent)

    with pytest.raises(Exception) as caught:
        services.attach_file(
            actor=requester(agent),
            ticket=ticket,
            uploaded=SimpleUploadedFile("payload.sh", b"#!/bin/sh"),
        )
    assert "not allowed" in str(caught.value)
    assert TicketAttachment.objects.filter(ticket=ticket).count() == 0


@pytest.mark.django_db
def test_the_grants_are_the_documented_family(seeded):
    assert SupportPermission.VIEW == "web.view_it_support"
    assert SupportPermission.TRIAGE == "web.triage_it_support"
    assert SupportPermission.ASSIGN == "web.assign_it_support"
    assert SupportPermission.NOTE == "web.note_it_support"
