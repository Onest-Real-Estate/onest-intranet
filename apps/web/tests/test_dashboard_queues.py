"""Support-queue and team-task dashboard providers.

Both panels are windows on an existing operations queue. What matters is that
they never widen it: scope, permission, and the destination each row links to
have to agree with the page the panel points at.
"""

from datetime import timedelta
from itertools import count

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.feedback.taxonomy import FeedbackCategory, FeedbackUrgency
from apps.it_support import services
from apps.it_support.models import SupportTicket
from apps.it_support.taxonomy import SupportCategory, SupportPriority, SupportStatus
from apps.operational_tasks.models import OperationalTask
from apps.operational_tasks.taxonomy import TaskPriority, TaskStatus
from apps.user.roles import BRANCH_MANAGER, IT_SUPPORT, ScopeType
from apps.web.dashboard import (
    WIDGET_BY_KEY,
    WidgetStatus,
    build_context,
    widget_payload,
)
from apps.web.tests.test_dashboard_metrics import (
    assign,
    branch,
    make_user,
    other_region_office,
)


@pytest.fixture(autouse=True)
def _clear_submission_limiter():
    """The ticket submission limiter is cache-backed and the cache outlives the
    test database. A test that raises several tickets as one person trips it
    otherwise, which looks like a provider bug and is not one."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def payload_for(user, key: str) -> dict:
    return widget_payload(WIDGET_BY_KEY[key], build_context(user))


def grant_permission(group_name: str, *codenames: str) -> None:
    """Add permissions to a role's group, the real grant path."""
    from django.contrib.auth.models import Group, Permission

    group = Group.objects.get(name=group_name)
    group.permissions.add(
        *[Permission.objects.get(codename=code) for code in codenames]
    )


def grant_triage_to_it_support() -> None:
    """Add the triage grant to the IT Support role's group.

    No catalogued role holds ``web.triage_it_support`` today, so the queue —
    page and panel alike — shows even an IT Support reader only the tickets
    they raised. That is a role-bundle gap, not a widget behaviour, so the
    tests that exercise a real queue grant it explicitly rather than pretending
    the seed already does.
    """
    from django.contrib.auth.models import Group, Permission

    group = Group.objects.get(name="IT Support")
    group.permissions.add(Permission.objects.get(codename="triage_it_support"))


_submission = count(1)


def make_ticket(*, submitter, subject: str, **fields) -> SupportTicket:
    """Raise a ticket the way the product does.

    `services.submit` is the only path that stamps the human reference and the
    office, both of which the model requires to be unique/derived; building the
    row directly collides on the second insert.
    """
    ticket, _ = services.submit(
        user=submitter,
        subject=subject,
        description="Nothing works.",
        category=SupportCategory.ACCESS,
        submission_key=f"dashboard-{next(_submission)}",
    )
    updates = {}
    for field, value in fields.items():
        setattr(ticket, field, value)
        updates[field] = value
    if updates:
        ticket.save(update_fields=list(updates))
    return ticket


def make_task(*, office, reporter, title: str, **fields) -> OperationalTask:
    return OperationalTask.objects.create(
        title=title,
        description="Do the thing.",
        office=office,
        reporter=reporter,
        status=fields.pop("status", TaskStatus.OPEN),
        priority=fields.pop("priority", TaskPriority.NORMAL),
        **fields,
    )


