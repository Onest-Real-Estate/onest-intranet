"""Company countersign ceremony (named officer)."""

from __future__ import annotations

import uuid
from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.pdfgen import canvas

from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import (
    AgentContract,
    ContractArtifact,
    ContractSignature,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.pdf_signing import fill_prefill_fields
from apps.contract.services.signing_service import (
    RequestMeta,
    SigningCeremonyError,
    complete_company_signing,
    start_company_signing,
    start_signing,
)
from apps.contract.signing_disclosure import DISCLOSURE_VERSION
from apps.contract.statuses import ContractStatus
from apps.contract.template_security import checksum_of
from apps.contract.tests.conftest import (
    agent,
    company_admin,
    issue_awaiting_company,
    office,
)

_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _pdf_bytes() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "Agreement")
    c.showPage()
    c.save()
    return buf.getvalue()


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


def _published_template(actor) -> ContractTemplateVersion:
    family = ContractTemplate.objects.create(
        stable_key=f"ica-co-{uuid.uuid4().hex[:8]}",
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
    family.active_version = version
    family.save(update_fields=["active_version", "updated_at"])
    return version


def _awaiting(seeded_offices, recipient, *, signatory=None):
    admin = company_admin(seeded_offices)
    signatory = signatory or admin
    hq = office("onest-head-office")
    version = _published_template(admin)
    with patch("apps.contract.lifecycle._queue_pdf_generation"):
        contract = AgentContract(
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
        from apps.contract.lifecycle import allow_status_write

        with allow_status_write():
            contract.save()
        transition(
            actor=admin,
            contract=contract,
            action="submit_for_review",
            expected_version=contract_version(contract),
        )
        contract.refresh_from_db()
        awaiting = issue_awaiting_company(admin, contract, company_signatory=signatory)
    return awaiting, admin, signatory


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


def _meta(session_key: str = "sess-co") -> RequestMeta:
    return RequestMeta(
        session_key=session_key, ip_address="127.0.0.1", user_agent="test"
    )


@pytest.mark.django_db
def test_non_assignee_cannot_start_company_ceremony(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    recipient = agent(seeded_offices, email="agent-co@example.com")
    other = agent(seeded_offices, email="other-officer@example.com")
    awaiting, _admin, _signatory = _awaiting(seeded_offices, recipient)
    _attach_generated(awaiting)
    with pytest.raises(PermissionDenied):
        start_company_signing(
            other,
            contract_public_id=awaiting.public_id,
            expected_version=contract_version(awaiting),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )
    with pytest.raises(PermissionDenied):
        start_company_signing(
            recipient,
            contract_public_id=awaiting.public_id,
            expected_version=contract_version(awaiting),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )


@pytest.mark.django_db
def test_assignee_company_complete_releases_agent(seeded_offices, settings):
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True
    recipient = agent(seeded_offices, email="agent-released@example.com")
    awaiting, _admin, signatory = _awaiting(seeded_offices, recipient)
    _attach_generated(awaiting)

    with pytest.raises((SigningCeremonyError, PermissionDenied)):
        start_signing(
            recipient,
            contract_public_id=awaiting.public_id,
            expected_version=contract_version(awaiting),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta("agent-early"),
        )

    payload = start_company_signing(
        signatory,
        contract_public_id=awaiting.public_id,
        expected_version=contract_version(awaiting),
        consent_accepted=True,
        disclosure_version=DISCLOSURE_VERSION,
        request_meta=_meta(),
    )
    assert payload["ceremony"]["intentPublicId"]

    with (
        patch("apps.contract.lifecycle._queue_agent_release_invite"),
        patch("apps.contract.lifecycle._queue_agent_status_email"),
    ):
        result = complete_company_signing(
            signatory,
            intent_public_id=uuid.UUID(payload["ceremony"]["intentPublicId"]),
            signature_data_url=_PNG_DATA_URL,
            signed_date="2026-09-10",
            request_meta=_meta(),
        )
    assert result["ok"] is True
    awaiting.refresh_from_db()
    assert awaiting.status == ContractStatus.SENT
    assert awaiting.company_signed_at is not None
    assert ContractSignature.objects.filter(
        contract=awaiting,
        signer_role=ContractSignature.SignerRole.COMPANY,
    ).exists()

    agent_payload = start_signing(
        recipient,
        contract_public_id=awaiting.public_id,
        expected_version=contract_version(awaiting),
        consent_accepted=True,
        disclosure_version=DISCLOSURE_VERSION,
        request_meta=_meta("agent-ok"),
    )
    assert agent_payload["ceremony"]["intentPublicId"]
