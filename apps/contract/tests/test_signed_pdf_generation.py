"""Immutable final signed-PDF generation (P1-043)."""

from __future__ import annotations

import io
import uuid
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader, PdfWriter

from apps.audit.models import DomainEvent
from apps.contract.certificate_of_completion import CERTIFICATE_MARKER
from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import (
    AgentContract,
    ContractArtifact,
    ContractSignature,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.pdf_signing import appearance_checksum, fill_prefill_fields
from apps.contract.services.signing_service import (
    RequestMeta,
    complete_signing,
    start_signing,
)
from apps.contract.signed_pdf_generation import (
    RENDERER_VERSION,
    attach_final_signed_pdf,
    generate_and_store_signed_pdf,
    integrity_payload,
    render_final_signed_pdf,
)
from apps.contract.signing_disclosure import DISCLOSURE_VERSION
from apps.contract.statuses import ContractStatus
from apps.contract.template_security import checksum_of
from apps.contract.tests.conftest import (
    agent,
    company_admin,
    issue_awaiting_company,
    office,
    release_to_agent,
)


def _pdf_bytes(*, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _hub_layout() -> list[dict]:
    return [
        {
            "id": "f1",
            "name": "PrefillLegalFirstName",
            "type": "text",
            "role": "Prefill",
            "page": 1,
            "x": 72,
            "y": 100,
            "w": 120,
            "h": 18,
        },
        {
            "id": "fc1",
            "name": "CompanySignature",
            "type": "signature",
            "role": "Company",
            "page": 1,
            "x": 72,
            "y": 500,
            "w": 200,
            "h": 48,
        },
        {
            "id": "fc2",
            "name": "CompanyDate",
            "type": "date",
            "role": "Company",
            "page": 1,
            "x": 300,
            "y": 500,
            "w": 100,
            "h": 24,
        },
        {
            "id": "f2",
            "name": "AgentSignature",
            "type": "signature",
            "role": "Agent",
            "page": 1,
            "x": 72,
            "y": 600,
            "w": 200,
            "h": 48,
        },
        {
            "id": "f3",
            "name": "AgentDate",
            "type": "date",
            "role": "Agent",
            "page": 1,
            "x": 300,
            "y": 600,
            "w": 100,
            "h": 24,
        },
    ]


def _published_template(actor, hq) -> ContractTemplateVersion:
    family = ContractTemplate.objects.create(
        stable_key=f"ica-signed-{uuid.uuid4().hex[:8]}",
        name="ICA Signed Final",
        status=ContractTemplate.Status.ACTIVE,
        company_wide=True,
        created_by=actor,
    )
    version = ContractTemplateVersion.objects.create(
        template=family,
        version_label="v1",
        status=ContractTemplateVersion.Status.PUBLISHED,
        source_format="pdf",
        source_media_type="application/pdf",
        source_checksum="abc",
        field_layout=_hub_layout(),
        extracted_placeholder_keys=["PrefillLegalFirstName"],
        merge_schema=[
            {
                "key": "PrefillLegalFirstName",
                "label": "Legal first name",
                "type": "text",
                "source": "party.legalFirstName",
            }
        ],
        created_by=actor,
        published_at=timezone.now(),
        approved_by=actor,
    )
    pdf = _pdf_bytes()
    version.source_document.save("blank.pdf", ContentFile(pdf), save=True)
    version.preview_pdf.save("preview.pdf", ContentFile(pdf), save=True)
    version.preview_checksum = checksum_of(pdf)
    version.source_checksum = checksum_of(pdf)
    version.save()
    family.active_version = version
    family.save(update_fields=["active_version"])
    return version


def _issued(seeded_offices, recipient, *, admin=None) -> AgentContract:
    hq = office("onest-head-office")
    admin = admin or company_admin(seeded_offices)
    version = _published_template(admin, hq)
    with patch("apps.contract.tasks.generate_contract_pdf.delay"):
        contract = AgentContract.objects.create(
            recipient=recipient,
            office=hq,
            template_version=version,
            effective_on=timezone.now().date(),
            status=ContractStatus.DRAFT,
            party_snapshot={
                "legalFirstName": "Ada",
                "legalLastName": "Lovelace",
                "email": recipient.email,
                "displayName": "Ada Lovelace",
            },
            office_snapshot={"name": hq.name, "state": "VA"},
            terms_snapshot={"agentSplitPercent": "70", "officeSplitPercent": "30"},
            calculation_rule_version="1.0.0",
            created_by=admin,
        )
        transition(
            actor=admin,
            contract=contract,
            action="submit_for_review",
            expected_version=contract_version(contract),
        )
        contract.refresh_from_db()
        awaiting = issue_awaiting_company(admin, contract, company_signatory=admin)
    _attach_generated(awaiting)
    awaiting.refresh_from_db()
    sent = release_to_agent(admin, awaiting, attach_pdf=False)
    assert sent.status == ContractStatus.SENT
    return sent


def _attach_generated(contract: AgentContract) -> ContractArtifact:
    version = contract.template_version
    assert version is not None
    filled = fill_prefill_fields(
        _pdf_bytes(),
        layout=list(version.field_layout or []),
        values={"PrefillLegalFirstName": "Ada"},
    )
    artifact = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name="review.pdf",
        media_type="application/pdf",
        byte_size=len(filled),
        checksum=checksum_of(filled),
        renderer_version="hub-pdf-1.0.0",
        input_fingerprint="fp",
    )
    artifact.file.save("review.pdf", ContentFile(filled), save=False)
    artifact.save()
    contract.generated_pdf = artifact
    contract.save(update_fields=["generated_pdf", "updated_at"])
    return artifact


def _meta(session_key: str = "sess-1") -> RequestMeta:
    return RequestMeta(
        session_key=session_key, ip_address="127.0.0.1", user_agent="test"
    )


def _sign(recipient, contract, *, session: str = "sess") -> ContractSignature:
    with patch("apps.contract.services.signing_service._queue_signed_pdf_generation"):
        payload = start_signing(
            recipient,
            contract_public_id=contract.public_id,
            expected_version=contract_version(contract),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(session),
        )
        complete_signing(
            recipient,
            intent_public_id=uuid.UUID(payload["ceremony"]["intentPublicId"]),
            signature_data_url=_PNG_DATA_URL,
            signed_date="2026-08-30",
            request_meta=_meta(session),
        )
    return ContractSignature.objects.get(
        contract=contract, signer_role=ContractSignature.SignerRole.AGENT
    )


@pytest.mark.django_db(transaction=True)
def test_final_pdf_binds_source_checksum_and_certificate(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    recipient = agent(seeded_offices, email="agent-final@example.com")
    contract = _issued(seeded_offices, recipient)
    review = contract.generated_pdf
    assert review is not None
    signature = _sign(recipient, contract, session="sess-final")

    assert signature.source_checksum == review.checksum.lower()
    assert signature.finalization_status == ContractSignature.FinalizationStatus.PENDING
    assert signature.artifact_id is None

    outcome = generate_and_store_signed_pdf(signature.pk, task_id="task-1")
    assert outcome == "ready"
    signature.refresh_from_db()
    contract.refresh_from_db()

    assert signature.finalization_status == ContractSignature.FinalizationStatus.READY
    assert signature.artifact_id == contract.signed_pdf_id
    assert signature.generation_task_id == "task-1"
    artifact = signature.artifact
    assert artifact is not None
    assert artifact.kind == ContractArtifact.Kind.SIGNED_PDF
    assert artifact.renderer_version == RENDERER_VERSION
    assert artifact.input_fingerprint == review.checksum.lower()
    assert artifact.generation_metadata["sourceChecksum"] == review.checksum.lower()
    assert artifact.generation_metadata["signaturePublicId"] == str(signature.public_id)

    pdf_bytes = artifact.file.read()
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 2
    cert_text = reader.pages[-1].extract_text() or ""
    assert "Certificate of Completion" in cert_text
    assert CERTIFICATE_MARKER in cert_text
    assert str(contract.public_id) in cert_text
    assert str(signature.public_id) in cert_text
    assert DISCLOSURE_VERSION in cert_text

    assert DomainEvent.objects.filter(name="contract.signed_pdf_ready").count() == 1


@pytest.mark.django_db
def test_final_pdf_idempotent_no_overwrite(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    recipient = agent(seeded_offices, email="agent-idem@example.com")
    contract = _issued(seeded_offices, recipient)
    signature = _sign(recipient, contract, session="sess-idem")

    assert generate_and_store_signed_pdf(signature.pk, task_id="t1") == "ready"
    first = ContractSignature.objects.get(pk=signature.pk).artifact
    assert first is not None
    first_checksum = first.checksum
    event_count = DomainEvent.objects.filter(name="contract.signed_pdf_ready").count()

    assert (
        generate_and_store_signed_pdf(signature.pk, task_id="t2") == "ready_idempotent"
    )
    signature.refresh_from_db()
    assert signature.artifact_id == first.pk
    assert signature.artifact is not None
    assert signature.artifact.checksum == first_checksum
    assert (
        DomainEvent.objects.filter(name="contract.signed_pdf_ready").count()
        == event_count
    )

    rendered = render_final_signed_pdf(signature)
    artifact, created = attach_final_signed_pdf(signature, rendered, task_id="t3")
    assert created is False
    assert artifact.pk == first.pk


@pytest.mark.django_db
def test_source_checksum_mismatch_keeps_signature(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    recipient = agent(seeded_offices, email="agent-mismatch@example.com")
    contract = _issued(seeded_offices, recipient)
    review = contract.generated_pdf
    assert review is not None
    signature = _sign(recipient, contract, session="sess-mismatch")

    ContractArtifact.objects.filter(pk=review.pk).update(checksum="0" * 64)
    # Bypass model immutability to simulate storage/byte drift after signing.
    storage = review.file.storage
    name = review.file.name
    storage.save(name, ContentFile(_pdf_bytes(pages=2)))

    outcome = generate_and_store_signed_pdf(signature.pk, task_id="fail-1")
    assert outcome.startswith("failed:")
    signature.refresh_from_db()
    contract.refresh_from_db()
    assert signature.finalization_status == ContractSignature.FinalizationStatus.FAILED
    assert contract.status == ContractStatus.SIGNED
    assert contract.signed_pdf_id is None


@pytest.mark.django_db
def test_artifact_immutable_and_admin_cannot_delete(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    recipient = agent(seeded_offices, email="agent-immut@example.com")
    contract = _issued(seeded_offices, recipient)
    signature = _sign(recipient, contract, session="sess-immut")
    generate_and_store_signed_pdf(signature.pk)
    signature.refresh_from_db()
    artifact = signature.artifact
    assert artifact is not None
    artifact.checksum = "1" * 64
    with pytest.raises(ValidationError):
        artifact.save()

    from django.contrib.admin.sites import AdminSite

    from apps.contract.admin import ContractArtifactAdmin, ContractSignatureAdmin

    site = AdminSite()
    assert (
        ContractArtifactAdmin(ContractArtifact, site).has_delete_permission(
            None, artifact
        )
        is False
    )
    assert (
        ContractSignatureAdmin(ContractSignature, site).has_delete_permission(
            None, signature
        )
        is False
    )


@pytest.mark.django_db
def test_verify_endpoints_authorization(client, seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="agent-verify@example.com")
    other = agent(seeded_offices, email="agent-other@example.com", slug="fairfax-va")
    contract = _issued(seeded_offices, recipient, admin=admin)
    signature = _sign(recipient, contract, session="sess-verify")
    generate_and_store_signed_pdf(signature.pk)
    signature.refresh_from_db()

    url_ops = reverse(
        "agent_contract_signed_pdf_verify",
        kwargs={"public_id": contract.public_id},
    )
    url_me = reverse(
        "my_contract_signed_pdf_verify",
        kwargs={"public_id": contract.public_id},
    )

    client.force_login(other)
    assert client.get(url_me).status_code == 404
    assert client.get(url_ops).status_code in {403, 404}

    client.force_login(recipient)
    mine = client.get(url_me)
    assert mine.status_code == 200
    body = mine.json()
    assert body["sourceChecksum"] == signature.source_checksum
    assert body["outputChecksum"]
    assert body["signaturePublicId"] == str(signature.public_id)
    assert body["rendererVersion"] == RENDERER_VERSION

    client.force_login(admin)
    ops = client.get(url_ops)
    assert ops.status_code == 200
    expected = integrity_payload(contract)
    assert expected is not None
    assert ops.json()["documentIdentifier"] == expected["documentIdentifier"]


@pytest.mark.django_db
def test_failed_finalization_can_regen_after_source_restored(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    recipient = agent(seeded_offices, email="agent-regen@example.com")
    contract = _issued(seeded_offices, recipient)
    review = contract.generated_pdf
    assert review is not None
    signature = _sign(recipient, contract, session="sess-regen")
    source_checksum = signature.source_checksum

    # Break appearance checksum → terminal failure, signature retained.
    ContractSignature.objects.filter(pk=signature.pk).update(
        appearance_checksum="a" * 64
    )
    assert generate_and_store_signed_pdf(signature.pk, task_id="fail").startswith(
        "failed:"
    )
    signature.refresh_from_db()
    assert signature.finalization_status == ContractSignature.FinalizationStatus.FAILED
    contract.refresh_from_db()
    assert contract.status == ContractStatus.SIGNED

    signature.appearance_file.open("rb")
    appearance = signature.appearance_file.read()
    signature.appearance_file.close()
    ContractSignature.objects.filter(pk=signature.pk).update(
        appearance_checksum=appearance_checksum(appearance),
        finalization_status=ContractSignature.FinalizationStatus.PENDING,
        finalization_error="",
    )

    outcome = generate_and_store_signed_pdf(signature.pk, task_id="regen-1")
    assert outcome == "ready"
    signature.refresh_from_db()
    assert signature.source_checksum == source_checksum
    assert signature.artifact is not None
    assert signature.artifact.input_fingerprint == review.checksum.lower()
