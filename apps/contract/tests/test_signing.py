"""Hub-native signing ceremony tests."""

from __future__ import annotations

import io
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from apps.contract.lifecycle import TransitionRefused, contract_version, transition
from apps.contract.models import (
    AgentContract,
    ContractArtifact,
    ContractSignature,
    ContractSigningIntent,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.pdf_signing import fill_prefill_fields
from apps.contract.services.signing_service import (
    RequestMeta,
    SigningCeremonyError,
    complete_signing,
    start_signing,
)
from apps.contract.signing_disclosure import DISCLOSURE_VERSION
from apps.contract.statuses import ContractStatus
from apps.contract.template_security import checksum_of
from apps.contract.tests.conftest import agent, company_admin, office


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
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
        stable_key="ica-hub-sign",
        name="ICA Hub",
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
        transition(
            actor=admin,
            contract=contract,
            action="issue",
            expected_version=contract_version(contract),
            confirmed=True,
        )
        contract.refresh_from_db()
    return contract


def _attach_generated(contract: AgentContract) -> ContractArtifact:
    version = contract.template_version
    assert version is not None
    layout = list(version.field_layout or [])
    filled = fill_prefill_fields(
        _pdf_bytes(),
        layout=layout,
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


@pytest.mark.django_db
def test_signing_ready_in_debug_without_cert(settings, seeded_offices):
    del seeded_offices
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    from apps.contract.pdf_signing import signing_is_ready

    assert signing_is_ready() is True


@pytest.mark.django_db
def test_admin_cannot_start_signing_for_agent(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="agent-admin-block@example.com")
    contract = _issued(seeded_offices, recipient, admin=admin)
    _attach_generated(contract)
    with pytest.raises(PermissionDenied):
        start_signing(
            admin,
            contract_public_id=contract.public_id,
            expected_version=contract_version(contract),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )


@pytest.mark.django_db
def test_start_and_complete_signing(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    recipient = agent(seeded_offices, email="agent-complete@example.com")
    contract = _issued(seeded_offices, recipient)
    _attach_generated(contract)

    payload = start_signing(
        recipient,
        contract_public_id=contract.public_id,
        expected_version=contract_version(contract),
        consent_accepted=True,
        disclosure_version=DISCLOSURE_VERSION,
        request_meta=_meta("sess-complete"),
    )
    assert payload["ceremony"]["intentPublicId"]
    assert payload["ceremony"]["reviewPdfUrl"]
    assert any(f["type"] == "signature" for f in payload["ceremony"]["agentFields"])

    result = complete_signing(
        recipient,
        intent_public_id=uuid.UUID(payload["ceremony"]["intentPublicId"]),
        signature_data_url=_PNG_DATA_URL,
        signed_date="2026-08-29",
        request_meta=_meta("sess-complete"),
    )
    assert result["ok"] is True
    contract.refresh_from_db()
    assert contract.status == ContractStatus.SIGNED
    sig = ContractSignature.objects.get(contract=contract)
    assert sig.signature_method == ContractSignature.Method.HUB_EMBEDDED
    assert sig.certificate_of_completion is not None


@pytest.mark.django_db
def test_complete_rejects_checksum_drift(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    recipient = agent(seeded_offices, email="agent-drift@example.com")
    contract = _issued(seeded_offices, recipient)
    artifact = _attach_generated(contract)
    payload = start_signing(
        recipient,
        contract_public_id=contract.public_id,
        expected_version=contract_version(contract),
        consent_accepted=True,
        disclosure_version=DISCLOSURE_VERSION,
        request_meta=_meta("sess-drift"),
    )
    artifact.checksum = "0" * 64
    ContractArtifact.objects.filter(pk=artifact.pk).update(checksum="0" * 64)
    with pytest.raises(TransitionRefused):
        complete_signing(
            recipient,
            intent_public_id=uuid.UUID(payload["ceremony"]["intentPublicId"]),
            signature_data_url=_PNG_DATA_URL,
            signed_date="2026-08-29",
            request_meta=_meta("sess-drift"),
        )


@pytest.mark.django_db
def test_expired_intent_blocks_completion(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    recipient = agent(seeded_offices, email="agent-exp@example.com")
    contract = _issued(seeded_offices, recipient)
    _attach_generated(contract)
    payload = start_signing(
        recipient,
        contract_public_id=contract.public_id,
        expected_version=contract_version(contract),
        consent_accepted=True,
        disclosure_version=DISCLOSURE_VERSION,
        request_meta=_meta("sess-exp"),
    )
    intent = ContractSigningIntent.objects.get(
        public_id=payload["ceremony"]["intentPublicId"]
    )
    intent.expires_at = timezone.now() - timedelta(seconds=5)
    intent.save(update_fields=["expires_at"])
    with pytest.raises(TransitionRefused):
        complete_signing(
            recipient,
            intent_public_id=uuid.UUID(str(intent.public_id)),
            signature_data_url=_PNG_DATA_URL,
            signed_date="2026-08-29",
            request_meta=_meta("sess-exp"),
        )


@pytest.mark.django_db
def test_start_signing_rejects_missing_consent(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    recipient = agent(seeded_offices, email="agent-consent@example.com")
    contract = _issued(seeded_offices, recipient)
    _attach_generated(contract)
    with pytest.raises(SigningCeremonyError):
        start_signing(
            recipient,
            contract_public_id=contract.public_id,
            expected_version=contract_version(contract),
            consent_accepted=False,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )


@pytest.mark.django_db
def test_ceremony_http_recipient_only(client, seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="agent-http@example.com")
    contract = _issued(seeded_offices, recipient, admin=admin)
    _attach_generated(contract)

    client.force_login(admin)
    response = client.post(
        reverse("my_contract_sign"),
        data={
            "consentAccepted": "true",
            "disclosureVersion": DISCLOSURE_VERSION,
            "expectedVersion": contract_version(contract),
            "contractPublicId": str(contract.public_id),
        },
    )
    assert response.status_code in {403, 302, 422}

    client.force_login(recipient)
    client.post(
        reverse("my_contract_sign"),
        data={
            "consentAccepted": "true",
            "disclosureVersion": DISCLOSURE_VERSION,
            "expectedVersion": contract_version(contract),
            "contractPublicId": str(contract.public_id),
        },
        content_type="application/json",
    )
    assert ContractSigningIntent.objects.filter(
        contract=contract, actor=recipient
    ).exists()
