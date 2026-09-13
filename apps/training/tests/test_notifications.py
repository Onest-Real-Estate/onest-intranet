"""Required-training assignment notices."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.audit.models import DomainEvent
from apps.notifications.consumers import deliver_for_event
from apps.notifications.models import Notification
from apps.notifications.producers import EVENT_PRODUCERS
from apps.notifications.sources import resolve_sources
from apps.training.administration import content_version, transition, update_content
from apps.training.audience import AudienceSelector
from apps.training.models import TrainingContent, TrainingProgress
from apps.training.notification_schedule import release_scheduled_required_training
from apps.training.tests.factories import agent, assign, category, office
from apps.user.models import User
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def publisher(*, slug="fairfax-va", email="publisher@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, "system_admin", "company")
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web", codename="manage_training"
        )
    )
    return User.objects.get(pk=user.pk)


def _envelope(name: str, payload: dict, *, actor_id: str = "1") -> EventEnvelope:
    return EventEnvelope(
        id=uuid4(),
        name=name,
        version=1,
        occurred_at=timezone.now(),
        actor_id=actor_id,
        subject=str(payload.get("content_id") or "1"),
        organization_id="",
        correlation_id=None,
        causation_id=None,
        payload=payload,
    )


def _from_event(event: DomainEvent) -> EventEnvelope:
    return EventEnvelope(
        id=event.id,
        name=event.name,
        version=event.version,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        subject=event.subject,
        organization_id=event.organization_id,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        payload=event.payload,
    )


def _draft(actor, **overrides) -> TrainingContent:
    from apps.training.administration import create_content

    cleaned = {
        "title": "Fair housing",
        "summary": "Summary",
        "body": "Body copy",
        "category": category(),
        "content_type": "article",
        "estimated_minutes": 10,
        "tool_code": "",
        "external_url": "",
        "publish_at": None,
        "expires_at": None,
        "is_required": True,
    }
    cleaned.update(overrides)
    return create_content(
        actor=actor,
        office=office("fairfax-va"),
        cleaned=cleaned,
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
    )


def test_training_producers_are_registered():
    assert "training.published" in EVENT_PRODUCERS
    assert "training.required_changed" in EVENT_PRODUCERS


@pytest.mark.django_db
def test_required_publish_notifies_audience_except_the_publisher(seeded):
    actor = publisher()
    learner = agent(email="learner@example.com")
    draft = _draft(actor)
    transition(
        actor=actor,
        content=draft,
        action="publish",
        expected_version=content_version(draft),
    )
    event = DomainEvent.objects.get(name="training.published", subject=str(draft.pk))
    deliver_for_event(_from_event(event))

    rows = list(Notification.objects.filter(source_module="training"))
    recipients = {row.recipient_id for row in rows}
    assert learner.pk in recipients
    assert actor.pk not in recipients
    assert rows[0].title == "Required training was assigned to you"
    assert rows[0].action_key == "open_training_detail"


@pytest.mark.django_db
def test_optional_publish_notifies_nobody(seeded):
    actor = publisher()
    agent(email="learner@example.com")
    draft = _draft(actor, is_required=False)
    transition(
        actor=actor,
        content=draft,
        action="publish",
        expected_version=content_version(draft),
    )
    event = DomainEvent.objects.get(name="training.published", subject=str(draft.pk))
    deliver_for_event(_from_event(event))
    assert Notification.objects.filter(source_module="training").count() == 0


@pytest.mark.django_db
def test_scheduled_publish_does_not_notify_until_release(seeded):
    actor = publisher()
    learner = agent(email="learner@example.com")
    later = timezone.now() + timedelta(days=2)
    draft = _draft(actor, publish_at=later)
    transition(
        actor=actor,
        content=draft,
        action="schedule",
        expected_version=content_version(draft),
    )
    assert DomainEvent.objects.filter(name="training.scheduled").exists()
    assert not DomainEvent.objects.filter(name="training.published").exists()
    deliver_for_event(
        _envelope(
            "training.scheduled",
            {"content_id": draft.pk, "is_required": True},
            actor_id=str(actor.pk),
        )
    )
    assert Notification.objects.count() == 0

    draft.publish_at = timezone.now() - timedelta(minutes=1)
    draft.save(update_fields=["publish_at"])
    assert release_scheduled_required_training() == 1
    event = DomainEvent.objects.get(name="training.published", subject=str(draft.pk))
    deliver_for_event(_from_event(event))
    assert Notification.objects.filter(recipient=learner).count() == 1
    assert release_scheduled_required_training() == 0


@pytest.mark.django_db
def test_marking_live_content_required_notifies(seeded):
    actor = publisher()
    learner = agent(email="learner@example.com")
    draft = _draft(actor, is_required=False)
    live = transition(
        actor=actor,
        content=draft,
        action="publish",
        expected_version=content_version(draft),
    )
    deliver_for_event(
        _from_event(
            DomainEvent.objects.get(name="training.published", subject=str(live.pk))
        )
    )
    assert Notification.objects.count() == 0

    update_content(
        actor=actor,
        content=live,
        cleaned={"is_required": True},
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        expected_version=content_version(live),
    )
    event = DomainEvent.objects.get(
        name="training.required_changed", subject=str(live.pk)
    )
    deliver_for_event(_from_event(event))
    assert Notification.objects.filter(recipient=learner).count() == 1


@pytest.mark.django_db
def test_completed_learner_is_skipped(seeded):
    actor = publisher()
    learner = agent(email="done@example.com")
    draft = _draft(actor)
    transition(
        actor=actor,
        content=draft,
        action="publish",
        expected_version=content_version(draft),
    )
    TrainingProgress.objects.create(
        user=learner,
        content=draft,
        status=TrainingProgress.Status.COMPLETED,
        completed_at=timezone.now(),
    )
    event = DomainEvent.objects.get(name="training.published", subject=str(draft.pk))
    deliver_for_event(_from_event(event))
    assert Notification.objects.filter(recipient=learner).count() == 0


@pytest.mark.django_db
def test_resolver_hides_training_after_audience_loss(seeded):
    actor = publisher()
    learner = agent(email="learner@example.com")
    outsider = completed_user(
        email="outsider@example.com", office=office("connecticut")
    )
    assign(outsider, "realtor", "office", office("connecticut"))
    draft = _draft(actor)
    transition(
        actor=actor,
        content=draft,
        action="publish",
        expected_version=content_version(draft),
    )
    event = DomainEvent.objects.get(name="training.published", subject=str(draft.pk))
    deliver_for_event(_from_event(event))
    row = Notification.objects.get(recipient=learner)
    visible = resolve_sources(learner, [row])[row.public_id]
    hidden = resolve_sources(outsider, [row])[row.public_id]
    assert visible.available is True
    assert visible.detail == "Fair housing"
    assert hidden.available is False
