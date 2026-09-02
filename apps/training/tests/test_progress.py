"""Training progress writes, quizzes, sessions, and required-status tests."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.training.administration import (
    content_version,
    duplicate_version,
    transition,
)
from apps.training.models import (
    TrainingLiveSession,
    TrainingProgress,
    TrainingQuiz,
    TrainingQuizAttempt,
    TrainingQuizQuestion,
    TrainingSessionRegistration,
)
from apps.training.progress_service import (
    ProgressError,
    learner_update_progress,
    mark_completed,
    mark_started,
)
from apps.training.quiz_service import QuizError, save_quiz_definition, submit_attempt
from apps.training.required_status import (
    bulk_required_training_states,
    required_training_summary,
)
from apps.training.session_service import SessionError, cancel_registration, register
from apps.training.taxonomy import VERSION_POLICY_CURRENT
from apps.training.tests.factories import agent, assign, office, publish_content
from apps.user.models import User
from apps.user.services.onboarding_state import MilestoneStatus
from apps.user.services.role_assignments import get_effective_access
from apps.user.tests.test_profile import completed_user
from apps.web.dashboard.envelope import WidgetStatus
from apps.web.dashboard.providers import DashboardContext, training


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return User.objects.get(pk=user.pk)


def publisher() -> User:
    user = completed_user(email="publisher@example.com", office=office("fairfax-va"))
    assign(user, "system_admin", "company")
    return grant(user, "manage_training")


def _json_post(client: Client, url: str, data: dict, user: User):
    client.force_login(user)
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
    )


@pytest.mark.django_db
def test_progress_transitions_and_idempotent_audit(
    seeded, django_capture_on_commit_callbacks
):
    learner = agent(email="progress@example.com")
    content = publish_content(
        slug="ethics-101",
        title="Ethics 101",
        owner_office=office("fairfax-va"),
    )
    with django_capture_on_commit_callbacks(execute=True):
        first = mark_started(learner, content)
    assert first.status == TrainingProgress.Status.IN_PROGRESS
    assert first.started_at is not None

    with django_capture_on_commit_callbacks(execute=True):
        mark_started(learner, content)
    assert AuditEvent.objects.filter(action="training.progress_started").count() == 1

    with django_capture_on_commit_callbacks(execute=True):
        done = mark_completed(learner, content)
    assert done.status == TrainingProgress.Status.COMPLETED
    assert done.completed_at is not None
    assert done.progress_percent == 100

    with django_capture_on_commit_callbacks(execute=True):
        mark_completed(learner, content)
    assert AuditEvent.objects.filter(action="training.progress_completed").count() == 1


@pytest.mark.django_db
def test_learner_progress_post_self_only(seeded):
    learner = agent(email="self@example.com")
    other = agent(email="other@example.com")
    content = publish_content(
        slug="guide-1",
        title="Guide",
        owner_office=office("fairfax-va"),
    )
    response = _json_post(
        Client(),
        reverse("training_progress", args=[content.pk]),
        {"action": "complete"},
        learner,
    )
    assert response.status_code in {302, 303}
    assert TrainingProgress.objects.filter(
        user=learner, content=content, status=TrainingProgress.Status.COMPLETED
    ).exists()
    assert not TrainingProgress.objects.filter(user=other, content=content).exists()


@pytest.mark.django_db
def test_interactive_content_refuses_manual_complete(seeded):
    learner = agent(email="quiz-user@example.com")
    content = publish_content(
        slug="quiz-1",
        title="Quiz",
        owner_office=office("fairfax-va"),
        content_type="quiz",
    )
    with pytest.raises(ProgressError):
        learner_update_progress(learner, content, action="complete")


@pytest.mark.django_db
def test_quiz_server_side_grading_and_tamper_rejection(seeded):
    actor = publisher()
    learner = agent(email="quizzer@example.com")
    content = publish_content(
        slug="fair-housing-quiz",
        title="Fair housing quiz",
        owner_office=office("fairfax-va"),
        content_type="quiz",
        is_required=True,
    )
    content.status = content.Status.DRAFT
    content.save(update_fields=["status"])
    save_quiz_definition(
        actor=actor,
        content=content,
        pass_threshold_percent=50,
        max_attempts=2,
        feedback_policy="score_only",
        questions=[
            {
                "prompt": "Which is true?",
                "choices": [
                    {"id": "a", "label": "Correct"},
                    {"id": "b", "label": "Wrong"},
                ],
                "correctChoiceIds": ["a"],
                "sortOrder": 0,
            }
        ],
    )
    content.status = content.Status.PUBLISHED
    content.published_at = timezone.now()
    content.save(update_fields=["status", "published_at"])

    quiz = TrainingQuiz.objects.get(content=content)
    question = TrainingQuizQuestion.objects.filter(quiz=quiz).get()

    with pytest.raises(QuizError):
        submit_attempt(learner, content, {"scorePercent": "100"})

    result = submit_attempt(learner, content, {str(question.pk): "a"})
    assert result["feedback"]["passed"] is True
    assert result["feedback"]["scorePercent"] == 100
    assert TrainingProgress.objects.filter(
        user=learner, content=content, status=TrainingProgress.Status.COMPLETED
    ).exists()
    assert (
        TrainingQuizAttempt.objects.filter(user=learner, content=content).count() == 1
    )


@pytest.mark.django_db
def test_version_policy_current_requires_live_completion(seeded):
    actor = publisher()
    learner = agent(email="version@example.com")
    live = publish_content(
        slug="compliance-v1",
        title="Compliance",
        owner_office=office("fairfax-va"),
        is_required=True,
    )
    live.version_completion_policy = VERSION_POLICY_CURRENT
    live.save(update_fields=["version_completion_policy"])
    mark_completed(learner, live)

    summary = required_training_summary(learner)
    assert summary["completedCount"] == 1

    draft = duplicate_version(
        actor=actor, content=live, expected_version=content_version(live)
    )
    draft.version_completion_policy = VERSION_POLICY_CURRENT
    draft.is_required = True
    draft.save(update_fields=["version_completion_policy", "is_required"])
    transition(
        actor=actor,
        content=draft,
        action="publish",
        expected_version=content_version(draft),
    )

    summary_after = required_training_summary(learner)
    assert summary_after["requiredCount"] == 1
    assert summary_after["completedCount"] == 0
    assert TrainingProgress.objects.filter(
        user=learner, content=live, status=TrainingProgress.Status.COMPLETED
    ).exists()


@pytest.mark.django_db
def test_live_session_capacity_and_cancel(seeded):
    content = publish_content(
        slug="live-1",
        title="Live ethics",
        owner_office=office("fairfax-va"),
        content_type="live_session",
    )
    TrainingLiveSession.objects.create(
        content=content,
        starts_at=timezone.now() + timedelta(days=1),
        timezone="America/New_York",
        duration_minutes=60,
        capacity=1,
    )
    first = agent(email="seat1@example.com")
    second = agent(email="seat2@example.com")
    register(first, content)
    with pytest.raises(SessionError):
        register(second, content)
    cancel_registration(first, content)
    register(second, content)
    assert TrainingSessionRegistration.objects.filter(
        user=second, content=content, status="registered"
    ).exists()


@pytest.mark.django_db
def test_bulk_onboarding_states_deterministic(seeded):
    a = agent(email="a@example.com")
    b = agent(email="b@example.com")
    content = publish_content(
        slug="required-onboard",
        title="Required onboard",
        owner_office=office("fairfax-va"),
        is_required=True,
    )
    mark_completed(a, content)
    states = bulk_required_training_states([a, b])
    assert states[a.pk].status == MilestoneStatus.COMPLETE
    assert states[a.pk].completed_count == 1
    assert states[b.pk].status == MilestoneStatus.PENDING
    assert states[b.pk].completed_count == 0


@pytest.mark.django_db
def test_dashboard_training_provider_ready(seeded):
    learner = agent(email="dash@example.com")
    publish_content(
        slug="dash-required",
        title="Dash required",
        owner_office=office("fairfax-va"),
        is_required=True,
    )
    result = training(
        DashboardContext(
            user=learner,
            access=get_effective_access(learner),
            now=timezone.now(),
            feed_limit=5,
        )
    )
    assert result.status == WidgetStatus.READY
    assert result.data is not None
    assert result.data["percent"] == 0