# ---------------------------------------------------------------------------
# Support queue
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_support_queue_is_withheld_without_the_grant():
    office = branch()
    reader = make_user("no-grant@example.com", office=office)
    make_ticket(submitter=reader, subject="Printer down")

    payload = payload_for(reader, "support_queue")
    # An `empty` envelope, not `unavailable`: the module is connected, this
    # reader simply has no queue. Saying "not connected" would be a lie.
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_support_queue_shows_open_tickets_in_reach():
    office = branch()
    triager = make_user("it@example.com", office=office)
    assign(triager, IT_SUPPORT, ScopeType.COMPANY)
    grant_triage_to_it_support()
    reporter = make_user("agent@example.com", office=office)
    make_ticket(
        submitter=reporter,
        subject="Laptop will not boot",
        priority=SupportPriority.URGENT,
    )

    payload = payload_for(triager, "support_queue")
    assert payload["status"] == WidgetStatus.READY
    assert payload["data"]["total"] == 1
    row = payload["data"]["rows"][0]
    assert row["title"] == "Laptop will not boot"
    assert row["tone"] == "destructive"
    assert row["href"].startswith("/")
    assert payload["data"]["viewAllHref"] == reverse("admin_it_support")


@pytest.mark.django_db
def test_support_queue_excludes_closed_tickets():
    office = branch()
    triager = make_user("it-closed@example.com", office=office)
    assign(triager, IT_SUPPORT, ScopeType.COMPANY)
    grant_triage_to_it_support()
    reporter = make_user("agent-closed@example.com", office=office)
    make_ticket(
        submitter=reporter,
        subject="Resolved already",
        status=SupportStatus.CLOSED,
        closed_at=timezone.now(),
    )

    payload = payload_for(triager, "support_queue")
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_support_queue_without_triage_is_only_the_readers_own_requests():
    """Exactly what the queue page does, and worth pinning.

    Office reach buys nothing without the triage grant: being a manager is not
    a reason to read a colleague's password problem. The panel therefore shows
    a reader with `view_it_support` alone their own open requests and nothing
    else.
    """
    office = branch()
    reader = make_user("view-only@example.com", office=office)
    assign(reader, IT_SUPPORT, ScopeType.COMPANY)
    colleague = make_user("colleague@example.com", office=office)
    make_ticket(submitter=colleague, subject="Someone else's problem")
    make_ticket(submitter=reader, subject="My own problem")

    payload = payload_for(reader, "support_queue")
    assert payload["status"] == WidgetStatus.READY
    assert payload["data"]["total"] == 1
    assert payload["data"]["rows"][0]["title"] == "My own problem"


