"""Contract review-PDF generation via Hub Prefill field fill."""

from __future__ import annotations

import io
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from apps.audit.models import AuditEvent, DomainEvent
from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import (
    ContractArtifact,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.pdf_generation import (
    RENDERER_VERSION,
    attach_generated_pdf,
    build_merge_values,
    generate_and_store,
    render_contract_pdf,
)
from apps.contract.pdf_signing import RENDERER_VERSION as SIGN_RENDERER
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tasks import cleanup_orphan_contract_artifacts, generate_contract_pdf
from apps.contract.template_security import checksum_of
from apps.contract.tests.conftest import agent, company_admin, office

assert RENDERER_VERSION == SIGN_RENDERER


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _hub_layout() -> list[dict]:
    return [
        {
            "id": "a",
            "name": "party.legalFirstName",
            "type": "text",
            "role": "Prefill",
            "page": 1,
            "x": 72,
            "y": 120,
            "w": 140,
            "h": 18,
        },
        {
            "id": "b",
            "name": "AgentSignature",
            "type": "signature",
            "role": "Agent",
            "page": 1,
            "x": 72,
            "y": 640,
            "w": 200,
            "h": 40,
        },
        {
            "id": "c",
            "name": "AgentDate",
            "type": "date",
            "role": "Agent",
            "page": 1,
            "x": 300,
            "y": 640,
            "w": 100,
            "h": 24,
        },
    ]


def _published_pdf_template(
    seeded_offices, *, key: str = "ica-pdf", admin=None
) -> ContractTemplateVersion:
    admin = admin or company_admin(seeded_offices)
    template = ContractTemplate.objects.create(
        stable_key=key,
        name="ICA PDF",
        status=ContractTemplate.Status.ACTIVE,
        company_wide=True,
        created_by=admin,
    )
    pdf = _blank_pdf()
    version = ContractTemplateVersion.objects.create(
        template=template,
        version_label="v1",
        status=ContractTemplateVersion.Status.PUBLISHED,
        source_format="pdf",
        source_media_type="application/pdf",
        source_checksum=checksum_of(pdf),
        field_layout=_hub_layout(),
        extracted_placeholder_keys=["party.legalFirstName"],
        merge_schema=[
            {
                "key": "party.legalFirstName",
                "label": "Legal first name",
                "type": "text",
                "source": "party.legalFirstName",
            }
        ],
        created_by=admin,
        published_at=timezone.now(),
        approved_by=admin,
    )
    version.source_document.save("blank.pdf", ContentFile(pdf), save=True)
    version.preview_pdf.save("preview.pdf", ContentFile(pdf), save=True)
    version.preview_checksum = checksum_of(pdf)
    version.save()
    template.active_version = version
    template.save(update_fields=["active_version"])
    return version


def _issued_contract(seeded_offices):
    admin = company_admin(seeded_offices)
    version = _published_pdf_template(seeded_offices, admin=admin)
    recipient = agent(seeded_offices)
    with patch("apps.contract.tasks.generate_contract_pdf.delay"):
        contract = create_draft_contract(
            actor=admin,
            recipient=recipient,
            office=office("onest-head-office"),
            template_version=version,
            effective_on=date.today(),
            expires_on=date.today() + timedelta(days=365),
            agent_split_percent="70",
            office_split_percent="30",
        )
        transition(
            actor=admin,
            contract=contract,
            action="submit_for_review",
            expected_version=contract_version(contract),
        )
        contract.refresh_from_db()
        transition(
            actor=admin,
            contract=contract,
            action="issue",
            expected_version=contract_version(contract),
            confirmed=True,
        )
        contract.refresh_from_db()
    return contract


@pytest.mark.django_db
def test_build_merge_values_from_frozen_snapshots(seeded_offices):
    contract = _issued_contract(seeded_offices)
    values = build_merge_values(contract)
    assert values["party.legalFirstName"]


@pytest.mark.django_db
def test_render_uses_hub_prefill(seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    contract = _issued_contract(seeded_offices)
    rendered = render_contract_pdf(contract)
    assert rendered.checksum
    assert rendered.page_count == 1
    assert "party.legalFirstName" in rendered.merge_values


@pytest.mark.django_db
def test_generate_and_store_is_idempotent(
    seeded_offices, settings, tmp_path, django_capture_on_commit_callbacks
):
    settings.MEDIA_ROOT = tmp_path
    contract = _issued_contract(seeded_offices)
    with patch("apps.contract.emails.send_signing_invite_email"):
        with django_capture_on_commit_callbacks(execute=True):
            first = generate_and_store(contract.pk)
        second = generate_and_store(contract.pk)
    assert first == "ready"
    assert second == "ready_idempotent"
    contract.refresh_from_db()
    assert contract.generated_pdf_id
    assert (
        ContractArtifact.objects.filter(
            contract=contract, kind=ContractArtifact.Kind.GENERATED_PDF
        ).count()
        == 1
    )
    assert DomainEvent.objects.filter(name="contract.pdf_ready").count() == 1


@pytest.mark.django_db
def test_task_duplicate_delivery_idempotent(seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    contract = _issued_contract(seeded_offices)
    with patch("apps.contract.emails.send_signing_invite_email"):
        assert generate_contract_pdf(contract.pk) == "ready"
        assert generate_contract_pdf(contract.pk) == "ready_idempotent"


@pytest.mark.django_db
def test_nonretryable_failure_marks_error_without_raise(
    seeded_offices, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    contract = _issued_contract(seeded_offices)
    contract.template_version.field_layout = []
    contract.template_version.save(update_fields=["field_layout"])
    outcome = generate_and_store(contract.pk)
    assert outcome.startswith("failed:")
    contract.refresh_from_db()
    assert contract.status == ContractStatus.GENERATION_ERROR


@pytest.mark.django_db
def test_artifact_download_authorized(client, seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    contract = _issued_contract(seeded_offices)
    with patch("apps.contract.emails.send_signing_invite_email"):
        generate_and_store(contract.pk)
    contract.refresh_from_db()
    artifact = contract.generated_pdf
    assert artifact is not None

    recipient = contract.recipient
    client.force_login(recipient)
    ok = client.get(
        reverse(
            "agent_contract_artifact_download",
            kwargs={
                "public_id": contract.public_id,
                "artifact_public_id": artifact.public_id,
            },
        )
    )
    assert ok.status_code == 200

    outsider = agent(seeded_offices, email="outsider-pdf@example.com")
    client.force_login(outsider)
    denied = client.get(
        reverse(
            "agent_contract_artifact_download",
            kwargs={
                "public_id": contract.public_id,
                "artifact_public_id": artifact.public_id,
            },
        )
    )
    assert denied.status_code == 404


@pytest.mark.django_db
def test_orphan_cleanup_preserves_current(seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    contract = _issued_contract(seeded_offices)
    with patch("apps.contract.emails.send_signing_invite_email"):
        generate_and_store(contract.pk)
    contract.refresh_from_db()
    current_id = contract.generated_pdf_id
    orphan = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name="orphan.pdf",
        media_type="application/pdf",
        byte_size=10,
        checksum="a" * 64,
        created_at=timezone.now() - timedelta(hours=48),
    )
    orphan.file.save("orphan.pdf", ContentFile(_blank_pdf()), save=False)
    orphan.save()
    deleted = cleanup_orphan_contract_artifacts(older_than_hours=24)
    assert deleted >= 1
    assert ContractArtifact.objects.filter(pk=current_id).exists()


@pytest.mark.django_db
def test_attach_emits_event_after_commit(
    seeded_offices, settings, tmp_path, django_capture_on_commit_callbacks
):
    settings.MEDIA_ROOT = tmp_path
    contract = _issued_contract(seeded_offices)
    rendered = render_contract_pdf(contract)
    with (
        patch("apps.contract.emails.send_signing_invite_email"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        artifact, emitted = attach_generated_pdf(contract, rendered)
    assert emitted is True
    assert artifact.pk
    assert DomainEvent.objects.filter(name="contract.pdf_ready").exists()
    assert AuditEvent.objects.filter(action="contract.pdf_generated").exists()
