"""Contract notification producers, schedule, and staff recipients."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import (
    AgentContract,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.notification_recipients import operational_staff_ids
from apps.contract.notification_schedule import (
    publish_expiration_warnings,
    publish_signature_reminders,
    suppress_stale_reminders,
)
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, company_admin
from apps.notifications.contract import NotificationPriority
from apps.notifications.models import Notification
from apps.notifications.producers import (
    EVENT_PRODUCERS,
    contract_expiration_warning,
    contract_generation_error,
    contract_signature_reminder,
    contract_viewed,
    notifications_for_event,
)
from apps.notifications.service import deliver_many


def _published_template(*, key: str) -> ContractTemplateVersion:
    template = ContractTemplate.objects.create(
        stable_key=key,
        name="ICA",
        status=ContractTemplate.Status.ACTIVE,
        company_wide=True,
    )
    version = ContractTemplateVersion.objects.create(
        template=template,
        version_label="1.0.0",
        status=ContractTemplateVersion.Status.PUBLISHED,
    )
    template.active_version = version
    template.save(update_fields=["active_version", "updated_at"])
    return version


def _issued(seeded_offices, recipient, *, admin=None):
    admin = admin or company_admin(seeded_offices)
    version = _published_template(key=f"notif-ica-{recipient.pk}")
    draft = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
        agent_split_percent="70",
        office_split_percent="30",
    )
    ready = transition(
        actor=admin,
        contract=draft,
        action="submit_for_review",
        expected_version=contract_version(draft),
    )
    with (
        patch("apps.contract.lifecycle._queue_pdf_generation"),
        patch("apps.contract.lifecycle._queue_agent_status_email"),
    ):
        return transition(
            actor=admin,
            contract=ready,
            action="issue",
            expected_version=contract_version(ready),
            confirmed=True,
        )


def _envelope(name: str, payload: dict) -> EventEnvelope:
    return EventEnvelope(
        id=uuid4(),
        name=name,
        version=1,
        occurred_at=timezone.now(),
        actor_id="1",
        subject="contract:1",
        organization_id="",
        correlation_id=None,
        causation_id=None,
        payload=payload,
    )


@pytest.mark.parametrize(
    "event_name",
    [
        "contract.viewed",
        "contract.generation_error",
        "contract.signature_reminder",
        "contract.expiration_warning",
    ],
)
def test_new_contract_producers_registered(event_name):
    assert event_name in EVENT_PRODUCERS


def test_contract_viewed_targets_staff_only():
    envelope = _envelope(
        "contract.viewed",
        {
            "contract_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "office_id": "1",
            "agent_id": "9",
            "status": "viewed",
            "occurred_at": "2026-08-30T00:00:00+00:00",
            "staff_ids": [3, 5],
        },
    )
    requests = contract_viewed(envelope)
    assert {row.recipient_id for row in requests} == {3, 5}
    assert all(not row.is_mandatory for row in requests)
    assert all(row.action_key == "open_agent_contract" for row in requests)
    assert all(row.priority == NotificationPriority.LOW for row in requests)


def test_generation_error_is_mandatory_for_staff():
    envelope = _envelope(
        "contract.generation_error",
        {
            "contract_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "office_id": "1",
            "agent_id": "9",
            "status": "generation_error",
            "occurred_at": "2026-08-30T00:00:00+00:00",
            "staff_ids": [4],
        },
    )
    [request] = contract_generation_error(envelope)
    assert request.recipient_id == 4
    assert request.is_mandatory is True
    assert "PDF" in request.title


def test_signature_reminder_dedupes_per_day():
    envelope = _envelope(
        "contract.signature_reminder",
        {
            "contract_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "office_id": "1",
            "agent_id": "9",
            "reminder_day": "7",
            "occurred_at": "2026-08-30T00:00:00+00:00",
        },
    )
    [request] = contract_signature_reminder(envelope)
    assert request.recipient_id == 9
    assert request.is_mandatory is True
    assert request.dedupe_key.endswith(":day:7")
    assert request.action_key == "open_my_contract_sign"


def test_expiration_warning_reaches_agent_and_staff():
    envelope = _envelope(
        "contract.expiration_warning",
        {
            "contract_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "office_id": "1",
            "agent_id": "9",
            "warning_day": "14",
            "occurred_at": "2026-08-30T00:00:00+00:00",
            "staff_ids": [2],
        },
    )
    requests = contract_expiration_warning(envelope)
    by_recipient = {row.recipient_id: row for row in requests}
    assert by_recipient[9].is_mandatory is True
    assert by_recipient[2].is_mandatory is False
    assert by_recipient[2].action_key == "open_agent_contract"


@pytest.mark.django_db
def test_operational_staff_includes_creator(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = _issued(seeded_offices, recipient, admin=admin)
    staff = operational_staff_ids(contract)
    assert admin.pk in staff
    assert recipient.pk not in staff


@pytest.mark.django_db
def test_suppress_stale_reminders_after_sign(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = _issued(seeded_offices, recipient, admin=admin)
    from django.core.files.base import ContentFile

    from apps.contract.models import ContractArtifact

    artifact = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name="review.pdf",
        media_type="application/pdf",
        byte_size=10,
        checksum="a" * 64,
        created_by=admin,
    )
    artifact.file.save("review.pdf", ContentFile(b"%PDF-1.4 test"), save=False)
    artifact.save()
    contract.generated_pdf = artifact
    contract.save(update_fields=["generated_pdf", "updated_at"])
    deliver_many(
        notifications_for_event(
            _envelope(
                "contract.signature_reminder",
                {
                    "contract_id": str(contract.public_id),
                    "office_id": str(contract.office_id),
                    "agent_id": str(recipient.pk),
                    "reminder_day": "3",
                    "occurred_at": timezone.now().isoformat(),
                },
            )
        )
    )
    assert Notification.objects.filter(
        recipient=recipient, event_key="contract.signature_reminder"
    ).exists()
    with patch("apps.contract.lifecycle._queue_agent_status_email"):
        transition(
            actor=admin,
            contract=contract,
            action="mark_signed",
            expected_version=contract_version(contract),
        )
    contract.refresh_from_db()
    assert contract.status == ContractStatus.SIGNED
    # on_commit callbacks may not run outside transaction=True; call directly.
    suppress_stale_reminders(contract)
    row = Notification.objects.get(
        recipient=recipient, event_key="contract.signature_reminder"
    )
    assert row.expires_at is not None
    assert row.is_expired()


@pytest.mark.django_db
def test_signature_reminder_schedule_skips_non_signable(seeded_offices, settings):
    settings.CONTRACT_SIGNATURE_REMINDER_DAYS = (3,)
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = _issued(seeded_offices, recipient, admin=admin)
    contract.sent_at = timezone.now() - timedelta(days=3)
    contract.save(update_fields=["sent_at", "updated_at"])
    # No generated PDF → not reminder-eligible.
    assert publish_signature_reminders() == 0


@pytest.mark.django_db
def test_signature_reminder_publishes_when_due(seeded_offices, settings):
    settings.CONTRACT_SIGNATURE_REMINDER_DAYS = (3,)
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = _issued(seeded_offices, recipient, admin=admin)
    from django.core.files.base import ContentFile

    from apps.contract.models import ContractArtifact

    artifact = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name="review.pdf",
        media_type="application/pdf",
        byte_size=10,
        checksum="a" * 64,
        created_by=admin,
    )
    artifact.file.save("review.pdf", ContentFile(b"%PDF-1.4 test"), save=False)
    artifact.save()
    contract.generated_pdf = artifact
    contract.sent_at = timezone.now() - timedelta(days=3)
    contract.save(update_fields=["generated_pdf", "sent_at", "updated_at"])
    with patch("apps.contract.notification_schedule.publish_event") as publish:
        assert publish_signature_reminders() == 1
        publish.assert_called_once()
        assert publish.call_args.args[0] == "contract.signature_reminder"


@pytest.mark.django_db
def test_expiration_warning_publishes_for_active(seeded_offices, settings):
    settings.CONTRACT_EXPIRATION_WARNING_DAYS = (14,)
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = _issued(seeded_offices, recipient, admin=admin)
    with patch("apps.contract.lifecycle._queue_agent_status_email"):
        signed = transition(
            actor=admin,
            contract=contract,
            action="mark_signed",
            expected_version=contract_version(contract),
        )
        active = transition(
            actor=admin,
            contract=signed,
            action="activate",
            expected_version=contract_version(signed),
            confirmed=True,
        )
    target = timezone.localdate() + timedelta(days=14)
    # Bypass model.save immutability — same pattern as expire_due_contracts tests.
    AgentContract.objects.filter(pk=active.pk).update(expires_on=target)
    with patch("apps.contract.notification_schedule.publish_event") as publish:
        assert publish_expiration_warnings(as_of=timezone.localdate()) == 1
        assert publish.call_args.args[0] == "contract.expiration_warning"