@pytest.mark.django_db
def test_support_queue_never_leaks_another_region():
    office = branch()
    elsewhere = other_region_office(office)
    triager = make_user("it-scoped@example.com", office=office)
    assign(triager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    grant_triage_to_it_support()
    # Give this reader triage + view without company reach, so the only thing
    # deciding what they see is their office scope.
    from django.contrib.auth.models import Group, Permission

    group = Group.objects.get(name="Branch Managers")
    group.permissions.add(
        Permission.objects.get(codename="view_it_support"),
        Permission.objects.get(codename="triage_it_support"),
    )
    stranger = make_user("stranger@example.com", office=elsewhere)
    make_ticket(submitter=stranger, subject="Not your office")

    payload = payload_for(triager, "support_queue")
    # Not one row, and not a count either: `total` is what the panel prints, so
    # a leaked total is a leaked record.
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_support_queue_is_capped_but_counts_honestly():
    office = branch()
    triager = make_user("it-cap@example.com", office=office)
    assign(triager, IT_SUPPORT, ScopeType.COMPANY)
    grant_triage_to_it_support()
    reporter = make_user("agent-cap@example.com", office=office)
    for index in range(8):
        make_ticket(submitter=reporter, subject=f"Ticket {index}")

    payload = payload_for(triager, "support_queue")
    assert payload["data"]["total"] == 8
    assert len(payload["data"]["rows"]) == 5


# ---------------------------------------------------------------------------
# Team tasks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_team_tasks_is_withheld_without_the_pages_own_grant():
    office = branch()
    reader = make_user("task-no-grant@example.com", office=office)

    payload = payload_for(reader, "team_tasks")
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_team_tasks_shows_live_work_in_scope():
    office = branch()
    manager = make_user("mgr@example.com", office=office)
    assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    make_task(office=office, reporter=manager, title="Reorder lockboxes")

    payload = payload_for(manager, "team_tasks")
    assert payload["status"] == WidgetStatus.READY
    assert payload["data"]["total"] == 1
    row = payload["data"]["rows"][0]
    assert row["title"] == "Reorder lockboxes"
    assert payload["data"]["viewAllHref"] == reverse("operational_tasks")


@pytest.mark.django_db
def test_team_tasks_marks_an_overdue_task():
    office = branch()
    manager = make_user("mgr-overdue@example.com", office=office)
    assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    make_task(
        office=office,
        reporter=manager,
        title="Late already",
        due_at=timezone.now() - timedelta(days=3),
    )

    payload = payload_for(manager, "team_tasks")
    row = payload["data"]["rows"][0]
    assert row["badge"] == "Overdue"
    assert row["tone"] == "destructive"


@pytest.mark.django_db
def test_team_tasks_excludes_closed_work():
    office = branch()
    manager = make_user("mgr-closed@example.com", office=office)
    assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    make_task(
        office=office,
        reporter=manager,
        title="Done",
        status=TaskStatus.CLOSED,
        closed_at=timezone.now(),
    )

    payload = payload_for(manager, "team_tasks")
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_team_tasks_never_leaks_another_region():
    office = branch()
    elsewhere = other_region_office(office)
    manager = make_user("mgr-scoped@example.com", office=office)
    assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    stranger = make_user("stranger-task@example.com", office=elsewhere)
    make_task(office=elsewhere, reporter=stranger, title="Not your office")

    payload = payload_for(manager, "team_tasks")
    assert payload["status"] == WidgetStatus.EMPTY


# ---------------------------------------------------------------------------
# Quick documents
# ---------------------------------------------------------------------------


def make_resource(*, office, slug: str, title: str, **fields):
    from apps.user.models import OfficeResource

    return OfficeResource.objects.create(
        owner_office=office,
        slug=slug,
        title=title,
        category=OfficeResource.Category.LOCAL_FORMS,
        resource_type=fields.pop("resource_type", OfficeResource.ResourceType.FILE),
        **fields,
    )


@pytest.mark.django_db
def test_quick_documents_lists_the_readers_office_library():
    office = branch()
    reader = make_user("docs@example.com", office=office)
    make_resource(office=office, slug="listing-packet", title="Listing packet")

    payload = payload_for(reader, "quick_documents")
    assert payload["status"] == WidgetStatus.READY
    item = payload["data"]["items"][0]
    assert item["name"] == "Listing packet"
    # A file goes through the protected download view, never a storage URL.
    assert item["href"] == reverse("office_resources_download", args=["listing-packet"])
    assert payload["data"]["viewAllHref"] == reverse("office_resources")


@pytest.mark.django_db
def test_quick_documents_inherits_the_office_chain():
    from apps.user.models import Office

    office = branch()
    reader = make_user("docs-chain@example.com", office=office)
    head = Office.objects.get(kind=Office.Kind.HEAD_OFFICE, parent__isnull=True)
    make_resource(office=head, slug="brokerage-policy", title="Brokerage policy")

    payload = payload_for(reader, "quick_documents")
    assert payload["status"] == WidgetStatus.READY
    assert [item["name"] for item in payload["data"]["items"]] == ["Brokerage policy"]


@pytest.mark.django_db
def test_quick_documents_says_empty_rather_than_unconnected():
    office = branch()
    reader = make_user("docs-empty@example.com", office=office)

    payload = payload_for(reader, "quick_documents")
    # The library exists and is simply empty for this reader; calling that
    # "not connected" would misdescribe a working module.
    assert payload["status"] == WidgetStatus.EMPTY


# ---------------------------------------------------------------------------
# Room utilization and agent onboarding
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_room_utilization_is_withheld_without_the_grant():
    office = branch()
    reader = make_user("rooms-no-grant@example.com", office=office)

    payload = payload_for(reader, "room_utilization")
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_room_utilization_reports_unmeasured_rather_than_zero():
    """A room with no published hours was never bookable.

    Reporting it as 0% used would read as "nobody wanted it" when the real
    answer is that nobody could have booked it.
    """
    from apps.reservations.models import Space
    from apps.reservations.taxonomy import SpaceStatus

    office = branch()
    manager = make_user("rooms@example.com", office=office)
    assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    Space.objects.create(
        owner_office=office,
        name="Unscheduled room",
        space_type="meeting_room",
        capacity=4,
        status=SpaceStatus.ACTIVE,
        is_reservable=True,
    )

    payload = payload_for(manager, "room_utilization")
    # No published hours anywhere in scope, so there is no denominator at all.
    assert payload["status"] == WidgetStatus.EMPTY
    assert payload["emptyState"]["title"] == "No published hours"


@pytest.mark.django_db
def test_agent_onboarding_is_withheld_without_the_grant():
    office = branch()
    reader = make_user("onboarding-no-grant@example.com", office=office)

    payload = payload_for(reader, "agent_onboarding")
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_agent_onboarding_counts_only_administered_people():
    office = branch()
    elsewhere = other_region_office(office)
    manager = make_user("onboarding@example.com", office=office)
    assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    make_user("newcomer@example.com", office=office)
    make_user("stranger-newcomer@example.com", office=elsewhere)

    payload = payload_for(manager, "agent_onboarding")
    assert payload["status"] == WidgetStatus.READY
    counted = sum(int(stage["value"]) for stage in payload["data"]["stages"])
    # The colleague in another region is not in this manager's population.
    assert counted >= 1
    assert "stranger" not in str(payload["data"])


# ---------------------------------------------------------------------------
# Awaiting signature and feedback signals
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_awaiting_signature_is_withheld_without_the_grant():
    office = branch()
    reader = make_user("contracts-no-grant@example.com", office=office)

    payload = payload_for(reader, "contracts_awaiting_signature")
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_feedback_signals_is_withheld_without_the_grant():
    office = branch()
    reader = make_user("feedback-no-grant@example.com", office=office)

    payload = payload_for(reader, "feedback_signals")
    assert payload["status"] == WidgetStatus.EMPTY


@pytest.mark.django_db
def test_feedback_signals_shows_open_reports_in_reach():
    from apps.feedback import services as feedback_services

    office = branch()
    triager = make_user("feedback-triage@example.com", office=office)
    assign(triager, IT_SUPPORT, ScopeType.COMPANY)
    grant_permission("IT Support", "view_feedback", "triage_feedback")
    reporter = make_user("reporter@example.com", office=office)
    feedback_services.submit(
        user=reporter,
        summary="Search returns nothing",
        description="Typing a name finds no one.",
        urgency=FeedbackUrgency.SLOWING,
        category=FeedbackCategory.BUG,
        submission_key="dashboard-feedback-1",
    )

    payload = payload_for(triager, "feedback_signals")
    assert payload["status"] == WidgetStatus.READY
    assert payload["data"]["total"] == 1
    assert payload["data"]["rows"][0]["title"] == "Search returns nothing"
    assert payload["data"]["viewAllHref"] == reverse("admin_feedback")


@pytest.mark.django_db
def test_feedback_signals_never_leaks_another_region():
    from apps.feedback import services as feedback_services

    office = branch()
    elsewhere = other_region_office(office)
    triager = make_user("feedback-scoped@example.com", office=office)
    assign(triager, BRANCH_MANAGER, ScopeType.OFFICE, office)
    grant_permission("Branch Managers", "view_feedback", "triage_feedback")
    stranger = make_user("feedback-stranger@example.com", office=elsewhere)
    feedback_services.submit(
        user=stranger,
        summary="Not your office",
        description="Something else entirely.",
        urgency=FeedbackUrgency.SLOWING,
        category=FeedbackCategory.BUG,
        submission_key="dashboard-feedback-2",
    )

    payload = payload_for(triager, "feedback_signals")
    assert payload["status"] == WidgetStatus.EMPTY
