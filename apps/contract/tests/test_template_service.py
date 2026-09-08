from __future__ import annotations

import io
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pypdf import PdfWriter

from apps.audit.models import AuditEvent
from apps.contract.field_layout import (
    assert_publishable_layout,
    normalize_field_layout,
)
from apps.contract.models import AgentContract, ContractTemplateVersion
from apps.contract.services.template_service import (
    activate_version,
    create_draft_version,
    create_template_family,
    publish_version,
    retire_version,
    save_draft_version,
    save_field_layout,
    serialize_template_row,
    serialize_version_detail,
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


def _hub_layout() -> list[dict]:
    return [
        {
            "id": "prefill-1",
            "name": "party.legalFirstName",
            "type": "text",
            "role": "Prefill",
            "page": 1,
            "x": 20,
            "y": 20,
            "w": 140,
            "h": 24,
        },
        {
            "id": "sig-1",
            "name": "AgentSignature",
            "type": "signature",
            "role": "Agent",
            "page": 1,
            "x": 20,
            "y": 80,
            "w": 180,
            "h": 48,
        },
        {
            "id": "date-1",
            "name": "AgentSignedOn",
            "type": "date",
            "role": "Agent",
            "page": 1,
            "x": 20,
            "y": 140,
            "w": 120,
            "h": 24,
        },
    ]


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


def test_normalize_field_layout_is_publishable():
    layout = normalize_field_layout(_hub_layout())
    assert len(layout) == 3
    assert_publishable_layout(layout)
    assert layout[1]["type"] == "signature"


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
    version.field_layout = _hub_layout()
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
def test_save_draft_uploads_pdf_and_resets_field_layout(seeded_offices):
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
    assert saved.field_layout == []
    assert saved.extracted_placeholder_keys == []


@pytest.mark.django_db
def test_save_field_layout_seeds_prefill_merge_keys(seeded_offices):
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-layout",
        name="ICA",
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
    save_draft_version(
        actor,
        version=version,
        expected_version=version.updated_at.isoformat(),
        display_name="ICA",
        description="",
        merge_schema=[],
        source_upload=upload,
    )
    version.refresh_from_db()
    saved = save_field_layout(actor, version=version, layout=_hub_layout())
    assert saved.extracted_placeholder_keys == ["party.legalFirstName"]
    assert saved.merge_schema[0]["key"] == "party.legalFirstName"


@pytest.mark.django_db
def test_save_field_layout_allows_unmapped_prefill_names_on_draft(seeded_offices):
    """Placer names like PrefillText are not hub sources until mapped later."""
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-placer-names",
        name="ICA",
        company_wide=True,
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        merge_schema=[],
    )
    save_draft_version(
        actor,
        version=version,
        expected_version=version.updated_at.isoformat(),
        display_name="ICA",
        description="",
        merge_schema=[],
        source_upload=SimpleUploadedFile(
            "template.pdf",
            _blank_pdf(),
            content_type="application/pdf",
        ),
    )
    version.refresh_from_db()
    layout = [
        {
            "id": "prefill-text",
            "name": "PrefillText",
            "type": "text",
            "role": "Prefill",
            "page": 1,
            "x": 10,
            "y": 10,
            "w": 120,
            "h": 24,
        },
        {
            "id": "sig-1",
            "name": "AgentSignature",
            "type": "signature",
            "role": "Agent",
            "page": 1,
            "x": 10,
            "y": 80,
            "w": 180,
            "h": 48,
        },
        {
            "id": "date-1",
            "name": "AgentSignedOn",
            "type": "date",
            "role": "Agent",
            "page": 1,
            "x": 10,
            "y": 140,
            "w": 120,
            "h": 24,
        },
    ]
    saved = save_field_layout(actor, version=version, layout=layout)
    assert saved.extracted_placeholder_keys == ["PrefillText"]
    assert saved.merge_schema == [
        {
            "key": "PrefillText",
            "label": "PrefillText",
            "type": "text",
            "source": "",
        }
    ]


