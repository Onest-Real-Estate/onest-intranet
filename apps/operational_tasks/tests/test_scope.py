"""Who can see what, and what an internal note is worth keeping internal for.

Two rules are under test here and both are enforced in the *queryset*:

* ``for_reader`` is the only place task visibility is decided. A later
  Python-side check would leak existence through counts and pagination totals
  even when it hid the row itself.
* ``visible_comments`` excludes internal notes before a payload builder can
  see them, so no serializer bug can turn one into a response field.
"""

from __future__ import annotations

import pytest

from apps.operational_tasks import services
from apps.operational_tasks.models import OperationalTask
from apps.operational_tasks.services import ActorContext
from apps.operational_tasks.taxonomy import (
    TaskCategory,
    TaskPermission,
    TaskPriority,
)
from apps.user.models import Office, UserRoleAssignment
from apps.user.services.role_assignments import get_effective_access
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, slug: str):
    return completed_user(email=email, office=office(slug))


def assign_role(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def admin_actor(user) -> ActorContext:
    return ActorContext(
        user=user,
        permissions=frozenset(
            {
                TaskPermission.VIEW,
                TaskPermission.MANAGE,
                TaskPermission.ASSIGN,
                TaskPermission.COMMENT,
            }
        ),
    )


def make(admin, office_slug: str, title: str, *, reporter=None, assignee=None):
    return services.create_task(
        actor=admin_actor(admin),
        office=office(office_slug),
        category=TaskCategory.OFFICE_SETUP,
        title=title,
        priority=TaskPriority.NORMAL,
        reporter=reporter,
        assignee=assignee,
    )


def visible_to(user) -> set[str]:
    access = get_effective_access(user)
    return set(
        OperationalTask.objects.for_reader(user, access=access).values_list(
            "title", flat=True
        )
    )


# --------------------------------------------------------------------------- #
# Office / region / company reach
# --------------------------------------------------------------------------- #


def test_an_agent_with_no_administrative_reach_sees_nothing_by_default(seeded):
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    make(creator, "fairfax-va", "Fairfax printer")

    agent = person("agent@example.com", "fairfax-va")
    assert visible_to(agent) == set()


def test_reporting_a_task_is_enough_to_keep_reading_it(seeded):
    """The personal grant that never widens organisational reach."""
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    agent = person("agent@example.com", "fairfax-va")

    make(creator, "fairfax-va", "Mine", reporter=agent)
    make(creator, "fairfax-va", "Somebody else's")

    assert visible_to(agent) == {"Mine"}


def test_being_assigned_a_task_is_enough_to_read_it(seeded):
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    agent = person("agent@example.com", "harrisburg")

    make(creator, "fairfax-va", "Assigned to me", assignee=agent)
    make(creator, "fairfax-va", "Not mine")

    assert visible_to(agent) == {"Assigned to me"}


def test_explicit_share_grants_this_record_and_nothing_else(seeded):
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    agent = person("agent@example.com", "harrisburg")

    shared = make(creator, "fairfax-va", "Shared with me")
    shared.visible_to.set([agent])
    make(creator, "fairfax-va", "Also in Fairfax")

    assert visible_to(agent) == {"Shared with me"}


def test_a_branch_manager_sees_their_office_and_not_a_sibling(seeded):
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    make(creator, "fairfax-va", "Fairfax work")
    make(creator, "harrisburg", "Harrisburg work")

    manager = person("branch@example.com", "fairfax-va")
    assign_role(manager, "branch_manager", "office", office("fairfax-va"))

    assert visible_to(manager) == {"Fairfax work"}


def test_company_reach_sees_every_office(seeded):
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    make(creator, "fairfax-va", "Fairfax work")
    make(creator, "harrisburg", "Harrisburg work")

    assert {"Fairfax work", "Harrisburg work"} <= visible_to(creator)


def test_scope_is_applied_before_counting_not_after(seeded):
    """A count is a disclosure too.

    Filtering in Python after the query would hide the rows and still leak how
    many exist through the total.
    """
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    for index in range(4):
        make(creator, "harrisburg", f"Hidden {index}")

    agent = person("agent@example.com", "fairfax-va")
    access = get_effective_access(agent)
    assert OperationalTask.objects.for_reader(agent, access=access).count() == 0


def test_an_anonymous_reader_sees_nothing(seeded):
    from django.contrib.auth.models import AnonymousUser

    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    make(creator, "fairfax-va", "Something")

    access = get_effective_access(creator)
    queryset = OperationalTask.objects.for_reader(AnonymousUser(), access=access)
    assert queryset.count() == 0


def test_a_reader_matching_two_ways_is_returned_once(seeded):
    """Reporter *and* in-office must not duplicate the row."""
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    manager = person("branch@example.com", "fairfax-va")
    assign_role(manager, "branch_manager", "office", office("fairfax-va"))

    task = make(creator, "fairfax-va", "Both ways", reporter=manager)
    task.visible_to.set([manager])

    access = get_effective_access(manager)
    assert OperationalTask.objects.for_reader(manager, access=access).count() == 1


# --------------------------------------------------------------------------- #
# Internal notes
# --------------------------------------------------------------------------- #


def test_an_internal_note_is_excluded_from_a_non_managers_queryset(seeded):
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    reporter = person("reporter@example.com", "fairfax-va")
    task = make(creator, "fairfax-va", "Has notes", reporter=reporter)

    services.add_comment(
        actor=admin_actor(creator), task=task, body="Visible to the reporter."
    )
    services.add_comment(
        actor=admin_actor(creator),
        task=task,
        body="Vendor is stalling; do not tell them yet.",
        internal=True,
    )

    reader = ActorContext(user=reporter, permissions=frozenset({TaskPermission.VIEW}))
    bodies = [c.body for c in services.visible_comments(task, reader)]
    assert bodies == ["Visible to the reporter."]

    staff_bodies = [
        c.body for c in services.visible_comments(task, admin_actor(creator))
    ]
    assert len(staff_bodies) == 2


def test_writing_an_internal_note_needs_the_management_grant(seeded):
    """Discussing a task with the reporter is not the staff-only channel."""
    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    task = make(creator, "fairfax-va", "Has notes")

    commenter = ActorContext(
        user=person("commenter@example.com", "fairfax-va"),
        permissions=frozenset({TaskPermission.VIEW, TaskPermission.COMMENT}),
    )
    # An ordinary comment is fine…
    services.add_comment(actor=commenter, task=task, body="Any update?")

    # …the internal channel is not.
    with pytest.raises(Exception) as raised:
        services.add_comment(
            actor=commenter, task=task, body="Staff only", internal=True
        )
    assert "permission" in str(raised.value).lower()


def test_an_empty_comment_is_refused(seeded):
    from django.core.exceptions import ValidationError

    creator = person("creator@example.com", "onest-head-office")
    assign_role(creator, "system_admin", "company")
    task = make(creator, "fairfax-va", "Has notes")

    with pytest.raises(ValidationError):
        services.add_comment(actor=admin_actor(creator), task=task, body="   ")
