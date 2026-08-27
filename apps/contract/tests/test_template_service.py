from __future__ import annotations

import io
from datetime import date
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from pypdf import PdfWriter

from apps.audit.models import AuditEvent
from apps.contract.docuseal_client import DocuSealTemplate, DocuSealTemplateField
from apps.contract.models import AgentContract, ContractTemplateVersion
from apps.contract.services.template_service import (
    activate_version,
    create_draft_version,
    create_template_family,
    publish_version,
    retire_version,
    save_draft_version,
    serialize_template_row,
)
from apps.contract.template_security import inspect_template, validate_merge_schema
from apps.contract.tests.conftest import agent, company_admin


@pytest.mark.django_db
def test_serialize_template_row_points_draft_families_at_draft_workspace(
    seeded_offices,
):
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-draft-open",
        name="Draft open",
        company_wide=True,
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        display_name="Draft open",
    )
    row = serialize_template_row(
        type(template)
        .objects.prefetch_related("versions")
        .select_related("active_version")
        .get(pk=template.pk)
    )
    assert row["activeVersionPk"] is None
    assert row["workspaceVersionPk"] == version.pk


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _pdf_with_unsafe_token() -> bytes:
    return _blank_pdf() + b"\n/OpenAction\n"


def _remote_template(*, template_id: int = 55) -> DocuSealTemplate:
    return DocuSealTemplate(
        id=template_id,
        name="ICA",
        external_id="ext",
        fields=(
            DocuSealTemplateField(
                name="party.legalFirstName",
                field_type="text",
                role="Prefill",
                required=True,
            ),
            DocuSealTemplateField(
                name="AgentSignature",
                field_type="signature",
                role="Agent",
                required=True,
            ),
            DocuSealTemplateField(
                name="AgentSignedOn",
                field_type="date",
                role="Agent",
                required=True,
            ),
        ),
    )


@pytest.mark.django_db
def test_pdf_upload_without_acroform_is_accepted():
    inspection = inspect_template(
        filename="template.pdf",
        media_type="application/pdf",
        data=_blank_pdf(),
    )
    assert inspection.format == "pdf"
    assert inspection.placeholder_keys == ()


@pytest.mark.django_db
def test_docx_template_is_rejected():
    with pytest.raises(ValidationError) as exc:
        inspect_template(
            filename="template.docx",
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            data=b"not-a-real-docx",
        )
    assert "source_document" in exc.value.message_dict


@pytest.mark.django_db
def test_pdf_template_rejects_unsafe_tokens():
    with pytest.raises(ValidationError) as exc:
        inspect_template(
            filename="template.pdf",
            media_type="application/pdf",
            data=_pdf_with_unsafe_token(),
        )
    assert "source_document" in exc.value.message_dict


@pytest.mark.django_db
def test_merge_schema_must_match_extracted_placeholders():
    with pytest.raises(ValidationError) as exc:
        validate_merge_schema(
            [
                {
                    "key": "party.legalFirstName",
                    "type": "text",
                    "label": "First name",
                    "source": "party.legalFirstName",
                }
            ],
            placeholder_keys=["party.legalFirstName", "office.state"],
        )
    assert "source_document" in exc.value.message_dict


@pytest.mark.django_db
def test_published_versions_are_immutable(seeded_offices):
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-standard",
        name="ICA Standard",
        jurisdiction_state_codes=["VA"],
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        merge_schema=[
            {
                "key": "party.legalFirstName",
                "type": "text",
                "label": "First name",
                "source": "party.legalFirstName",
            }
        ],
    )
    version.source_format = "pdf"
    version.source_media_type = "application/pdf"
    version.source_checksum = "a" * 64
    version.docuseal_template_id = 99
    version.docuseal_external_id = "ext-99"
    version.extracted_placeholder_keys = ["party.legalFirstName"]
    version.preview_checksum = "b" * 64
    version.preview_generated_at = version.created_at
    version.published_at = version.created_at
    version.status = ContractTemplateVersion.Status.PUBLISHED
    version.full_clean()
    version.save()

    version.display_name = "Changed"
    with pytest.raises(ValidationError):
        version.full_clean()


@pytest.mark.django_db
def test_save_draft_uploads_pdf_and_prepares_docuseal_external_id(seeded_offices):
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-standard",
        name="ICA Standard",
        jurisdiction_state_codes=["VA"],
        company_wide=True,
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        merge_schema=[],
    )
    upload = SimpleUploadedFile(
        "template.pdf",
        _blank_pdf(),
        content_type="application/pdf",
    )
    with patch(
        "apps.contract.services.template_service.is_docuseal_builder_configured",
        return_value=True,
    ):
        saved = save_draft_version(
            actor,
            version=version,
            expected_version=version.updated_at.isoformat(),
            display_name="ICA Standard",
            description="Draft",
            merge_schema=[],
            source_upload=upload,
        )
    assert saved.source_format == "pdf"
    assert saved.docuseal_external_id.startswith("contract-template-version-")
    assert saved.docuseal_template_id is None


