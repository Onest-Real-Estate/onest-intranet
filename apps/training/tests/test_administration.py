"""Training administration: scope, lifecycle, versioning, concurrency, media."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent, DomainEvent
from apps.training.administration import (
    StaleTrainingVersion,
    content_version,
    create_content,
    duplicate_version,
    manageable_queryset,
    preview_payload,
    transition,
    update_content,
)
from apps.training.audience import AudienceSelector
from apps.training.media_service import attach_media, media_publish_debt
from apps.training.models import TrainingContent, TrainingMedia, TrainingProgress
from apps.training.services import visible_queryset
from apps.training.tasks import process_training_media
from apps.training.tests.factories import (
    agent,
    assign,
    category,
    office,
    publish_content,
)
from apps.user.models import User
from apps.user.tests.test_profile import completed_user


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


def publisher(*, slug="fairfax-va", email="publisher@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, "system_admin", "company")
    return grant(user, "manage_training")


def regional_publisher(*, email="regional@example.com") -> User:
    user = completed_user(email=email, office=office("region-mid-atlantic"))
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    return grant(user, "manage_training")


def _draft(actor: User, **overrides) -> TrainingContent:
    cleaned = {
        "title": "Safety briefing",
        "summary": "Summary",
        "body": "Body copy",
        "category": category(),
        "content_type": "article",
        "estimated_minutes": 10,
        "tool_code": "",
        "external_url": "",
        "publish_at": None,
        "expires_at": None,
        "is_required": False,
    }
    cleaned.update(overrides)
    return create_content(
        actor=actor,
        office=office("fairfax-va"),
        cleaned=cleaned,
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
    )


@pytest.mark.django_db
def test_out_of_scope_content_is_404(seeded, client: Client):
    actor = regional_publisher()
    other = publish_content(
        slug="other-region",
        title="Other",
        owner_office=office("connecticut"),
    )
    assert not manageable_queryset(actor).filter(pk=other.pk).exists()
    client.force_login(actor)
    assert client.get(reverse("training_edit", args=[other.pk])).status_code == 404


@pytest.mark.django_db
def test_scoped_admin_cannot_assign_company_audience(seeded):
    actor = regional_publisher()
    with pytest.raises(PermissionDenied):
        create_content(
            actor=actor,
            office=office("fairfax-va"),
            cleaned={
                "title": "Company blast",
                "summary": "",
                "body": "Body",
                "category": category(),
                "content_type": "article",
                "estimated_minutes": None,
                "tool_code": "",
                "external_url": "",
                "publish_at": None,
                "expires_at": None,
                "is_required": True,
            },
            selectors=[AudienceSelector(kind="company")],
        )


@pytest.mark.django_db
def test_stale_version_refuses_update(seeded):
    actor = publisher()
    draft = _draft(actor)
    with pytest.raises(StaleTrainingVersion):
        update_content(
            actor=actor,
            content=draft,
            cleaned={"title": "Changed"},
            selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
            expected_version="not-the-token",
        )


@pytest.mark.django_db
def test_publish_blocked_while_media_pending(seeded):
    actor = publisher()
    draft = _draft(actor)
    upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.7\n" + b"x" * 40)
    media = attach_media(actor, draft, upload, role=TrainingMedia.Role.ATTACHMENT)
    assert media.processing_state == TrainingMedia.ProcessingState.PENDING
    assert media_publish_debt(draft)
    with pytest.raises(ValidationError):
        transition(
            actor=actor,
            content=draft,
            action="publish",
            expected_version=content_version(draft),
        )


@pytest.mark.django_db
def test_duplicate_version_and_supersede(seeded):
    actor = publisher()
    live = publish_content(
        slug="compliance-v1",
        title="Compliance",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    learner = agent(email="learner@example.com")
    TrainingProgress.objects.create(
        user=learner,
        content=live,
        status=TrainingProgress.Status.COMPLETED,
        completed_at=timezone.now(),
    )

    draft = duplicate_version(
        actor=actor, content=live, expected_version=content_version(live)
    )
    assert draft.status == TrainingContent.Status.DRAFT
    assert draft.version_family == live.version_family
    assert draft.version_number == 2
    assert AuditEvent.objects.filter(action="training.version_created").exists()

    transition(
        actor=actor,
        content=draft,
        action="publish",
        expected_version=content_version(draft),
    )
    live.refresh_from_db()
    draft.refresh_from_db()
    assert draft.status == TrainingContent.Status.PUBLISHED
    assert live.status == TrainingContent.Status.ARCHIVED
    assert TrainingProgress.objects.filter(
        user=learner, content=live, status=TrainingProgress.Status.COMPLETED
    ).exists()
    assert DomainEvent.objects.filter(name="training.published").exists()
    assert DomainEvent.objects.filter(name="training.archived").exists()


@pytest.mark.django_db
def test_preview_does_not_expose_draft_in_library(seeded):
    actor = publisher()
    draft = _draft(actor)
    reader = agent(email="reader@example.com")
    assert draft.pk not in visible_queryset(reader).values_list("pk", flat=True)
    preview = preview_payload(
        draft, actor=actor, office=office("fairfax-va"), role_code=""
    )
    assert preview["article"]["title"] == draft.title
    assert preview["reach"]["matched"] is True


@pytest.mark.django_db
def test_audience_and_required_audited(seeded):
    actor = publisher()
    draft = _draft(actor)
    update_content(
        actor=actor,
        content=draft,
        cleaned={"is_required": True},
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        expected_version=content_version(draft),
    )
    assert AuditEvent.objects.filter(action="training.audience_changed").exists()
    assert AuditEvent.objects.filter(action="training.required_changed").exists()


@pytest.mark.django_db
def test_create_defaults_display_order(seeded):
    actor = publisher()
    draft = _draft(actor)
    assert draft.display_order == 100


@pytest.mark.django_db
def test_json_create_path(seeded, client: Client):
    import json

    actor = publisher()
    client.force_login(actor)
    response = client.post(
        reverse("training_create"),
        data=json.dumps(
            {
                "owner_office": str(office("fairfax-va").pk),
                "title": "JSON draft",
                "summary": "",
                "body": "Hello",
                "category": "general",
                "content_type": "article",
                "is_required": False,
                "audience_offices": [str(office("fairfax-va").pk)],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {302, 303}, response.content[:2000]
    assert TrainingContent.objects.filter(title="JSON draft").exists()


@pytest.mark.django_db
def test_index_requires_permission(seeded, client: Client):
    reader = agent()
    client.force_login(reader)
    assert client.get(reverse("admin_training")).status_code == 403


@pytest.mark.django_db
def test_process_training_media_marks_ready(seeded):
    actor = publisher()
    draft = _draft(actor)
    upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.7\n" + b"x" * 40)
    media = attach_media(actor, draft, upload, role=TrainingMedia.Role.ATTACHMENT)
    assert process_training_media(media.pk) == TrainingMedia.ProcessingState.READY
    media.refresh_from_db()
    assert media.processing_state == TrainingMedia.ProcessingState.READY


@pytest.mark.django_db
def test_published_media_mutate_refused(seeded):
    actor = publisher()
    live = publish_content(
        slug="locked-files",
        title="Locked",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.7\n" + b"x" * 40)
    with pytest.raises(ValidationError):
        attach_media(actor, live, upload, role=TrainingMedia.Role.ATTACHMENT)


@pytest.mark.django_db
def test_archive_transition(seeded):
    actor = publisher()
    draft = _draft(actor)
    transition(
        actor=actor,
        content=draft,
        action="publish",
        expected_version=content_version(draft),
    )
    draft.refresh_from_db()
    transition(
        actor=actor,
        content=draft,
        action="archive",
        expected_version=content_version(draft),
    )
    draft.refresh_from_db()
    assert draft.status == TrainingContent.Status.ARCHIVED
    assert AuditEvent.objects.filter(action="training.archived").exists()


@pytest.mark.django_db
def test_json_quiz_save_configures_questions(seeded, client: Client):
    import json

    from apps.training.models import TrainingQuiz, TrainingQuizQuestion
    from apps.training.quiz_service import quiz_is_configured

    actor = publisher()
    draft = _draft(actor, content_type="quiz", title="Quiz draft")
    client.force_login(actor)
    response = client.post(
        reverse("training_quiz_save", args=[draft.pk]),
        data=json.dumps(
            {
                "passThresholdPercent": 70,
                "maxAttempts": 3,
                "feedbackPolicy": "score_only",
                "questions": json.dumps(
                    [
                        {
                            "prompt": "Which is fair housing?",
                            "choices": [
                                {"id": "a", "label": "Equal access"},
                                {"id": "b", "label": "Steering"},
                            ],
                            "correctChoiceIds": ["a"],
                            "sortOrder": 0,
                        }
                    ]
                ),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {302, 303}, response.content[:2000]
    draft.refresh_from_db()
    assert quiz_is_configured(draft)
    quiz = TrainingQuiz.objects.get(content=draft)
    assert quiz.pass_threshold_percent == 70
    assert TrainingQuizQuestion.objects.filter(quiz=quiz).count() == 1


@pytest.mark.django_db
def test_json_session_save_configures_schedule(seeded, client: Client):
    import json

    from apps.training.models import TrainingLiveSession
    from apps.training.session_service import session_is_configured

    actor = publisher()
    draft = _draft(actor, content_type="live_session", title="Session draft")
    client.force_login(actor)
    response = client.post(
        reverse("training_session_save", args=[draft.pk]),
        data=json.dumps(
            {
                "startsAt": "2026-10-01T15:00",
                "timezone": "America/New_York",
                "durationMinutes": 45,
                "capacity": 20,
                "meetingUrl": "https://meet.example/room",
                "registrationOpensAt": "",
                "registrationClosesAt": "",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {302, 303}, response.content[:2000]
    draft.refresh_from_db()
    assert session_is_configured(draft)
    session = TrainingLiveSession.objects.get(content=draft)
    assert session.duration_minutes == 45
    assert session.capacity == 20
    assert session.meeting_url == "https://meet.example/room"
