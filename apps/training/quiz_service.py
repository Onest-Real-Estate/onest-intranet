"""Server-side quiz definition and attempt grading."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.service import actor_from_user, log_on_commit, target_from_instance
from apps.training.audience import assert_visible
from apps.training.models import (
    TrainingContent,
    TrainingQuiz,
    TrainingQuizAttempt,
    TrainingQuizQuestion,
)
from apps.training.progress_service import mark_completed, mark_started
from apps.training.taxonomy import (
    CONTENT_TYPE_QUIZ,
    PROGRESS_SOURCE_QUIZ,
    QUIZ_FEEDBACK_NONE,
    QUIZ_FEEDBACK_REVIEW,
    QUIZ_FEEDBACK_SCORE_ONLY,
)
from apps.user.models import User


class QuizError(ValidationError):
    """Domain validation for quiz mutations."""


def get_quiz(content: TrainingContent) -> TrainingQuiz | None:
    return TrainingQuiz.objects.filter(content=content).first()


def quiz_is_configured(content: TrainingContent) -> bool:
    quiz = get_quiz(content)
    if quiz is None:
        return False
    return TrainingQuizQuestion.objects.filter(quiz=quiz).exists()


def _learner_choices(choices: list) -> list[dict[str, str]]:
    rows = []
    for item in choices or []:
        if not isinstance(item, dict):
            continue
        choice_id = str(item.get("id", "")).strip()
        label = str(item.get("label", "")).strip()
        if choice_id and label:
            rows.append({"id": choice_id, "label": label})
    return rows


def quiz_payload(content: TrainingContent, user: User) -> dict[str, Any] | None:
    quiz = get_quiz(content)
    if quiz is None:
        return None
    questions = list(
        TrainingQuizQuestion.objects.filter(quiz=quiz).order_by("sort_order", "pk")
    )
    attempts = list(
        TrainingQuizAttempt.objects.filter(user=user, content=content).order_by(
            "-attempt_number"
        )
    )
    attempt_count = len(attempts)
    remaining = None
    if quiz.max_attempts is not None:
        remaining = max(0, quiz.max_attempts - attempt_count)
    latest = attempts[0] if attempts else None
    return {
        "passThresholdPercent": quiz.pass_threshold_percent,
        "maxAttempts": quiz.max_attempts,
        "feedbackPolicy": quiz.feedback_policy,
        "attemptCount": attempt_count,
        "attemptsRemaining": remaining,
        "canAttempt": remaining is None or remaining > 0,
        "latestAttempt": (
            {
                "attemptNumber": latest.attempt_number,
                "scorePercent": latest.score_percent,
                "passed": latest.passed,
                "submittedAt": latest.submitted_at.isoformat(),
            }
            if latest
            else None
        ),
        "questions": [
            {
                "id": question.pk,
                "prompt": question.prompt,
                "choices": _learner_choices(question.choices),
                "sortOrder": question.sort_order,
            }
            for question in questions
        ],
    }


def _grade(
    questions: list[TrainingQuizQuestion],
    answers: dict[str, str],
) -> tuple[int, dict[int, bool]]:
    if not questions:
        raise QuizError({"questions": ["This quiz has no questions yet."]})
    results: dict[int, bool] = {}
    correct = 0
    for question in questions:
        submitted = str(answers.get(str(question.pk), "")).strip()
        expected = {str(item) for item in (question.correct_choice_ids or [])}
        # Single-choice MCQ: exactly one correct id expected.
        ok = submitted in expected and len(expected) >= 1
        results[question.pk] = ok
        if ok:
            correct += 1
    score = int(round((correct / len(questions)) * 100))
    return score, results


def _feedback_payload(
    quiz: TrainingQuiz,
    *,
    score: int,
    passed: bool,
    results: dict[int, bool],
    questions: list[TrainingQuizQuestion],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scorePercent": score,
        "passed": passed,
        "passThresholdPercent": quiz.pass_threshold_percent,
    }
    if quiz.feedback_policy == QUIZ_FEEDBACK_NONE:
        return {"passed": passed}
    if quiz.feedback_policy == QUIZ_FEEDBACK_SCORE_ONLY:
        return payload
    if quiz.feedback_policy == QUIZ_FEEDBACK_REVIEW:
        payload["questionResults"] = [
            {
                "id": question.pk,
                "correct": results.get(question.pk, False),
                "correctChoiceIds": [
                    str(item) for item in (question.correct_choice_ids or [])
                ],
            }
            for question in questions
        ]
        return payload
    return payload


@transaction.atomic
def submit_attempt(
    user: User,
    content: TrainingContent,
    answers: dict[str, str],
) -> dict[str, Any]:
    """Grade a quiz attempt server-side. Never trusts client scores."""
    assert_visible(user, content, reason="quiz_out_of_audience")
    if content.content_type != CONTENT_TYPE_QUIZ:
        raise QuizError({"content": ["This item is not a quiz."]})
    quiz = (
        TrainingQuiz.objects.select_for_update(of=("self",))
        .filter(content=content)
        .first()
    )
    if quiz is None:
        raise QuizError({"quiz": ["This quiz is not configured yet."]})

    questions = list(
        TrainingQuizQuestion.objects.filter(quiz=quiz).order_by("sort_order", "pk")
    )
    attempt_count = TrainingQuizAttempt.objects.filter(
        user=user, content=content
    ).count()
    if quiz.max_attempts is not None and attempt_count >= quiz.max_attempts:
        raise QuizError({"attempts": ["No attempts remaining."]})

    # Reject client-supplied score fields if present (callers should strip).
    if any(key in answers for key in ("score", "scorePercent", "passed")):
        raise QuizError({"answers": ["Client-calculated scores are not accepted."]})

    score, results = _grade(questions, answers)
    passed = score >= quiz.pass_threshold_percent
    attempt_number = attempt_count + 1
    attempt = TrainingQuizAttempt.objects.create(
        user=user,
        content=content,
        attempt_number=attempt_number,
        answers={str(k): str(v) for k, v in answers.items()},
        score_percent=score,
        passed=passed,
        content_version_number=content.version_number,
    )

    mark_started(
        user,
        content,
        source=PROGRESS_SOURCE_QUIZ,
        evidence={"attemptId": attempt.pk},
    )
    if passed:
        mark_completed(
            user,
            content,
            source=PROGRESS_SOURCE_QUIZ,
            evidence={"attemptId": attempt.pk, "scorePercent": score},
        )

    log_on_commit(
        "training.quiz_submitted",
        actor=actor_from_user(user),
        target=target_from_instance(attempt, label=content.title),
        metadata={
            "content_id": content.pk,
            "attempt_number": attempt_number,
            "score_percent": score,
            "passed": passed,
        },
    )

    remaining = None
    if quiz.max_attempts is not None:
        remaining = max(0, quiz.max_attempts - attempt_number)

    return {
        "attemptNumber": attempt_number,
        "attemptsRemaining": remaining,
        "submittedAt": attempt.submitted_at.isoformat(),
        "feedback": _feedback_payload(
            quiz,
            score=score,
            passed=passed,
            results=results,
            questions=questions,
        ),
    }


@transaction.atomic
def save_quiz_definition(
    *,
    actor: User,
    content: TrainingContent,
    pass_threshold_percent: int,
    max_attempts: int | None,
    feedback_policy: str,
    questions: list[dict[str, Any]],
) -> TrainingQuiz:
    from apps.training.administration import assert_can_author
    from apps.training.taxonomy import QUIZ_FEEDBACK_POLICY_CODES

    assert_can_author(actor, content.owner_office)
    if content.status != TrainingContent.Status.DRAFT:
        raise QuizError({"content": ["Quiz definitions can only change on drafts."]})
    if content.content_type != CONTENT_TYPE_QUIZ:
        raise QuizError({"content": ["This item is not a quiz."]})
    if pass_threshold_percent < 0 or pass_threshold_percent > 100:
        raise QuizError({"pass_threshold_percent": ["Must be between 0 and 100."]})
    if feedback_policy not in QUIZ_FEEDBACK_POLICY_CODES:
        raise QuizError({"feedback_policy": ["Unknown feedback policy."]})
    if max_attempts is not None and max_attempts < 1:
        raise QuizError({"max_attempts": ["Max attempts must be at least 1."]})

    quiz, _ = TrainingQuiz.objects.update_or_create(
        content=content,
        defaults={
            "pass_threshold_percent": pass_threshold_percent,
            "max_attempts": max_attempts,
            "feedback_policy": feedback_policy,
        },
    )
    TrainingQuizQuestion.objects.filter(quiz=quiz).delete()
    created = []
    for index, raw in enumerate(questions):
        prompt = str(raw.get("prompt", "")).strip()
        choices = raw.get("choices") or []
        correct = raw.get("correctChoiceIds") or raw.get("correct_choice_ids") or []
        if not prompt:
            raise QuizError({"questions": [f"Question {index + 1} needs a prompt."]})
        normalized_choices = _learner_choices(choices)
        if len(normalized_choices) < 2:
            raise QuizError(
                {"questions": [f"Question {index + 1} needs at least two choices."]}
            )
        correct_ids = [str(item) for item in correct]
        choice_ids = {item["id"] for item in normalized_choices}
        if not correct_ids or not set(correct_ids).issubset(choice_ids):
            raise QuizError(
                {"questions": [f"Question {index + 1} needs a valid correct choice."]}
            )
        created.append(
            TrainingQuizQuestion(
                quiz=quiz,
                prompt=prompt,
                choices=normalized_choices,
                correct_choice_ids=correct_ids,
                sort_order=int(raw.get("sortOrder", index)),
            )
        )
    TrainingQuizQuestion.objects.bulk_create(created)
    return quiz


def admin_quiz_payload(content: TrainingContent) -> dict[str, Any] | None:
    quiz = get_quiz(content)
    if quiz is None:
        return None
    return {
        "passThresholdPercent": quiz.pass_threshold_percent,
        "maxAttempts": quiz.max_attempts,
        "feedbackPolicy": quiz.feedback_policy,
        "questions": [
            {
                "id": question.pk,
                "prompt": question.prompt,
                "choices": question.choices,
                "correctChoiceIds": question.correct_choice_ids,
                "sortOrder": question.sort_order,
            }
            for question in TrainingQuizQuestion.objects.filter(quiz=quiz).order_by(
                "sort_order", "pk"
            )
        ],
    }