@pytest.mark.django_db
def test_publish_activate_and_retire_are_audited(seeded_offices):
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-standard",
        name="ICA Standard",
        jurisdiction_state_codes=["VA"],
        company_wide=True,
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        merge_schema=[
            {
                "key": "party.legalFirstName",
                "type": "text",
                "label": "First name",
                "source": "party.legalFirstName",
            }
        ],
    )
    upload = SimpleUploadedFile(
        "template.pdf",
        _blank_pdf(),
        content_type="application/pdf",
    )
    with patch(
        "apps.contract.services.template_service.is_docuseal_builder_configured",
        return_value=True,
    ):
        save_draft_version(
            actor,
            version=version,
            expected_version=version.updated_at.isoformat(),
            display_name="ICA Standard",
            description="Draft",
            merge_schema=[
                {
                    "key": "party.legalFirstName",
                    "type": "text",
                    "label": "First name",
                    "source": "party.legalFirstName",
                }
            ],
            source_upload=upload,
        )
    version.refresh_from_db()
    version.docuseal_template_id = 55
    version.extracted_placeholder_keys = ["party.legalFirstName"]
    version.preview_pdf.save(
        "preview.pdf",
        SimpleUploadedFile("p.pdf", b"%PDF-1.4"),
        save=False,
    )
    version.preview_checksum = "c" * 64
    version.preview_generated_at = version.created_at
    version.save()

    with patch(
        "apps.contract.services.template_service.get_template",
        return_value=_remote_template(template_id=55),
    ):
        publish_version(actor, version=version)
    version.refresh_from_db()
    activate_version(actor, version=version)
    version.refresh_from_db()
    retire_version(actor, version=version)

    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert "contract_template.version.published" in actions
    assert "contract_template.version.activated" in actions
    assert "contract_template.version.retired" in actions


@pytest.mark.django_db
def test_publish_requires_agent_signature_field(seeded_offices):
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-nosig",
        name="ICA",
        company_wide=True,
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        merge_schema=[
            {
                "key": "party.legalFirstName",
                "type": "text",
                "label": "First name",
                "source": "party.legalFirstName",
            }
        ],
    )
    version.docuseal_template_id = 12
    version.extracted_placeholder_keys = ["party.legalFirstName"]
    version.preview_pdf.save(
        "preview.pdf",
        SimpleUploadedFile("p.pdf", b"%PDF-1.4"),
        save=False,
    )
    version.preview_checksum = "c" * 64
    version.preview_generated_at = version.created_at
    version.save()

    remote = DocuSealTemplate(
        id=12,
        name="ICA",
        external_id="ext",
        fields=(
            DocuSealTemplateField(
                name="party.legalFirstName",
                field_type="text",
                role="Prefill",
                required=True,
            ),
        ),
    )
    with (
        patch(
            "apps.contract.services.template_service.get_template",
            return_value=remote,
        ),
        pytest.raises(ValidationError) as exc,
    ):
        publish_version(actor, version=version)
    assert "signature" in str(exc.value).lower()


@pytest.mark.django_db
def test_referenced_versions_cannot_be_retired(seeded_offices):
    actor = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-standard",
        name="ICA Standard",
        jurisdiction_state_codes=["VA"],
        company_wide=True,
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        merge_schema=[
            {
                "key": "party.legalFirstName",
                "type": "text",
                "label": "First name",
                "source": "party.legalFirstName",
            }
        ],
    )
    version.docuseal_template_id = 9
    version.extracted_placeholder_keys = ["party.legalFirstName"]
    version.preview_pdf.save(
        "preview.pdf",
        SimpleUploadedFile("p.pdf", b"%PDF-1.4"),
        save=False,
    )
    version.preview_checksum = "c" * 64
    version.preview_generated_at = version.created_at
    version.save()

    with patch(
        "apps.contract.services.template_service.get_template",
        return_value=_remote_template(template_id=9),
    ):
        publish_version(actor, version=version)
    activate_version(actor, version=version)
    AgentContract.objects.create(
        recipient=recipient,
        office=recipient.office,
        template_version=version,
        created_by=actor,
        effective_on=date.today(),
        party_snapshot={},
        office_snapshot={},
        terms_snapshot={},
    )

    with pytest.raises(ValidationError):
        retire_version(actor, version=version)
