from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from pypdf import PdfWriter

from apps.audit.models import AuditEvent
from apps.contract.models import AgentContract, ContractTemplateVersion
from apps.contract.services.template_service import (
    activate_version,
    create_draft_version,
    create_template_family,
    publish_version,
    retire_version,
    save_draft_version,
)
from apps.contract.template_security import inspect_template, validate_merge_schema
from apps.contract.tests.conftest import agent, company_admin


def _docx_with_tags(*tags: str) -> bytes:
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {controls}
  </w:body>
</w:document>"""
    controls = []
    for tag in tags:
        controls.append(
            f"""
            <w:sdt>
              <w:sdtPr><w:tag w:val="{tag}"/></w:sdtPr>
              <w:sdtContent>
                <w:p><w:r><w:t>{tag}</w:t></w:r></w:p>
              </w:sdtContent>
            </w:sdt>
            """
        )
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default
    Extension="rels"
    ContentType="application/vnd.openxmlformats-package.relationships+xml"
  />
  <Default Extension="xml" ContentType="application/xml"/>
  <Override
    PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
  />
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship
    Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"
  />
</Relationships>"""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr(
            "word/document.xml", document.format(controls="".join(controls))
        )
    return out.getvalue()


def _pdf_with_unsafe_token() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue() + b"\n/OpenAction\n"


@pytest.mark.django_db
def test_docx_template_inspection_extracts_content_control_tags():
    inspection = inspect_template(
        filename="template.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data=_docx_with_tags("party.legalFirstName", "office.state"),
    )
    assert inspection.format == "docx"
    assert inspection.placeholder_keys == ("office.state", "party.legalFirstName")


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
    version.source_format = "docx"
    version.source_media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    version.source_checksum = "a" * 64
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
def test_save_draft_version_rejects_unknown_placeholder_upload(seeded_offices):
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
    upload = SimpleUploadedFile(
        "template.docx",
        _docx_with_tags("party.legalFirstName", "office.state"),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    with pytest.raises(ValidationError) as exc:
        save_draft_version(
            actor,
            version=version,
            expected_version=version.updated_at.isoformat(),
            display_name="ICA Standard",
            description="Draft",
            merge_schema=list(version.merge_schema),
            source_upload=upload,
        )
    assert "source_document" in exc.value.message_dict


@pytest.mark.django_db
def test_publish_activate_and_retire_are_audited(seeded_offices, monkeypatch):
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
    upload = SimpleUploadedFile(
        "template.docx",
        _docx_with_tags("party.legalFirstName"),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    save_draft_version(
        actor,
        version=version,
        expected_version=version.updated_at.isoformat(),
        display_name="ICA Standard",
        description="Draft",
        merge_schema=list(version.merge_schema),
        source_upload=upload,
    )
    version.refresh_from_db()

    monkeypatch.setattr(
        "apps.contract.services.template_service.render_preview_pdf",
        lambda **kwargs: (b"%PDF-1.4 preview", ("party.legalFirstName",)),
    )
    from apps.contract.services.template_service import generate_preview

    generate_preview(version)
    version.refresh_from_db()

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
def test_referenced_versions_cannot_be_retired(seeded_offices, monkeypatch):
    actor = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
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
    upload = SimpleUploadedFile(
        "template.docx",
        _docx_with_tags("party.legalFirstName"),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    save_draft_version(
        actor,
        version=version,
        expected_version=version.updated_at.isoformat(),
        display_name="ICA Standard",
        description="Draft",
        merge_schema=list(version.merge_schema),
        source_upload=upload,
    )
    version.refresh_from_db()
    monkeypatch.setattr(
        "apps.contract.services.template_service.render_preview_pdf",
        lambda **kwargs: (b"%PDF-1.4 preview", ("party.legalFirstName",)),
    )
    from apps.contract.services.template_service import generate_preview

    generate_preview(version)
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
