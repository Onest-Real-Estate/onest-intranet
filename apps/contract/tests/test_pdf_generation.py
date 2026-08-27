"""Contract review-PDF generation via DocuSeal template submissions."""

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
from apps.contract.docuseal_client import DocuSealSubmission, DocuSealSubmitter
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
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tasks import cleanup_orphan_contract_artifacts, generate_contract_pdf
from apps.contract.template_security import checksum_of
from apps.contract.tests.conftest import agent, company_admin


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _fake_submission(submission_id: int = 42) -> DocuSealSubmission:
    return DocuSealSubmission(
        id=submission_id,
        submitters=(
            DocuSealSubmitter(
                id=1,
                email="prefill@onest.local",
                slug="prefill",
                embed_src="http://localhost:3000/s/prefill",
                external_id="prefill",
                role="Prefill",
            ),
            DocuSealSubmitter(
                id=2,
                email="agent@example.com",
                slug="agent-slug",
                embed_src="http://localhost:3000/s/agent-slug",
                external_id="agent",
                role="Agent",
            ),
        ),
    )


def _published_pdf_template(
    *,
    key: str = "ica-pdf",
    fields: tuple[str, ...] = (
        "party.legalFirstName",
        "office.state",
        "contract.publicId",
        "terms.agentSplitPercent",
    ),
) -> ContractTemplateVersion:
    template = ContractTemplate.objects.create(
        stable_key=key,
        name="ICA PDF",
        status=ContractTemplate.Status.ACTIVE,
        company_wide=True,
    )
    version = ContractTemplateVersion(
        template=template,
        version_label="1.0.0",
        status=ContractTemplateVersion.Status.DRAFT,
        source_format="pdf",
        source_media_type="application/pdf",
        docuseal_template_id=1001,
        docuseal_external_id=f"ext-{key}",
        merge_schema=[
            {
                "key": name,
                "type": "text",
                "label": name,
                "source": name,
            }
            for name in fields
        ],
        extracted_placeholder_keys=list(fields),
    )
    data = _blank_pdf()
    version.source_checksum = checksum_of(data)
    version.source_document.save("template.pdf", ContentFile(data), save=False)
    version.preview_checksum = version.source_checksum
    from django.utils import timezone as dj_tz

    version.preview_generated_at = dj_tz.now()
    version.published_at = dj_tz.now()
    version.status = ContractTemplateVersion.Status.PUBLISHED
    version.full_clean()
    version.save()
    template.active_version = version
    template.save(update_fields=["active_version", "updated_at"])
    return version


def _issued_contract(admin, recipient, **kwargs):
    version = kwargs.pop("template_version", None) or _published_pdf_template()
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
        agent_split_percent="70",
        office_split_percent="30",
        **kwargs,
    )
    ready = transition(
        actor=admin,
        contract=contract,
        action="submit_for_review",
        expected_version=contract_version(contract),
    )
    with patch("apps.contract.tasks.generate_contract_pdf.delay"):
        return transition(
            actor=admin,
            contract=ready,
            action="issue",
            expected_version=contract_version(ready),
            confirmed=True,
        )


def _patch_docuseal(submission_id: int = 42):
    pdf = _blank_pdf()
    return (
        patch(
            "apps.contract.pdf_generation.create_submission",
            return_value=_fake_submission(submission_id),
        ),
        patch(
            "apps.contract.pdf_generation.download_submission_documents",
            return_value=pdf,
        ),
    )


@pytest.mark.django_db
def test_build_merge_values_from_frozen_snapshots(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="merge@example.com")
    recipient.first_name = "Ada"
    recipient.last_name = "Lovelace"
    recipient.save(update_fields=["first_name", "last_name"])
    contract = _issued_contract(admin, recipient)
    values = build_merge_values(contract)
    assert values["party.legalFirstName"] == "Ada"
    assert "office.state" in values
    assert values["contract.publicId"] == str(contract.public_id)
    assert values["terms.agentSplitPercent"] == "70.000"


