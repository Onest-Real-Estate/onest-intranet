"""Transactional agent-contract emails across lifecycle changes."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core import mail
from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.contract.emails import (
    send_lifecycle_status_email,
    send_signed_confirmation_email,
    send_signing_invite_email,
)
from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import ContractTemplate, ContractTemplateVersion
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, company_admin
from apps.notifications.producers import (
    EVENT_PRODUCERS,
    contract_pdf_ready,
    contract_signed,
    notifications_for_event,
)


def _published_template(*, key="email-ica") -> ContractTemplateVersion:
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
    version = _published_template(key=f"email-ica-{recipient.pk}")
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


@pytest.mark.django_db
def test_signing_invite_email_content(seeded_offices, settings):
    settings.SITE_BASE_URL = "https://hub.example.test"
    recipient = agent(seeded_offices, email="invitee@example.com")
    contract = _issued(seeded_offices, recipient)
    send_signing_invite_email(contract)
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["invitee@example.com"]
    assert "ready to sign" in message.subject.lower()
    assert "/my-contract/sign" in message.body
    assert str(contract.public_id) in message.body
    assert "prepared and issued" in message.body.lower()


@pytest.mark.django_db
def test_signed_confirmation_email_content(seeded_offices, settings):
    settings.SITE_BASE_URL = "https://hub.example.test"
    recipient = agent(seeded_offices, email="signer@example.com")
    contract = _issued(seeded_offices, recipient)
    send_signed_confirmation_email(contract)
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["signer@example.com"]
    assert "signed" in message.subject.lower()
    assert "/my-contract" in message.body


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "needle"),
    [
        ("issue", "issued"),
        ("mark_signed", "signed"),
        ("activate", "active"),
        ("supersede", "superseded"),
        ("terminate", "terminated"),
        ("expire", "expired"),
    ],
)
def test_lifecycle_status_email_copy(seeded_offices, settings, action, needle):
    settings.SITE_BASE_URL = "https://hub.example.test"
    recipient = agent(seeded_offices, email=f"lifecycle-{action}@example.com")
    contract = _issued(seeded_offices, recipient)
    send_lifecycle_status_email(contract, action=action)
    assert len(mail.outbox) == 1
    assert needle in mail.outbox[0].subject.lower()
    assert mail.outbox[0].to == [f"lifecycle-{action}@example.com"]
    assert "/my-contract" in mail.outbox[0].body


@pytest.mark.django_db(transaction=True)
def test_mark_signed_sends_confirmation_email(
    seeded_offices, django_capture_on_commit_callbacks
):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="signed-mail@example.com")
    contract = _issued(seeded_offices, recipient, admin=admin)
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        transition(
            actor=admin,
            contract=contract,
            action="mark_signed",
            expected_version=contract_version(contract),
        )
    contract.refresh_from_db()
    assert contract.status == ContractStatus.SIGNED
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["signed-mail@example.com"]
    assert "signed" in mail.outbox[0].subject.lower()


@pytest.mark.django_db(transaction=True)
def test_terminate_sends_email(seeded_offices, django_capture_on_commit_callbacks):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="term-mail@example.com")
    contract = _issued(seeded_offices, recipient, admin=admin)
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        transition(
            actor=admin,
            contract=contract,
            action="terminate",
            expected_version=contract_version(contract),
            confirmed=True,
        )
    contract.refresh_from_db()
    assert contract.status == ContractStatus.TERMINATED
    assert len(mail.outbox) == 1
    assert "terminated" in mail.outbox[0].subject.lower()
    assert mail.outbox[0].to == ["term-mail@example.com"]


def test_contract_signed_producer_targets_signer():
    envelope = _envelope(
        "contract.signed",
        {
            "contract_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "signer_id": "42",
            "signed_at": "2026-08-30T00:00:00+00:00",
        },
    )
    [request] = contract_signed(envelope)
    assert request.recipient_id == 42
    assert request.action_key == "open_my_contract"
    assert request.dedupe_key.endswith("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert notifications_for_event(envelope) == [request]


def test_contract_pdf_ready_producer_points_at_sign():
    envelope = _envelope(
        "contract.pdf_ready",
        {
            "contract_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "office_id": "1",
            "agent_id": "7",
            "artifact_id": "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee",
            "checksum": "a" * 64,
            "occurred_at": "2026-08-30T00:00:00+00:00",
        },
    )
    [request] = contract_pdf_ready(envelope)
    assert request.recipient_id == 7
    assert request.action_key == "open_my_contract_sign"
    assert "ready to sign" in request.title.lower()


@pytest.mark.parametrize(
    "event_name",
    [
        "contract.issued",
        "contract.activated",
        "contract.superseded",
        "contract.terminated",
        "contract.expired",
    ],
)
def test_lifecycle_producers_registered(event_name):
    envelope = _envelope(
        event_name,
        {
            "contract_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "office_id": "1",
            "agent_id": "9",
            "status": event_name.split(".")[-1],
            "occurred_at": "2026-08-30T00:00:00+00:00",
        },
    )
    assert event_name in EVENT_PRODUCERS
    [request] = notifications_for_event(envelope)
    assert request.recipient_id == 9
    assert request.action_key == "open_my_contract"
