"""Recipient DocuSeal signing ceremony (P1-042)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from apps.audit.models import AuditEvent
from apps.contract.docuseal_client import (
    DocuSealSubmission,
    DocuSealSubmitter,
)
from apps.contract.lifecycle import (
    StaleContractVersion,
    TransitionRefused,
    contract_version,
    transition,
)
from apps.contract.models import (
    ContractArtifact,
    ContractSignature,
    ContractSigningIntent,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.services import create_draft_contract
from apps.contract.services.signing_service import (
    RequestMeta,
    SigningCeremonyError,
    complete_signing_from_docuseal,
    start_signing,
)
from apps.contract.signing_disclosure import DISCLOSURE_VERSION
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, company_admin
from apps.web.tests.test_permissions import inertia_page_script


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _published_template(*, key="ica-sign") -> ContractTemplateVersion:
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


def _issued(admin, recipient, **kwargs):
    version = kwargs.pop("template_version", None) or _published_template()
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
        agent_split_percent="70",
        office_split_percent="30",
        mentor_percent="5",
        mentor_basis="gross_commission",
        mentor_payee=admin,
        **kwargs,
    )
    contract = transition(
        actor=admin,
        contract=contract,
        action="submit_for_review",
        expected_version=contract_version(contract),
    )
    return transition(
        actor=admin,
        contract=contract,
        action="issue",
        expected_version=contract_version(contract),
        confirmed=True,
    )


def _attach_generated(
    contract,
    data: bytes | None = None,
    *,
    submission_id: int = 99,
) -> ContractArtifact:
    payload = data or _pdf_bytes()
    checksum = hashlib.sha256(payload).hexdigest()
    artifact = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name="agreement.pdf",
        media_type="application/pdf",
        byte_size=len(payload),
        checksum=checksum,
    )
    artifact.full_clean(exclude=["file"])
    artifact.file.save("agreement.pdf", ContentFile(payload), save=False)
    artifact.full_clean()
    artifact.save()
    contract.generated_pdf = artifact
    contract.docuseal_submission_id = submission_id
    contract.docuseal_agent_submitter_slug = "slug-abc"
    contract.save(
        update_fields=[
            "generated_pdf",
            "docuseal_submission_id",
            "docuseal_agent_submitter_slug",
            "updated_at",
        ]
    )
    return artifact


def _meta() -> RequestMeta:
    return RequestMeta(
        session_key="session-abc",
        ip_address="203.0.113.10",
        user_agent="pytest-agent",
    )


def _fake_submission(submission_id: int = 99) -> DocuSealSubmission:
    return DocuSealSubmission(
        id=submission_id,
        submitters=(
            DocuSealSubmitter(
                id=1,
                email="prefill@example.com",
                slug="prefill-slug",
                embed_src="http://localhost:3000/s/prefill-slug",
                external_id="prefill",
                role="Prefill",
            ),
            DocuSealSubmitter(
                id=2,
                email="a@example.com",
                slug="slug-abc",
                embed_src="http://localhost:3000/s/slug-abc",
                external_id="intent",
                role="Agent",
            ),
        ),
    )


@pytest.mark.django_db
def test_signing_ready_requires_docuseal_config(client, settings, seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-ready@example.com")
    contract = _issued(admin, recipient)
    _attach_generated(contract)
    client.force_login(recipient)

    settings.DOCUSEAL_API_KEY = ""
    response = client.get(reverse("my_contract"))
    assert response.status_code == 200
    props = inertia_page_script(response)["props"]
    assert props["capabilities"]["canSign"] is True
    assert props["capabilities"]["signingReady"] is False

    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"
    response = client.get(reverse("my_contract"))
    props = inertia_page_script(response)["props"]
    assert props["capabilities"]["signingReady"] is True


@pytest.mark.django_db
def test_admin_cannot_start_signing_for_agent(settings, seeded_offices):
    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-admin@example.com")
    contract = _issued(admin, recipient)
    _attach_generated(contract, submission_id=99)

    with (
        patch(
            "apps.contract.services.signing_service.get_submission",
            return_value=_fake_submission(),
        ),
        pytest.raises(PermissionDenied),
    ):
        start_signing(
            admin,
            contract_public_id=contract.public_id,
            expected_version=contract_version(contract),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )


@pytest.mark.django_db
def test_start_signing_creates_intent_and_embed(settings, seeded_offices):
    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-start@example.com")
    contract = _issued(admin, recipient)
    _attach_generated(contract, submission_id=101)

    with (
        patch(
            "apps.contract.services.signing_service.get_submission",
            return_value=_fake_submission(101),
        ) as create,
        patch(
            "apps.contract.services.signing_service.docuseal_embeds_available",
            return_value=True,
        ),
    ):
        payload = start_signing(
            recipient,
            contract_public_id=contract.public_id,
            expected_version=contract_version(contract),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )

    assert payload["ceremony"]["embedSrc"].endswith("/s/slug-abc")
    assert payload["ceremony"]["embedsAvailable"] is True
    assert payload["ceremony"]["docusealProtocol"] == "http"
    intent = ContractSigningIntent.objects.get(docuseal_submission_id=101)
    assert intent.actor_id == recipient.pk
    assert intent.disclosure_version == DISCLOSURE_VERSION
    assert intent.request_ip_hash
    assert intent.status == ContractSigningIntent.Status.PENDING
    create.assert_called_once()
    assert AuditEvent.objects.filter(action="contract.signing_intent.created").exists()


@pytest.mark.django_db
def test_start_signing_rejects_stale_version_and_missing_consent(
    settings, seeded_offices
):
    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-stale@example.com")
    contract = _issued(admin, recipient)
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

    with pytest.raises(StaleContractVersion):
        start_signing(
            recipient,
            contract_public_id=contract.public_id,
            expected_version="not-the-version",
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )


@pytest.mark.django_db
def test_complete_signing_is_idempotent(settings, seeded_offices):
    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-done@example.com")
    contract = _issued(admin, recipient)
    artifact = _attach_generated(contract, submission_id=202)

    with patch(
        "apps.contract.services.signing_service.get_submission",
        return_value=_fake_submission(202),
    ):
        start_signing(
            recipient,
            contract_public_id=contract.public_id,
            expected_version=contract_version(contract),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )

    signed_pdf = b"%PDF-1.4 signed"
    with patch(
        "apps.contract.services.signing_service.download_submission_documents",
        return_value=signed_pdf,
    ):
        first = complete_signing_from_docuseal(submission_id=202)
        second = complete_signing_from_docuseal(submission_id=202)

    assert first["ok"] is True
    assert second.get("idempotent") is True
    contract.refresh_from_db()
    assert contract.status == ContractStatus.SIGNED
    assert ContractSignature.objects.filter(contract=contract).count() == 1
    assert contract.signed_pdf_id is not None
    assert contract.signed_pdf.checksum == hashlib.sha256(signed_pdf).hexdigest()
    assert artifact.pk == contract.generated_pdf_id
    assert AuditEvent.objects.filter(action="contract.signature.created").count() == 1


@pytest.mark.django_db
def test_complete_rejects_checksum_drift(settings, seeded_offices):
    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-drift@example.com")
    contract = _issued(admin, recipient)
    _attach_generated(contract, submission_id=303)

    with patch(
        "apps.contract.services.signing_service.get_submission",
        return_value=_fake_submission(303),
    ):
        start_signing(
            recipient,
            contract_public_id=contract.public_id,
            expected_version=contract_version(contract),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )

    intent = ContractSigningIntent.objects.get(docuseal_submission_id=303)
    intent.artifact_checksum = "b" * 64
    intent.save(update_fields=["artifact_checksum"])

    with (
        patch(
            "apps.contract.services.signing_service.download_submission_documents",
            return_value=b"%PDF-1.4",
        ),
        pytest.raises(TransitionRefused),
    ):
        complete_signing_from_docuseal(submission_id=303)


@pytest.mark.django_db
def test_expired_intent_blocks_completion(settings, seeded_offices):
    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-exp@example.com")
    contract = _issued(admin, recipient)
    _attach_generated(contract, submission_id=404)

    with patch(
        "apps.contract.services.signing_service.get_submission",
        return_value=_fake_submission(404),
    ):
        start_signing(
            recipient,
            contract_public_id=contract.public_id,
            expected_version=contract_version(contract),
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )

    intent = ContractSigningIntent.objects.get(docuseal_submission_id=404)
    intent.expires_at = timezone.now() - timedelta(minutes=1)
    intent.save(update_fields=["expires_at"])

    with pytest.raises(TransitionRefused):
        complete_signing_from_docuseal(submission_id=404)


@pytest.mark.django_db
def test_ceremony_http_recipient_only_and_csrf(client, settings, seeded_offices):
    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-http@example.com")
    contract = _issued(admin, recipient)
    _attach_generated(contract, submission_id=505)

    # Admin authenticated — still cannot sign agent's contract via ceremony.
    client.force_login(admin)
    response = client.post(
        reverse("my_contract_sign"),
        {
            "consentAccepted": "true",
            "disclosureVersion": DISCLOSURE_VERSION,
            "expectedVersion": contract_version(contract),
            "contractPublicId": str(contract.public_id),
        },
    )
    assert response.status_code in {403, 404, 302}

    client.force_login(recipient)
    with patch(
        "apps.contract.services.signing_service.get_submission",
        return_value=_fake_submission(505),
    ):
        response = client.post(
            reverse("my_contract_sign"),
            {
                "consentAccepted": "true",
                "disclosureVersion": DISCLOSURE_VERSION,
                "expectedVersion": contract_version(contract),
                "contractPublicId": str(contract.public_id),
            },
        )
    assert response.status_code == 200
    assert ContractSigningIntent.objects.filter(docuseal_submission_id=505).exists()


@pytest.mark.django_db
def test_webhook_rejects_bad_signature_and_accepts_valid(client, settings):
    settings.DOCUSEAL_WEBHOOK_SECRET = "whsec_test"
    settings.DOCUSEAL_API_KEY = "test-key"
    settings.DOCUSEAL_BASE_URL = "http://localhost:3000"

    body = json.dumps(
        {"event_type": "form.completed", "data": {"submission_id": 999}}
    ).encode()
    bad = client.post(
        reverse("docuseal_contract_webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_DOCUSEAL_SIGNATURE="deadbeef",
    )
    assert bad.status_code == 403

    # Self-hosted: shared token in the URL (no HMAC UI).
    missing_token = client.post(
        reverse("docuseal_contract_webhook"),
        data=body,
        content_type="application/json",
    )
    assert missing_token.status_code == 403

    with patch(
        "apps.contract.views.signing_views.complete_signing_from_docuseal",
        return_value={"ok": True, "ignored": True},
    ) as complete:
        good = client.post(
            reverse("docuseal_contract_webhook") + "?token=whsec_test",
            data=body,
            content_type="application/json",
        )
    assert good.status_code == 200
    complete.assert_called_once()

    digest = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    with patch(
        "apps.contract.views.signing_views.complete_signing_from_docuseal",
        return_value={"ok": True, "ignored": True},
    ) as complete_hmac:
        hmac_ok = client.post(
            reverse("docuseal_contract_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_DOCUSEAL_SIGNATURE=digest,
        )
    assert hmac_ok.status_code == 200
    complete_hmac.assert_called_once()


def test_verify_webhook_timestamp_format(settings):
    from apps.contract.docuseal_client import authorize_docuseal_webhook

    settings.DOCUSEAL_WEBHOOK_SECRET = "secret"
    raw = b'{"event_type":"form.completed"}'
    ts = str(int(timezone.now().timestamp()))
    signed = f"{ts}.".encode() + raw
    sig = hmac.new(b"secret", signed, hashlib.sha256).hexdigest()
    assert authorize_docuseal_webhook(
        raw_body=raw, signature_header=f"{ts}.{sig}", url_token=""
    )
    assert not authorize_docuseal_webhook(
        raw_body=raw, signature_header=f"{ts}.nope", url_token=""
    )
    assert authorize_docuseal_webhook(
        raw_body=raw, signature_header="", url_token="secret"
    )
    assert not authorize_docuseal_webhook(
        raw_body=raw, signature_header="", url_token="wrong"
    )


@pytest.mark.django_db
def test_recipient_mark_signed_via_lifecycle_still_allowed_for_recipient(
    seeded_offices,
):
    """Lifecycle auth allows recipient mark_signed (ceremony uses this path)."""
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="sign-lc@example.com")
    contract = _issued(admin, recipient)
    _attach_generated(contract)
    contract.refresh_from_db()
    contract = transition(
        actor=recipient,
        contract=contract,
        action="mark_viewed",
        expected_version=contract_version(contract),
    )
    signed = transition(
        actor=recipient,
        contract=contract,
        action="mark_signed",
        expected_version=contract_version(contract),
    )
    assert signed.status == ContractStatus.SIGNED