@pytest.mark.django_db
def test_render_uses_docuseal_submission(seeded_offices, settings, tmp_path):
    settings.DOCUSEAL_PREFILL_EMAIL = "prefill@onest.local"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="golden@example.com")
    recipient.first_name = "Grace"
    recipient.save(update_fields=["first_name"])
    contract = _issued_contract(admin, recipient)

    create_patch, download_patch = _patch_docuseal(7)
    with create_patch as create, download_patch:
        rendered = render_contract_pdf(contract)

    assert rendered.page_count >= 1
    assert rendered.checksum
    assert rendered.docuseal_submission_id == 7
    assert rendered.docuseal_agent_submitter_slug == "agent-slug"
    assert rendered.merge_values["party.legalFirstName"] == "Grace"
    create.assert_called_once()

    golden = tmp_path / "golden-contract.pdf"
    golden.write_bytes(rendered.data)
    assert golden.stat().st_size == len(rendered.data)


@pytest.mark.django_db
def test_generate_and_store_is_idempotent(
    seeded_offices, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.DOCUSEAL_PREFILL_EMAIL = "prefill@onest.local"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="idem@example.com")
    contract = _issued_contract(admin, recipient)

    create_patch, download_patch = _patch_docuseal(11)
    with (
        create_patch,
        download_patch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        first = generate_and_store(contract.pk)
    assert first == "ready"
    contract.refresh_from_db()
    artifact_id = contract.generated_pdf_id
    assert artifact_id is not None
    assert contract.docuseal_submission_id == 11
    events = DomainEvent.objects.filter(name="contract.pdf_ready").count()
    audits = AuditEvent.objects.filter(action="contract.pdf_generated").count()
    assert events == 1
    assert audits == 1

    with django_capture_on_commit_callbacks(execute=True):
        second = generate_and_store(contract.pk)
    assert second in {"ready", "ready_idempotent"}
    contract.refresh_from_db()
    assert contract.generated_pdf_id == artifact_id
    assert (
        ContractArtifact.objects.filter(
            contract=contract, kind=ContractArtifact.Kind.GENERATED_PDF
        ).count()
        == 1
    )
    assert DomainEvent.objects.filter(name="contract.pdf_ready").count() == events
    assert AuditEvent.objects.filter(action="contract.pdf_generated").count() == audits


@pytest.mark.django_db
def test_task_duplicate_delivery_idempotent(
    seeded_offices, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.DOCUSEAL_PREFILL_EMAIL = "prefill@onest.local"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="task@example.com")
    contract = _issued_contract(admin, recipient)

    create_patch, download_patch = _patch_docuseal(12)
    with create_patch, download_patch:
        with django_capture_on_commit_callbacks(execute=True):
            assert generate_contract_pdf(contract.pk) == "ready"
        with django_capture_on_commit_callbacks(execute=True):
            assert generate_contract_pdf(contract.pk) == "ready_idempotent"
    assert AuditEvent.objects.filter(action="contract.pdf_generated").count() == 1
    assert DomainEvent.objects.filter(name="contract.pdf_ready").count() == 1


@pytest.mark.django_db
def test_failed_render_marks_generation_error(seeded_offices, settings):
    settings.DOCUSEAL_PREFILL_EMAIL = "prefill@onest.local"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="fail@example.com")
    contract = _issued_contract(admin, recipient)

    from apps.contract.docuseal_client import DocuSealError
    from apps.contract.pdf_generation import PdfGenerationError, mark_generation_failed

    with patch(
        "apps.contract.pdf_generation.create_submission",
        side_effect=DocuSealError("boom"),
    ):
        with pytest.raises(PdfGenerationError) as exc:
            render_contract_pdf(contract)
        assert exc.value.code == "docuseal_render_failed"
        assert exc.value.retryable is True
        mark_generation_failed(contract.pk, code=exc.value.code)

    contract.refresh_from_db()
    assert contract.status == ContractStatus.GENERATION_ERROR
    assert contract.generated_pdf_id is None
    assert not DomainEvent.objects.filter(name="contract.pdf_ready").exists()