@pytest.mark.django_db
def test_field_layout_json_post_persists_placer_prefill_fields(seeded_offices, client):
    """Inertia router.post sends JSON; empty Prefill sources must still save."""
    import json

    from apps.web.tests.test_permissions import inertia_page_script

    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-json-layout",
        name="ICA",
        company_wide=True,
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        merge_schema=[],
    )
    save_draft_version(
        actor,
        version=version,
        expected_version=version.updated_at.isoformat(),
        display_name="ICA",
        description="",
        merge_schema=[],
        source_upload=SimpleUploadedFile(
            "template.pdf",
            _blank_pdf(),
            content_type="application/pdf",
        ),
    )
    version.refresh_from_db()
    client.force_login(actor)
    layout = [
        {
            "id": "prefill-1",
            "name": "PrefillText",
            "type": "text",
            "role": "Prefill",
            "page": 1,
            "x": 12,
            "y": 18,
            "w": 140,
            "h": 24,
        },
        {
            "id": "sig-1",
            "name": "AgentSignature",
            "type": "signature",
            "role": "Agent",
            "page": 1,
            "x": 12,
            "y": 80,
            "w": 180,
            "h": 48,
        },
        {
            "id": "date-1",
            "name": "AgentSignedOn",
            "type": "date",
            "role": "Agent",
            "page": 1,
            "x": 12,
            "y": 140,
            "w": 120,
            "h": 24,
        },
    ]
    response = client.post(
        reverse(
            "contract_template_field_layout",
            kwargs={"version_id": version.pk},
        ),
        data=json.dumps(
            {
                "fieldLayoutJson": json.dumps(layout),
                "expectedVersion": version.updated_at.isoformat(),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {200, 302, 303}
    if response.status_code == 200:
        page = inertia_page_script(response)
        errors = (page.get("props") or {}).get("errors") or {}
        assert not errors.get("form") and not errors.get("fields"), errors
    version.refresh_from_db()
    assert version.field_layout[0]["name"] == "PrefillText"
    assert version.extracted_placeholder_keys == ["PrefillText"]
    assert version.merge_schema[0]["source"] == ""


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
    save_field_layout(actor, version=version, layout=_hub_layout())
    version.refresh_from_db()
    version.merge_schema = [
        {
            "key": "party.legalFirstName",
            "type": "text",
            "label": "First name",
            "source": "party.legalFirstName",
        }
    ]
    version.preview_pdf.save(
        "preview.pdf",
        SimpleUploadedFile("p.pdf", b"%PDF-1.4"),
        save=False,
    )
    version.preview_checksum = "c" * 64
    version.preview_generated_at = version.created_at
    version.save()

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
    version.field_layout = [
        {
            "id": "prefill-1",
            "name": "party.legalFirstName",
            "type": "text",
            "role": "Prefill",
            "page": 1,
            "x": 20,
            "y": 20,
            "w": 140,
            "h": 24,
        }
    ]
    version.extracted_placeholder_keys = ["party.legalFirstName"]
    version.preview_pdf.save(
        "preview.pdf",
        SimpleUploadedFile("p.pdf", b"%PDF-1.4"),
        save=False,
    )
    version.preview_checksum = "c" * 64
    version.preview_generated_at = version.created_at
    version.save()

    with pytest.raises(ValidationError) as exc:
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
    upload = SimpleUploadedFile(
        "template.pdf",
        _blank_pdf(),
        content_type="application/pdf",
    )
    save_draft_version(
        actor,
        version=version,
        expected_version=version.updated_at.isoformat(),
        display_name="ICA Standard",
        description="",
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
    save_field_layout(actor, version=version, layout=_hub_layout())
    version.refresh_from_db()
    version.merge_schema = [
        {
            "key": "party.legalFirstName",
            "type": "text",
            "label": "First name",
            "source": "party.legalFirstName",
        }
    ]
    version.preview_pdf.save(
        "preview.pdf",
        SimpleUploadedFile("p.pdf", b"%PDF-1.4"),
        save=False,
    )
    version.preview_checksum = "c" * 64
    version.preview_generated_at = version.created_at
    version.save()

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
        calculation_rule_version="1.0.0",
    )

    with pytest.raises(ValidationError):
        retire_version(actor, version=version)


@pytest.mark.django_db
def test_preview_url_is_hub_stream_not_storage_url(
    client, seeded_offices, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-preview-stream",
        name="ICA",
        company_wide=True,
    )
    version = create_draft_version(
        actor,
        template=template,
        version_label="1.0.0",
        merge_schema=[],
    )
    pdf = _blank_pdf()
    version.preview_pdf.save(
        "preview.pdf",
        SimpleUploadedFile("preview.pdf", pdf, content_type="application/pdf"),
        save=True,
    )
    detail = serialize_version_detail(version)
    assert detail["previewUrl"] == (
        f"/operations/contract-templates/templates/{version.pk}/preview.pdf"
    )
    assert "localhost:9000" not in (detail["previewUrl"] or "")

    client.force_login(actor)
    response = client.get(
        reverse("contract_template_preview_pdf", kwargs={"version_id": version.pk})
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


@pytest.mark.django_db
def test_create_rejects_duplicate_stable_key(seeded_offices, client):
    from apps.web.tests.test_permissions import inertia_page_script

    actor = company_admin(seeded_offices)
    create_template_family(
        actor,
        stable_key="ica-dup",
        name="Existing",
        company_wide=True,
    )
    client.force_login(actor)
    response = client.post(
        reverse("contract_template_create"),
        data={
            "stable_key": "ica-dup",
            "name": "Duplicate attempt",
            "description": "",
            "company_wide": "on",
            "version_label": "1.0.0",
            "context": "sheet",
        },
    )
    assert response.status_code == 422
    page = inertia_page_script(response)
    assert page["component"] == "ContractTemplateAdministration"
    assert page["props"]["createSheet"]["open"] is True
    assert "stable_key" in page["props"]["errors"]["fields"]


@pytest.mark.django_db
def test_template_rows_carry_their_own_status_presentation(seeded_offices):
    """Pages render a StatusBadge, so the label and tone come from the server.

    The template console previously printed the raw enum with a CSS
    `capitalize`, which made it the one list in the app that disagreed with
    every other one about how a status looks.
    """
    actor = company_admin(seeded_offices)
    template = create_template_family(
        actor,
        stable_key="ica-status-presentation",
        name="Status presentation",
        company_wide=True,
    )

    row = serialize_template_row(
        type(template)
        .objects.prefetch_related("versions")
        .select_related("active_version")
        .get(pk=template.pk)
    )

    assert row["statusLabel"] == "Draft"
    assert row["statusTone"] == "neutral"


def test_version_detail_carries_its_own_status_presentation(seeded_offices):
    from apps.contract.statuses import (
        template_version_status_label,
        template_version_status_tone,
    )

    assert template_version_status_label("published") == "Published"
    assert template_version_status_tone("published") == "info"
    assert template_version_status_tone("retired") == "warning"
    # An unknown code still renders, just without a claim about severity.
    assert template_version_status_tone("nonsense") == "neutral"
