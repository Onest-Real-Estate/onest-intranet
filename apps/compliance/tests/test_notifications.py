"""Mandatory policy publish notices and overdue reminder resolution."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.audit.models import DomainEvent
from apps.compliance.acknowledgements import acknowledge, record_access
from apps.compliance.administration import policy_version_token, transition
from apps.compliance.models import (
    PolicyRequirement,
    PolicyVersion,
    PolicyVersionAccess,
)
from apps.compliance.notification_schedule import release_effective_mandatory_policies
from apps.compliance.tasks import send_policy_ack_reminders
from apps.compliance.tests.factories import agent, publish_policy, publisher
from apps.notifications.consumers import deliver_for_event
from apps.notifications.models import Notification
from apps.notifications.producers import EVENT_PRODUCERS
from apps.notifications.sources import resolve_sources


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


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


def _ack(user, version):
    record_access(user, version, kind=PolicyVersionAccess.Kind.DETAIL)
    return acknowledge(
        user,
        version.pk,
        expected_checksum=version.content_checksum,
        disclosure_version=version.disclosure_version,
    )


def test_policy_published_producer_is_registered():
    assert "policy.published" in EVENT_PRODUCERS


@pytest.mark.django_db
def test_mandatory_publish_notifies_audience_except_the_publisher(seeded):
    actor = publisher()
    learner = agent(email="ack-me@example.com")
    learner.license_state = "VA"
    learner.save(update_fields=["license_state"])
    version = publish_policy(title="Mandatory handbook", is_mandatory=True, actor=actor)
    event = DomainEvent.objects.get(name="policy.published", subject=str(version.pk))
    deliver_for_event(_from_event(event))

    rows = list(Notification.objects.filter(event_key="policy.published"))
    recipients = {row.recipient_id for row in rows}
    assert learner.pk in recipients
    assert actor.pk not in recipients
    assert rows[0].is_mandatory is True
    assert rows[0].source_module == "compliance"
    assert rows[0].action_key == "open_policy_detail"


@pytest.mark.django_db
def test_optional_publish_notifies_nobody(seeded):
    actor = publisher()
    agent(email="reader@example.com")
    version = publish_policy(title="Optional guide", is_mandatory=False, actor=actor)
    event = DomainEvent.objects.get(name="policy.published", subject=str(version.pk))
    deliver_for_event(_from_event(event))
    assert Notification.objects.filter(event_key="policy.published").count() == 0


@pytest.mark.django_db
def test_jurisdiction_and_ack_skip_recipients(seeded):
    actor = publisher()
    va = agent(email="va@example.com")
    va.license_state = "VA"
    va.save(update_fields=["license_state"])
    md = agent(email="md@example.com")
    md.license_state = "MD"
    if md.office:
        md.office.state = "MD"
        md.office.save(update_fields=["state"])
    md.save(update_fields=["license_state"])
    already = agent(email="acked@example.com")
    already.license_state = "VA"
    already.save(update_fields=["license_state"])

    version = publish_policy(
        title="VA handbook",
        is_mandatory=True,
        jurisdiction_state_codes=["VA"],
        actor=actor,
    )
    _ack(already, version)
    event = DomainEvent.objects.get(name="policy.published", subject=str(version.pk))
    deliver_for_event(_from_event(event))

    recipients = set(
        Notification.objects.filter(event_key="policy.published").values_list(
            "recipient_id", flat=True
        )
    )
    assert va.pk in recipients
    assert md.pk not in recipients
    assert already.pk not in recipients


@pytest.mark.django_db
def test_future_effective_at_waits_for_release(seeded):
    actor = publisher()
    learner = agent(email="later@example.com")
    learner.license_state = "VA"
    learner.save(update_fields=["license_state"])
    version = publish_policy(
        title="Next quarter",
        is_mandatory=True,
        actor=actor,
        effective_at=timezone.now() + timedelta(days=7),
    )
    event = DomainEvent.objects.get(name="policy.published", subject=str(version.pk))
    deliver_for_event(_from_event(event))
    assert Notification.objects.filter(event_key="policy.published").count() == 0

    version.effective_at = timezone.now() - timedelta(minutes=1)
    version.save(update_fields=["effective_at", "updated_at"])
    assert release_effective_mandatory_policies() >= 1
    assert Notification.objects.filter(recipient=learner).count() == 1
    assert release_effective_mandatory_policies() == 0


@pytest.mark.django_db
def test_overdue_reminder_resolves_until_acknowledged(seeded):
    actor = publisher()
    learner = agent(email="overdue@example.com")
    learner.license_state = "VA"
    learner.save(update_fields=["license_state"])
    version = publish_policy(title="Ack overdue", is_mandatory=True, actor=actor)
    PolicyRequirement.objects.filter(policy_version=version).update(
        due_at=timezone.now() - timedelta(days=1)
    )
    assert send_policy_ack_reminders() >= 1
    for event in DomainEvent.objects.filter(name="policy.ack_reminder"):
        deliver_for_event(_from_event(event))
    row = Notification.objects.get(recipient=learner, event_key="policy.ack_reminder")
    assert row.source_module == "compliance"
    before = resolve_sources(learner, [row])[row.public_id]
    assert before.available is True
    assert before.detail == "Acknowledge Ack overdue"

    _ack(learner, version)
    after = resolve_sources(learner, [row])[row.public_id]
    assert after.available is False


@pytest.mark.django_db
def test_publish_notice_is_idempotent(seeded):
    actor = publisher()
    learner = agent(email="once@example.com")
    learner.license_state = "VA"
    learner.save(update_fields=["license_state"])
    version = publish_policy(title="Once", is_mandatory=True, actor=actor)
    envelope = _from_event(
        DomainEvent.objects.get(name="policy.published", subject=str(version.pk))
    )
    deliver_for_event(envelope)
    deliver_for_event(envelope)
    assert Notification.objects.filter(recipient=learner).count() == 1


@pytest.mark.django_db
def test_retired_policy_hides_notice(seeded):
    actor = publisher()
    learner = agent(email="retired@example.com")
    learner.license_state = "VA"
    learner.save(update_fields=["license_state"])
    version = publish_policy(title="Retire me", is_mandatory=True, actor=actor)
    deliver_for_event(
        _from_event(
            DomainEvent.objects.get(name="policy.published", subject=str(version.pk))
        )
    )
    row = Notification.objects.get(recipient=learner)
    transition(
        actor=actor,
        version=version,
        action="retire",
        expected_version=policy_version_token(version),
    )
    version.refresh_from_db()
    assert version.status == PolicyVersion.Status.RETIRED
    assert resolve_sources(learner, [row])[row.public_id].available is False