@pytest.mark.django_db
def test_nonretryable_failure_marks_error_without_raise(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="noretry@example.com")
    contract = _issued_contract(admin, recipient)

    with patch(
        "apps.contract.pdf_generation.render_contract_pdf",
        side_effect=__import__(
            "apps.contract.pdf_generation", fromlist=["PdfGenerationError"]
        ).PdfGenerationError("missing_snapshots", retryable=False),
    ):
        result = generate_and_store(contract.pk)

    assert result == "failed:missing_snapshots"
    contract.refresh_from_db()
    assert contract.status == ContractStatus.GENERATION_ERROR


@pytest.mark.django_db
def test_artifact_download_authorized(seeded_offices, client, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.DOCUSEAL_PREFILL_EMAIL = "prefill@onest.local"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="dl@example.com")
    outsider = agent(seeded_offices, email="outsider@example.com", slug="harrisburg")
    contract = _issued_contract(admin, recipient)
    create_patch, download_patch = _patch_docuseal(13)
    with create_patch, download_patch:
        assert generate_and_store(contract.pk) == "ready"
    contract.refresh_from_db()
    url = reverse(
        "agent_contract_artifact_download",
        kwargs={
            "public_id": contract.public_id,
            "artifact_public_id": contract.generated_pdf.public_id,
        },
    )

    client.force_login(admin)
    ok = client.get(url)
    assert ok.status_code == 200
    assert ok["Content-Type"] == "application/pdf"
    assert ok["Cache-Control"].startswith("private")

    client.force_login(recipient)
    own = client.get(url)
    assert own.status_code == 200

    client.force_login(outsider)
    denied = client.get(url)
    assert denied.status_code == 404

    client.force_login(admin)
    missing = client.get(
        reverse(
            "agent_contract_artifact_download",
            kwargs={
                "public_id": contract.public_id,
                "artifact_public_id": "00000000-0000-0000-0000-000000000000",
            },
        )
    )
    assert missing.status_code == 404


@pytest.mark.django_db
def test_orphan_cleanup_preserves_current(seeded_offices, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.DOCUSEAL_PREFILL_EMAIL = "prefill@onest.local"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="orphan@example.com")
    contract = _issued_contract(admin, recipient)
    create_patch, download_patch = _patch_docuseal(14)
    with create_patch, download_patch:
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
        renderer_version=RENDERER_VERSION,
    )
    orphan.file.save("orphan.pdf", ContentFile(b"%PDF-orphan"), save=False)
    orphan.created_at = timezone.now() - timedelta(hours=48)
    orphan.save()

    deleted = cleanup_orphan_contract_artifacts(older_than_hours=24)
    assert deleted == 1
    assert not ContractArtifact.objects.filter(pk=orphan.pk).exists()
    assert ContractArtifact.objects.filter(pk=current_id).exists()


@pytest.mark.django_db
def test_attach_emits_event_after_commit(
    seeded_offices, settings, django_capture_on_commit_callbacks
):
    settings.DOCUSEAL_PREFILL_EMAIL = "prefill@onest.local"
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="commit@example.com")
    contract = _issued_contract(admin, recipient)
    create_patch, download_patch = _patch_docuseal(15)
    with create_patch, download_patch:
        rendered = render_contract_pdf(contract)
    with django_capture_on_commit_callbacks(execute=True):
        artifact, emitted = attach_generated_pdf(contract, rendered)
    assert emitted is True
    assert artifact.renderer_version == RENDERER_VERSION
    contract.refresh_from_db()
    assert contract.docuseal_submission_id == 15
    assert DomainEvent.objects.filter(name="contract.pdf_ready").exists()
    assert AuditEvent.objects.filter(action="contract.pdf_generated").exists()
