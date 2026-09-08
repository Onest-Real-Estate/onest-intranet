"""The lifecycle, the actor matrix, and the two idempotency guarantees.

The through-line of this file is that a status is only ever changed by the
service, with an actor and an expected state. Several tests deliberately hand
the service a *stale* view of the world, so a regression that let a caller
overwrite somebody else's decision fails here rather than in production.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.operational_tasks import services
from apps.operational_tasks.models import OperationalTask, TaskComment
from apps.operational_tasks.services import (
    ActorContext,
    ConcurrentUpdate,
    TransitionError,
)
from apps.operational_tasks.taxonomy import (
    TaskCategory,
    TaskPermission,
    TaskPriority,
    TaskSource,
    TaskStatus,
    find_transition,
    transitions_from,
)
from apps.user.models import Office
from apps.user.tests.test_profile import completed_user

ALL_PERMS = frozenset(
    {
        TaskPermission.VIEW,
        TaskPermission.MANAGE,
        TaskPermission.ASSIGN,
        TaskPermission.COMMENT,
    }
)


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str = "fairfax-va") -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def actor(user, permissions=ALL_PERMS) -> ActorContext:
    return ActorContext(user=user, permissions=frozenset(permissions))


def make_task(admin, *, assignee=None, due_at=None, title="Provision CRM seat"):
    return services.create_task(
        actor=actor(admin),
        office=office(),
        category=TaskCategory.TOOL_SETUP,
        title=title,
        priority=TaskPriority.NORMAL,
        assignee=assignee,
        due_at=due_at,
    )


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #


def test_create_stamps_a_reference_and_opens_the_task(seeded):
    admin = person("admin@example.com")
    task = make_task(admin)

    assert task.status == TaskStatus.OPEN
    assert task.reference == f"TSK-{task.pk:06d}"
    assert task.reporter_pk == admin.pk
    assert task.closed_at is None


def test_create_requires_the_management_grant(seeded):
    reader = person("reader@example.com")
    with pytest.raises(PermissionDenied):
        services.create_task(
            actor=actor(reader, {TaskPermission.VIEW}),
            office=office(),
            category=TaskCategory.BUG,
            title="Nope",
            priority=TaskPriority.NORMAL,
        )


def test_assigning_needs_the_assign_or_manage_grant(seeded):
    """MANAGE implies ASSIGN; ASSIGN alone exists for a dispatcher who cannot
    otherwise manage the queue. Holding neither opens nothing."""
    admin = person("admin@example.com")
    other = person("other@example.com", "harrisburg")
    task = make_task(admin)

    dispatcher = actor(other, {TaskPermission.ASSIGN})
    assert (
        services.assign(actor=dispatcher, task=task, assignee=other).assignee_pk
        == other.pk
    )

    with pytest.raises(PermissionDenied):
        services.assign(
            actor=actor(other, {TaskPermission.VIEW}), task=task, assignee=None
        )


def test_create_rejects_a_category_outside_the_closed_vocabulary(seeded):
    admin = person("admin@example.com")
    with pytest.raises(ValidationError):
        services.create_task(
            actor=actor(admin),
            office=office(),
            category="not_a_category",
            title="Bad code",
            priority=TaskPriority.NORMAL,
        )


def test_create_rejects_an_unknown_priority(seeded):
    admin = person("admin@example.com")
    with pytest.raises(ValidationError):
        services.create_task(
            actor=actor(admin),
            office=office(),
            category=TaskCategory.BUG,
            title="Bad code",
            priority=99,
        )


def test_create_rejects_an_unknown_source(seeded):
    admin = person("admin@example.com")
    with pytest.raises(ValidationError):
        services.create_task(
            actor=actor(admin),
            office=office(),
            category=TaskCategory.BUG,
            title="Bad code",
            priority=TaskPriority.NORMAL,
            source="telepathy",
        )


def test_a_title_of_whitespace_is_not_a_title(seeded):
    admin = person("admin@example.com")
    with pytest.raises(ValidationError):
        services.create_task(
            actor=actor(admin),
            office=office(),
            category=TaskCategory.BUG,
            title="   ",
            priority=TaskPriority.NORMAL,
        )


# --------------------------------------------------------------------------- #
# Conversion idempotency
# --------------------------------------------------------------------------- #


def test_converting_the_same_feedback_twice_yields_one_task(seeded):
    """The acceptance criterion, stated as a test.

    A retried Celery task, a double-clicked button, and a replayed event all
    land here; none of them may produce a second row.
    """
    admin = person("admin@example.com")
    first = services.convert_from_feedback(
        actor=actor(admin),
        feedback_reference="fb-0001",
        office=office(),
        category=TaskCategory.BUG,
        title="Screenshot upload fails",
        priority=TaskPriority.HIGH,
    )
    second = services.convert_from_feedback(
        actor=actor(admin),
        feedback_reference="fb-0001",
        office=office(),
        category=TaskCategory.BUG,
        title="Screenshot upload fails (retry)",
        priority=TaskPriority.HIGH,
    )

    assert first.pk == second.pk
    assert OperationalTask.objects.filter(source_reference="fb-0001").count() == 1
    # Source identity survives conversion — losing it is the named failure mode.
    assert first.source == TaskSource.FEEDBACK
    assert first.source_reference == "fb-0001"


def test_conversion_copies_no_attachment_from_the_source(seeded):
    """A feedback screenshot stays under the feedback module's policy.

    Conversion carries a reference, never a file or a URL: a task reader is not
    automatically entitled to the reporter's screenshot.
    """
    admin = person("admin@example.com")
    task = services.convert_from_feedback(
        actor=actor(admin),
        feedback_reference="fb-0002",
        office=office(),
        category=TaskCategory.BUG,
        title="Converted",
        priority=TaskPriority.NORMAL,
    )
    from apps.operational_tasks.models import TaskAttachment

    assert TaskAttachment.objects.filter(task=task).count() == 0


# --------------------------------------------------------------------------- #
# Transitions
# --------------------------------------------------------------------------- #


def test_every_declared_transition_starts_and_ends_in_a_real_status(seeded):
    for move in transitions_from(TaskStatus.OPEN):
        assert find_transition(move.source, move.target) is move


def test_illegal_move_is_refused_with_the_current_state_named(seeded):
    admin = person("admin@example.com")
    task = make_task(admin)
    with pytest.raises(TransitionError):
        services.transition(actor=actor(admin), task=task, to_status=TaskStatus.CLOSED)


def test_unknown_target_status_is_a_refusal_not_a_crash(seeded):
    """A stale client naming a retired status gets the ordinary answer."""
    admin = person("admin@example.com")
    task = make_task(admin)
    with pytest.raises(TransitionError):
        services.transition(actor=actor(admin), task=task, to_status="teleported")


def test_repeating_a_transition_is_a_no_op(seeded):
    admin = person("admin@example.com")
    task = make_task(admin)
    services.transition(actor=actor(admin), task=task, to_status=TaskStatus.IN_PROGRESS)
    before = AuditEvent.objects.filter(action="operational_task.status_changed").count()

    again = services.transition(
        actor=actor(admin), task=task, to_status=TaskStatus.IN_PROGRESS
    )

    assert again.status == TaskStatus.IN_PROGRESS
    after = AuditEvent.objects.filter(action="operational_task.status_changed").count()
    assert after == before, "a repeat must not write a second audit event"


def test_expected_state_check_stops_the_loser_of_a_race(seeded):
    """Two people acting on the same board, one of them holding a stale view."""
    admin = person("admin@example.com")
    task = make_task(admin)
    services.transition(actor=actor(admin), task=task, to_status=TaskStatus.IN_PROGRESS)

    stale = OperationalTask.objects.get(pk=task.pk)
    stale.status = TaskStatus.OPEN  # what the second browser still believes

    with pytest.raises(ConcurrentUpdate):
        services.transition(
            actor=actor(admin),
            task=stale,
            to_status=TaskStatus.IN_PROGRESS,
            expected_status=TaskStatus.OPEN,
        )


def test_blocking_requires_an_explanation(seeded):
    admin = person("admin@example.com")
    task = make_task(admin)
    services.transition(actor=actor(admin), task=task, to_status=TaskStatus.IN_PROGRESS)
    with pytest.raises(ValidationError):
        services.transition(actor=actor(admin), task=task, to_status=TaskStatus.BLOCKED)

    moved = services.transition(
        actor=actor(admin),
        task=task,
        to_status=TaskStatus.BLOCKED,
        note="Vendor has not provisioned the licence.",
    )
    assert moved.status == TaskStatus.BLOCKED


def test_the_note_on_a_transition_is_an_internal_comment(seeded):
    """The reason for a staff decision is staff-only; the outcome is notified."""
    admin = person("admin@example.com")
    task = make_task(admin)
    services.transition(actor=actor(admin), task=task, to_status=TaskStatus.IN_PROGRESS)
    services.transition(
        actor=actor(admin),
        task=task,
        to_status=TaskStatus.BLOCKED,
        note="Vendor is stalling on the contract.",
    )
    note = TaskComment.objects.get(task=task)
    assert note.internal is True


def test_closing_and_reopening_move_the_closed_timestamp(seeded):
    admin = person("admin@example.com")
    task = make_task(admin)
    services.transition(actor=actor(admin), task=task, to_status=TaskStatus.IN_PROGRESS)
    services.transition(actor=actor(admin), task=task, to_status=TaskStatus.RESOLVED)
    closed = services.transition(
        actor=actor(admin), task=task, to_status=TaskStatus.CLOSED
    )
    assert closed.closed_at is not None

    reopened = services.transition(
        actor=actor(admin), task=closed, to_status=TaskStatus.IN_PROGRESS
    )
    assert reopened.status == TaskStatus.IN_PROGRESS
    assert reopened.closed_at is None
    assert reopened.resolved_at is None


# --------------------------------------------------------------------------- #
# The actor matrix
# --------------------------------------------------------------------------- #


def test_assignee_may_progress_their_own_work_without_the_manage_grant(seeded):
    admin = person("admin@example.com")
    worker = person("worker@example.com")
    task = make_task(admin, assignee=worker)

    moved = services.transition(
        actor=actor(worker, {TaskPermission.VIEW}),
        task=task,
        to_status=TaskStatus.IN_PROGRESS,
    )
    assert moved.status == TaskStatus.IN_PROGRESS


def test_assignee_may_not_close_even_their_own_task(seeded):
    """Finishing work and signing it off are different decisions."""
    admin = person("admin@example.com")
    worker = person("worker@example.com")
    task = make_task(admin, assignee=worker)
    services.transition(
        actor=actor(worker, {TaskPermission.VIEW}),
        task=task,
        to_status=TaskStatus.IN_PROGRESS,
    )
    services.transition(
        actor=actor(worker, {TaskPermission.VIEW}),
        task=task,
        to_status=TaskStatus.RESOLVED,
    )

    with pytest.raises(PermissionDenied):
        services.transition(
            actor=actor(worker, {TaskPermission.VIEW}),
            task=task,
            to_status=TaskStatus.CLOSED,
        )


def test_a_bystander_cannot_move_somebody_elses_task(seeded):
    admin = person("admin@example.com")
    worker = person("worker@example.com")
    bystander = person("bystander@example.com")
    task = make_task(admin, assignee=worker)

    with pytest.raises(PermissionDenied):
        services.transition(
            actor=actor(bystander, {TaskPermission.VIEW}),
            task=task,
            to_status=TaskStatus.IN_PROGRESS,
        )


def test_available_transitions_match_what_the_service_will_accept(seeded):
    """The UI renders from this list, so it must not over-promise."""
    admin = person("admin@example.com")
    worker = person("worker@example.com")
    task = make_task(admin, assignee=worker)
    worker_actor = actor(worker, {TaskPermission.VIEW})

    offered = {t.target for t in services.available_transitions(task, worker_actor)}
    assert offered == {TaskStatus.IN_PROGRESS}

    for move in transitions_from(task.status):
        if move.target in offered:
            continue
        with pytest.raises(PermissionDenied):
            services.transition(
                actor=worker_actor, task=task, to_status=move.target, note="x"
            )


# --------------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------------- #


def test_assignment_records_an_audit_event(
    seeded, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    admin = person("admin@example.com")
    worker = person("worker@example.com")
    task = make_task(admin)

    # The audit write is deliberately after commit: an event describing a
    # change that rolled back would be worse than no event at all.
    with django_capture_on_commit_callbacks(execute=True):
        services.assign(actor=actor(admin), task=task, assignee=worker)

    event = AuditEvent.objects.filter(action="operational_task.assigned").latest("pk")
    assert event.metadata["to"] == worker.pk


def test_assignment_rejects_a_stale_expected_assignee(seeded):
    admin = person("admin@example.com")
    first = person("first@example.com")
    second = person("second@example.com")
    task = make_task(admin)
    services.assign(actor=actor(admin), task=task, assignee=first)

    with pytest.raises(ConcurrentUpdate):
        services.assign(
            actor=actor(admin),
            task=task,
            assignee=second,
            expected_assignee_id=None,  # "I believe this is unassigned"
        )


def test_a_closed_task_cannot_be_reassigned(seeded):
    admin = person("admin@example.com")
    worker = person("worker@example.com")
    task = make_task(admin)
    services.transition(actor=actor(admin), task=task, to_status=TaskStatus.IN_PROGRESS)
    services.transition(
        actor=actor(admin),
        task=task,
        to_status=TaskStatus.CANCELLED,
        note="Duplicate of TSK-000001.",
    )

    with pytest.raises(ValidationError):
        services.assign(actor=actor(admin), task=task, assignee=worker)


# --------------------------------------------------------------------------- #
# Overdue
# --------------------------------------------------------------------------- #


def test_a_closed_task_is_never_overdue(seeded):
    admin = person("admin@example.com")
    past = timezone.now() - timezone.timedelta(days=3)
    task = make_task(admin, due_at=past)
    assert task.is_overdue() is True

    services.transition(actor=actor(admin), task=task, to_status=TaskStatus.IN_PROGRESS)
    cancelled = services.transition(
        actor=actor(admin),
        task=task,
        to_status=TaskStatus.CANCELLED,
        note="Not needed after all.",
    )
    # The service returns the locked row; the caller's stale instance is
    # deliberately not mutated behind their back.
    assert cancelled.is_overdue() is False
    assert OperationalTask.objects.overdue().filter(pk=task.pk).exists() is False


def test_the_permission_family_is_not_the_celery_status_grant(seeded):
    """Guards the decision this module was named for.

    ``web.view_platform_tasks`` means "read sanitized job status" and is held
    by roles that were never granted a scoped work queue. Holding it alone must
    open nothing here.
    """
    reader = person("reader@example.com")
    celery_only = actor(reader, {"web.view_platform_tasks"})
    assert celery_only.holds(TaskPermission.VIEW) is False
    assert celery_only.holds(TaskPermission.MANAGE) is False

    assert Permission.objects.filter(
        content_type__app_label="web", codename="view_operational_tasks"
    ).exists()
